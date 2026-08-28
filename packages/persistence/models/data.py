from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class DataObject(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "objects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "object_key"),
        {"schema": "data_vault"},
    )

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    owner_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    media_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_name: Mapped[str | None] = mapped_column(String(200))
    attributes: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    encryption_key_ref: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataGrant(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "grants"
    __table_args__ = {"schema": "data_vault"}

    data_object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("data_vault.objects.id"), nullable=False, index=True
    )
    grantor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    grantee_type: Mapped[str] = mapped_column(String(30), nullable=False)
    grantee_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    purposes: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataAccessEvent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "access_events"
    __table_args__ = {"schema": "data_vault"}

    data_object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("data_vault.objects.id"), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
