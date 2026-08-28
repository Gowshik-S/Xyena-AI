from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TenantScopedMixin, UUIDPrimaryKeyMixin


class AuditEvent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sequence"),
        {"schema": "audit"},
    )

    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    previous_hash: Mapped[str | None] = mapped_column(String(128))
    event_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEvent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "outbox"
    __table_args__ = {"schema": "audit"}

    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    aggregate_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    event_type: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0")
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

