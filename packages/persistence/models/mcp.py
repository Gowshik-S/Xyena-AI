from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class MCPServer(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "servers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "label"),
        {"schema": "mcp"},
    )

    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    transport: Mapped[str] = mapped_column(String(40), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(2000), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(50), nullable=False, default="BEARER")
    secret_ref: Mapped[str | None] = mapped_column(String(500))
    trust_tier: Mapped[str] = mapped_column(String(50), nullable=False, default="UNREVIEWED")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_REVIEW")
    allowed_egress_hosts: Mapped[list[str]] = mapped_column(ARRAY(String(255)), nullable=False, default=list)
    timeout_seconds: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    discovery_hash: Mapped[str | None] = mapped_column(String(128))
    last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MCPServerVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "server_versions"
    __table_args__ = (
        UniqueConstraint("server_id", "discovery_hash"),
        {"schema": "mcp"},
    )

    server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mcp.servers.id"), nullable=False, index=True
    )
    implementation_name: Mapped[str | None] = mapped_column(String(200))
    implementation_version: Mapped[str | None] = mapped_column(String(100))
    protocol_version: Mapped[str | None] = mapped_column(String(100))
    discovery_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    discovery_document: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class MCPTool(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "tools"
    __table_args__ = (
        UniqueConstraint("server_id", "original_name"),
        UniqueConstraint(
            "server_id", "canonical_name", name="uq_mcp_tools_server_canonical_name"
        ),
        {"schema": "mcp"},
    )

    server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mcp.servers.id"), nullable=False, index=True
    )
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_REVIEW")


class MCPToolVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tool_versions"
    __table_args__ = (
        UniqueConstraint("tool_id", "schema_hash"),
        {"schema": "mcp"},
    )

    tool_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mcp.tools.id"), nullable=False, index=True
    )
    schema_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    input_schema: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    risk_class: Mapped[str] = mapped_column(String(30), nullable=False, default="READ")
    side_effects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    parallel_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hosted_mcp_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_REVIEW")


class MCPToolPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "tool_policies"
    __table_args__ = {"schema": "mcp"}

    tool_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mcp.tool_versions.id"), nullable=False, index=True
    )
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    required_roles: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    required_purposes: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    required_consents: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    allowed_agents: Mapped[list[str]] = mapped_column(ARRAY(String(150)), nullable=False, default=list)
    approval_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="POLICY")
    timeout_seconds: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, default=30)
    maximum_result_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=262144)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")


class AgentToolGrant(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "agent_tool_grants"
    __table_args__ = (
        UniqueConstraint("agent_version_id", "tool_version_id"),
        {"schema": "mcp"},
    )

    agent_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    tool_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mcp.tool_versions.id"), nullable=False, index=True
    )
    constraints: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")


class MCPToolCall(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "tool_calls"
    __table_args__ = {"schema": "mcp"}

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    agent_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    agent_name: Mapped[str] = mapped_column(String(150), nullable=False)
    server_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tool_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_arguments: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    resource_refs: Mapped[list[str]] = mapped_column(ARRAY(String(500)), nullable=False, default=list)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="REQUESTED", index=True)
    guardian_decision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    authorization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)


class MCPCallAttempt(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "call_attempts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "call_id", "attempt_number"),
        {"schema": "mcp"},
    )

    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mcp.tool_calls.id"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    server_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_class: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(Text)


class MCPToolResult(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "tool_results"
    __table_args__ = (
        UniqueConstraint("tenant_id", "call_id"),
        {"schema": "mcp"},
    )

    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mcp.tool_calls.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    model_projection: Mapped[dict[str, object] | list[object] | str | None] = mapped_column(JSONB)
    raw_object_ref: Mapped[str | None] = mapped_column(String(1000))
    raw_hash: Mapped[str | None] = mapped_column(String(128))
    normalized_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    classification: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class MCPHealthEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "health_events"
    __table_args__ = {"schema": "mcp"}

    server_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_signal: Mapped[str | None] = mapped_column(String(200))
    circuit_transition: Mapped[str | None] = mapped_column(String(50))

