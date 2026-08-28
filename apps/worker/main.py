import asyncio
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from packages.config import get_settings
from packages.observability import configure_logging, get_logger
from packages.persistence import get_database
from packages.persistence.models.ops import Job
from apps.worker.handlers import handle_agent_run, handle_mcp_resume, handle_memory_embed

logger = get_logger(__name__)


class Worker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.database = get_database()
        self.owner = f"{socket.gethostname()}:{id(self)}"
        self.handlers: dict[str, Any] = {}

    def register(self, job_type: str, handler: Any) -> None:
        self.handlers[job_type] = handler

    async def run_forever(self) -> None:
        configure_logging(self.settings.log_level)
        logger.info("worker_started", owner=self.owner)
        while True:
            processed = await self.process_one()
            if not processed:
                await asyncio.sleep(self.settings.worker_poll_seconds)

    async def process_one(self) -> bool:
        database = self.database
        async with database.session(service_role="worker") as db:
            job = await db.scalar(
                select(Job)
                .where(Job.state == "AVAILABLE", Job.available_at <= datetime.now(UTC))
                .order_by(Job.available_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return False
            job.state = "RUNNING"
            job.lease_owner = self.owner
            job.lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
            job.attempts += 1
            job_id = job.id
            tenant_id = job.tenant_id
            job_type = job.job_type
            payload = dict(job.payload)

        handler = self.handlers.get(job_type)
        if handler is None:
            await self._fail(job_id, tenant_id, f"No handler registered for {job_type}")
            return True
        try:
            await handler(tenant_id=tenant_id, **payload)
        except Exception as exc:
            await self._fail(job_id, tenant_id, str(exc))
            logger.exception("job_failed", job_id=str(job_id), job_type=job_type)
        else:
            async with database.session(tenant_id=tenant_id, service_role="worker") as db:
                current = await db.get(Job, job_id)
                if current is not None:
                    current.state = "COMPLETED"
                    current.lease_owner = None
                    current.lease_expires_at = None
        return True

    async def _fail(self, job_id: UUID, tenant_id: UUID, error: str) -> None:
        async with self.database.session(tenant_id=tenant_id, service_role="worker") as db:
            job = await db.get(Job, job_id)
            if job is None:
                return
            job.last_error = error[:4000]
            job.lease_owner = None
            job.lease_expires_at = None
            if job.attempts >= job.max_attempts:
                job.state = "FAILED"
            else:
                job.state = "AVAILABLE"
                job.available_at = datetime.now(UTC) + timedelta(seconds=2**job.attempts)


async def main() -> None:
    worker = Worker()
    worker.register("agent.run", handle_agent_run)
    worker.register("mcp.resume", handle_mcp_resume)
    worker.register("memory.embed", handle_memory_embed)
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
