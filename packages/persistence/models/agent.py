from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class AgentDefinition(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "definitions"
    __table_args__ = {"schema": "agent"}

    stable_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False, default="platform")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")


class AgentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "versions"
    __table_args__ = (
        UniqueConstraint("definition_id", "version"),
        {"schema": "agent"},
    )

    definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent.definitions.id"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    instructions_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    instructions_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    model_policy: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    context_profile: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    budgets: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")


class AgentRun(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "runs"
    __table_args__ = {"schema": "agent"}

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    start_agent: Mapped[str] = mapped_column(String(100), nullable=False, default="xyena-supervisor")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="QUEUED", index=True)
    input_message_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    result_message_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(Text)
    usage: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    runtime_scope: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRunStep(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "run_steps"
    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", "sequence"),
        {"schema": "agent"},
    )

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent.runs.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    input_ref: Mapped[str | None] = mapped_column(String(500))
    output_ref: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class AgentRunEvent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", "sequence"),
        {"schema": "agent"},
    )

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent.runs.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
