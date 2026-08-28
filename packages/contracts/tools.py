from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, SecretStr

from .common import ContractModel
from .context import RuntimeContext


class ToolRiskClass(StrEnum):
    READ = "READ"
    SENSITIVE_READ = "SENSITIVE_READ"
    MUTATE = "MUTATE"
    PRIVILEGED = "PRIVILEGED"


class MCPTransport(StrEnum):
    STREAMABLE_HTTP = "STREAMABLE_HTTP"
    STDIO_DEV = "STDIO_DEV"
    HOSTED_MCP = "HOSTED_MCP"
    IN_PROCESS = "IN_PROCESS"


class ToolCallStatus(StrEnum):
    REQUESTED = "REQUESTED"
    VALIDATED = "VALIDATED"
    POLICY_CHECK = "POLICY_CHECK"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    CALLING = "CALLING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"


class MCPServerCreate(ContractModel):
    label: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,99}$")
    description: str = Field(min_length=1, max_length=1000)
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    endpoint: AnyHttpUrl
    auth_type: str = "BEARER"
    secret_ref: str | None = Field(default=None, max_length=500)
    trust_tier: str = "UNREVIEWED"
    allowed_egress_hosts: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=30, gt=0, le=300)
    max_retries: int = Field(default=2, ge=0, le=5)


class MCPServerView(ContractModel):
    id: UUID
    tenant_id: UUID | None
    label: str
    description: str
    transport: str
    endpoint: str
    auth_type: str
    trust_tier: str
    status: str
    last_discovered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DiscoveredTool(ContractModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = Field(default_factory=dict)


class ToolPolicyCreate(ContractModel):
    canonical_name: str
    risk_class: ToolRiskClass
    required_roles: list[str] = Field(default_factory=list)
    required_purposes: list[str] = Field(default_factory=list)
    required_consents: list[str] = Field(default_factory=list)
    allowed_agents: list[str] = Field(default_factory=list)
    approval_mode: Literal["NEVER", "POLICY", "ALWAYS"] = "POLICY"
    side_effects: bool = False
    idempotent: bool = True
    parallel_allowed: bool = False
    hosted_mcp_allowed: bool = False
    timeout_seconds: float = Field(default=30, gt=0, le=300)
    maximum_result_bytes: int = Field(default=262_144, ge=1024, le=10_485_760)


class ToolIntent(ContractModel):
    requested_name: str
    arguments: dict[str, Any]
    purpose: str = Field(min_length=1, max_length=500)
    resource_refs: list[str] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=255)


class CanonicalToolRequest(ContractModel):
    call_id: UUID
    run_id: UUID
    agent_version_id: UUID | None = None
    agent_name: str
    scope: RuntimeContext
    server_id: UUID
    tool_version_id: UUID
    canonical_name: str
    original_name: str
    normalized_arguments: dict[str, Any]
    purpose: str
    resource_refs: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None
    request_hash: str


class ToolCallSubmit(ContractModel):
    run_id: UUID
    agent_version_id: UUID | None = None
    agent_name: str
    context: RuntimeContext
    intent: ToolIntent


class ToolCallResume(ContractModel):
    tenant_id: UUID
    call_id: UUID
    correlation_id: UUID


class SafeToolResult(ContractModel):
    call_id: UUID
    status: Literal["SUCCEEDED", "FAILED", "UNKNOWN", "BLOCKED"]
    model_projection: dict[str, Any] | list[Any] | str | None = None
    result_ref: UUID | None = None
    provenance_hash: str
    security_flags: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class ToolCallView(ContractModel):
    id: UUID
    run_id: UUID
    tenant_id: UUID
    tool_version_id: UUID
    canonical_name: str
    status: str
    purpose: str
    request_hash: str
    idempotency_key: str | None
    created_at: datetime
    updated_at: datetime
