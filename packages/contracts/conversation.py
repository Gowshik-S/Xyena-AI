from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .common import ContractModel


class SessionCreateRequest(ContractModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None


class SessionView(ContractModel):
    id: UUID
    tenant_id: UUID
    organization_id: UUID
    user_id: UUID
    status: str
    last_seen_at: datetime
    expires_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime


class ConversationCreateRequest(ContractModel):
    session_id: UUID
    title: str | None = Field(default=None, max_length=200)
    model_policy_id: str = "default"


class ConversationView(ContractModel):
    id: UUID
    session_id: UUID
    tenant_id: UUID
    organization_id: UUID
    user_id: UUID
    title: str | None
    status: str
    model_policy_id: str
    created_at: datetime
    updated_at: datetime


class MessageCreateRequest(ContractModel):
    content: str = Field(min_length=1, max_length=100_000)
    case_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageView(ContractModel):
    id: UUID
    conversation_id: UUID
    sequence: int
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | dict[str, Any]
    sensitivity: str
    created_at: datetime


class MessageAccepted(ContractModel):
    message: MessageView
    run_id: UUID
    status: str = "QUEUED"

