from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .common import ContractModel

RunStatus = Literal[
    "QUEUED",
    "ASSEMBLING_CONTEXT",
    "RUNNING_MODEL",
    "TOOL_REQUESTED",
    "POLICY_CHECK",
    "WAITING_APPROVAL",
    "CALLING_TOOL",
    "TOOL_RESULT_RECORDED",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
    "BLOCKED",
]


class AgentDefinitionContract(ContractModel):
    id: UUID
    stable_name: str
    display_name: str
    purpose: str
    status: str


class AgentVersionContract(ContractModel):
    id: UUID
    definition_id: UUID
    version: str
    instructions_hash: str
    model_policy: dict[str, Any]
    output_schema: dict[str, Any]
    status: str


class RunView(ContractModel):
    id: UUID
    conversation_id: UUID
    session_id: UUID
    tenant_id: UUID
    organization_id: UUID
    user_id: UUID
    status: RunStatus
    start_agent: str
    correlation_id: UUID
    input_message_id: UUID | None
    result_message_id: UUID | None
    error_code: str | None
    error_detail: str | None
    usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RunEvent(ContractModel):
    id: UUID
    run_id: UUID
    sequence: int
    event_type: str
    status: str
    data: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class StructuredFinding(ContractModel):
    finding_type: str
    status: str
    confidence: float = Field(ge=0, le=1)
    facts: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[UUID] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    security_flags: list[str] = Field(default_factory=list)

