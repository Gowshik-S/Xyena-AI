from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class Session(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "conversation"}

    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class Conversation(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "conversations"
    __table_args__ = {"schema": "conversation"}

    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversation.sessions.id"), nullable=False, index=True
    )
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    model_policy_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")


class ConversationMember(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "conversation_members"
    __table_args__ = (
        UniqueConstraint("tenant_id", "conversation_id", "user_id"),
        {"schema": "conversation"},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversation.conversations.id"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    member_role: Mapped[str] = mapped_column(String(50), nullable=False, default="OWNER")
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "conversation_id", "sequence"),
        {"schema": "conversation"},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversation.conversations.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text)
    structured_content: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    sensitivity: Mapped[str] = mapped_column(String(30), nullable=False, default="INTERNAL")
    supersedes_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    attributes: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class ProviderState(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, VersionMixin):
    __tablename__ = "provider_state"
    __table_args__ = (
        UniqueConstraint("tenant_id", "conversation_id", "provider"),
        {"schema": "conversation"},
    )

    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_conversation_id: Mapped[str | None] = mapped_column(String(255))
    previous_response_id: Mapped[str | None] = mapped_column(String(255))
    encrypted_state: Mapped[str | None] = mapped_column(Text)

