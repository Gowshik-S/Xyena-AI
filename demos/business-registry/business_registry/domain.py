import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditEvent, OutboxEvent


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def record_change(
    db: AsyncSession,
    *,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    event_type: str,
    actor_type: str,
    actor_id: str,
    reason: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    correlation_id = str(uuid4())
    db.add(
        AuditEvent(
            id=str(uuid4()),
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            metadata_json=metadata or {},
        )
    )
    db.add(
        OutboxEvent(
            id=str(uuid4()),
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            event_type=event_type,
            payload={"id": aggregate_id, "version": aggregate_version},
            correlation_id=correlation_id,
        )
    )
