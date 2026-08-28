import asyncio
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select

from packages.config import get_settings
from packages.observability import configure_logging, configure_worker_telemetry, get_logger
from packages.persistence import get_database
from packages.persistence.models.ops import Job
from packages.persistence.models.audit import OutboxEvent
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
        configure_worker_telemetry("xyena-worker")
        logger.info("worker_started", owner=self.owner)
        while True:
            recovered = await self.recover_expired_lease()
            processed = recovered or await self.process_one() or await self.publish_outbox_one()
            if not processed:
                await asyncio.sleep(self.settings.worker_poll_seconds)

    async def recover_expired_lease(self) -> bool:
        async with self.database.session(service_role="worker") as db:
            job = await db.scalar(
                select(Job)
                .where(
                    Job.state == "RUNNING",
                    Job.lease_expires_at.is_not(None),
                    Job.lease_expires_at < datetime.now(UTC),
                )
                .order_by(Job.lease_expires_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return False
            job.state = "AVAILABLE" if job.attempts < job.max_attempts else "FAILED"
            job.available_at = datetime.now(UTC)
            job.lease_owner = None
            job.lease_expires_at = None
            job.last_error = "Worker lease expired before completion."
            return True

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

    async def publish_outbox_one(self) -> bool:
        endpoint = self.settings.event_webhook_url
        if endpoint is None:
            return False
        async with self.database.session(service_role="worker") as db:
            event = await db.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                return False
            token = self.settings.service_token
            headers = {
                "Content-Type": "application/json",
                "X-Correlation-ID": str(event.correlation_id),
                "X-Xyena-Event-ID": str(event.id),
            }
            if token is not None:
                headers["Authorization"] = f"Bearer {token.get_secret_value()}"
            envelope = {
                "id": str(event.id),
                "tenant_id": str(event.tenant_id),
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "aggregate_version": event.aggregate_version,
                "event_type": event.event_type,
                "schema_version": event.schema_version,
                "payload": event.payload,
                "correlation_id": str(event.correlation_id),
                "created_at": event.created_at.isoformat(),
            }
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.post(str(endpoint), json=envelope, headers=headers)
                    response.raise_for_status()
            except Exception as exc:
                event.attempt_count += 1
                event.last_error = str(exc)[:4000]
                return False
            event.published_at = datetime.now(UTC)
            event.attempt_count += 1
            event.last_error = None
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
