import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.contracts.context import RuntimeContext
from packages.persistence.models.agent import AgentRun
from packages.persistence.models.conversation import Message
from packages.persistence.models.memory import ContextSnapshot, MemoryRecord
from packages.tools.canonical import canonical_hash


@dataclass(frozen=True)
class AssembledContext:
    trusted_envelope: dict[str, object]
    model_items: list[dict[str, object]]
    snapshot_id: str
    estimated_tokens: int


class ContextAssembler:
    def __init__(self, token_budget: int = 24_000) -> None:
        self.token_budget = token_budget

    async def assemble(
        self,
        db: AsyncSession,
        run: AgentRun,
        runtime_context: RuntimeContext,
        turn_number: int = 1,
    ) -> AssembledContext:
        messages = list(
            reversed(
                (
                    await db.scalars(
                        select(Message)
                        .where(
                            Message.tenant_id == run.tenant_id,
                            Message.conversation_id == run.conversation_id,
                        )
                        .order_by(Message.sequence.desc())
                        .limit(40)
                    )
                ).all()
            )
        )
        memories = (
            await db.scalars(
                select(MemoryRecord)
                .where(
                    MemoryRecord.tenant_id == run.tenant_id,
                    MemoryRecord.organization_id == run.organization_id,
                    or_(MemoryRecord.user_id == run.user_id, MemoryRecord.user_id.is_(None)),
                    MemoryRecord.status == "ACTIVE",
                    MemoryRecord.sensitivity.in_(["PUBLIC", "INTERNAL", "CONFIDENTIAL"]),
                    or_(MemoryRecord.expires_at.is_(None), MemoryRecord.expires_at > datetime.now(UTC)),
                )
                .order_by(MemoryRecord.updated_at.desc())
                .limit(20)
            )
        ).all()
        trusted = {
            "tenant_id": str(runtime_context.tenant_id),
            "organization_id": str(runtime_context.organization_id),
            "user_id": str(runtime_context.user_id),
            "session_id": str(runtime_context.session_id),
            "run_id": str(run.id),
            "roles": list(runtime_context.roles),
            "consent_ids": [str(value) for value in runtime_context.consent_ids],
            "policy_bundle_version": runtime_context.policy_bundle_version,
        }
        items: list[dict[str, object]] = []
        for memory in reversed(memories):
            items.append(
                {
                    "type": "memory",
                    "trust": "UNTRUSTED_DATA",
                    "memory_id": str(memory.id),
                    "kind": memory.kind,
                    "content": memory.content,
                    "sensitivity": memory.sensitivity,
                }
            )
        for message in messages:
            content: object = message.structured_content or message.text_content or ""
            items.append(
                {
                    "type": "message",
                    "trust": "UNTRUSTED_DATA",
                    "message_id": str(message.id),
                    "role": message.role,
                    "content": content,
                    "sensitivity": message.sensitivity,
                }
            )
        while self._estimate(trusted, items) > self.token_budget and len(items) > 1:
            items.pop(0)
        estimated = self._estimate(trusted, items)
        snapshot_document = {"trusted_envelope": trusted, "items": items}
        snapshot = ContextSnapshot(
            id=uuid4(),
            tenant_id=run.tenant_id,
            run_id=run.id,
            turn_number=turn_number,
            token_budget=self.token_budget,
            estimated_tokens=estimated,
            policy_bundle_version=runtime_context.policy_bundle_version,
            snapshot_hash=canonical_hash(snapshot_document),
            items=items,
        )
        db.add(snapshot)
        await db.flush()
        return AssembledContext(trusted, items, str(snapshot.id), estimated)

    @staticmethod
    def _estimate(trusted: dict[str, object], items: list[dict[str, object]]) -> int:
        return max(1, len(json.dumps({"trusted": trusted, "items": items}, default=str)) // 4)
