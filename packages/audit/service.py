import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.persistence.models.audit import AuditEvent, OutboxEvent


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


async def append_audit_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_type: str,
    actor_id: str,
    event_type: str,
    subject_type: str,
    subject_id: UUID,
    correlation_id: UUID,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    payload = payload or {}
    last_event = await session.scalar(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.sequence.desc())
        .limit(1)
        .with_for_update()
    )
    sequence = (last_event.sequence + 1) if last_event else 1
    previous_hash = last_event.event_hash if last_event else None
    occurred_at = datetime.now(UTC)
    canonical = {
        "tenant_id": str(tenant_id),
        "sequence": sequence,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "event_type": event_type,
        "subject_type": subject_type,
        "subject_id": str(subject_id),
        "correlation_id": str(correlation_id),
        "payload": payload,
        "previous_hash": previous_hash,
        "occurred_at": occurred_at.isoformat(),
    }
    event_hash = hashlib.sha256(_canonical_json(canonical).encode()).hexdigest()
    event = AuditEvent(
        id=uuid4(),
        tenant_id=tenant_id,
        sequence=sequence,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload,
        correlation_id=correlation_id,
        previous_hash=previous_hash,
        event_hash=event_hash,
        occurred_at=occurred_at,
    )
    session.add(event)
    return event


async def enqueue_outbox(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    aggregate_type: str,
    aggregate_id: UUID,
    aggregate_version: int,
    event_type: str,
    correlation_id: UUID,
    payload: dict[str, Any],
) -> OutboxEvent:
    event = OutboxEvent(
        id=uuid4(),
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        schema_version="1.0",
        payload=payload,
        correlation_id=correlation_id,
        created_at=datetime.now(UTC),
        attempt_count=0,
    )
    session.add(event)
    return event

