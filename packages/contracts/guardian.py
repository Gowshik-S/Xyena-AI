from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .common import ContractModel
from .tools import CanonicalToolRequest, ToolRiskClass


class GuardianOutcome(StrEnum):
    ALLOW = "ALLOW"
    VERIFY = "VERIFY"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


class ToolPolicySnapshot(ContractModel):
    risk_class: ToolRiskClass
    required_roles: tuple[str, ...] = ()
    required_purposes: tuple[str, ...] = ()
    required_consents: tuple[str, ...] = ()
    allowed_agents: tuple[str, ...] = ()
    approval_mode: Literal["NEVER", "POLICY", "ALWAYS"] = "POLICY"
    side_effects: bool = False
    idempotent: bool = True


class GuardianEvaluationRequest(ContractModel):
    request: CanonicalToolRequest
    policy: ToolPolicySnapshot


class GuardianEvaluationResponse(ContractModel):
    decision_id: UUID
    outcome: GuardianOutcome
    reason_codes: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    policy_bundle_version: str
    approval_id: UUID | None = None
    authorization_id: UUID | None = None
    authorization_token: str | None = None
    expires_at: datetime | None = None


class ApprovalView(ContractModel):
    id: UUID
    tenant_id: UUID
    decision_id: UUID
    tool_call_id: UUID
    requested_for_user_id: UUID
    summary: str
    risk_class: ToolRiskClass
    status: str
    required_approver_roles: list[str]
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ApprovalActionCreate(ContractModel):
    action: Literal["APPROVE", "REJECT"]
    actor_user_id: UUID
    actor_roles: tuple[str, ...] = ()
    reason: str = Field(min_length=1, max_length=1000)
    correlation_id: UUID


class ApprovalDecisionRequest(ContractModel):
    action: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=1, max_length=1000)


class ApprovalActionResult(ContractModel):
    approval: ApprovalView
    resume_required: bool


class AuthorizationConsumeRequest(ContractModel):
    token: str
    call_id: UUID
    request_hash: str = Field(min_length=64, max_length=128)
    correlation_id: UUID


class AuthorizationConsumeResult(ContractModel):
    authorization_id: UUID
    consumed: bool
    constraints: dict[str, Any] = Field(default_factory=dict)


class ApprovedAuthorizationRequest(ContractModel):
    call_id: UUID
    request_hash: str = Field(min_length=64, max_length=128)
    correlation_id: UUID
