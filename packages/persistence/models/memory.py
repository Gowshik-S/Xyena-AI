from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class SessionItem(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "session_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "session_id", "sequence"),
        {"schema": "memory"},
    )

    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversation.sessions.id"), nullable=False, index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversation.conversations.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryRecord(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "records"
    __table_args__ = {"schema": "memory"}

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    sensitivity: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL")
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryEvidence(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "evidence"
    __table_args__ = {"schema": "memory"}

    memory_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("memory.records.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1000), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(128), nullable=False)


class ContextSnapshot(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "context_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", "turn_number"),
        {"schema": "memory"},
    )

    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    turn_number: Mapped[int] = mapped_column(nullable=False)
    token_budget: Mapped[int] = mapped_column(nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(nullable=False)
    policy_bundle_version: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    items: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
