from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class GuardianPolicyBundle(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "policy_bundles"
    __table_args__ = (UniqueConstraint("stable_name", "bundle_version"), {"schema": "guardian"})

    stable_name: Mapped[str] = mapped_column(String(100), nullable=False)
    bundle_version: Mapped[str] = mapped_column(String(100), nullable=False)
    document: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    document_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuardianDecision(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "decisions"
    __table_args__ = {"schema": "guardian"}

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    tool_call_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evaluation_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_bundle_version: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    reason_codes: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    constraints: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GuardianApprovalRequest(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "approval_requests"
    __table_args__ = {"schema": "guardian"}

    decision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    tool_call_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    requested_for_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk_class: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", index=True)
    required_approver_roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuardianApprovalAction(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "approval_actions"
    __table_args__ = {"schema": "guardian"}

    approval_request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    actor_roles: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)


class GuardianAuthorization(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "authorizations"
    __table_args__ = {"schema": "guardian"}

    decision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    tool_call_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    token_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    constraints: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
