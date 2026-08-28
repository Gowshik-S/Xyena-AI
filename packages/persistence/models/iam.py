from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "iam"}

    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    data_region: Mapped[str] = mapped_column(String(50), nullable=False, default="default")
    policy_bundle_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")


class Organization(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug"),
        {"schema": "iam"},
    )

    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("iam.organizations.id"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(50), nullable=False, default="CUSTOMER")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")


class User(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idp_subject_hash"),
        {"schema": "iam"},
    )

    idp_subject_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="en")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")


class Membership(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "organization_id", "user_id"),
        {"schema": "iam"},
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("iam.organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("iam.users.id"), nullable=False, index=True
    )
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")


class Consent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "consents"
    __table_args__ = {"schema": "iam"}

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    data_classes: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proof_ref: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class ServiceIdentity(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "service_identities"
    __table_args__ = {"schema": "iam"}

    workload_name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    audience: Mapped[str] = mapped_column(String(200), nullable=False)
    key_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(150)), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")

