from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .common import ContractModel


class MemoryCreateRequest(ContractModel):
    kind: Literal["PREFERENCE", "PROFILE", "WORKING_FACT", "ORGANIZATION_FACT"]
    content: str = Field(min_length=1, max_length=20_000)
    structured_content: dict[str, Any] = Field(default_factory=dict)
    sensitivity: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] = "INTERNAL"
    source_type: str = Field(default="USER_ASSERTED", max_length=100)
    source_id: UUID | None = None
    expires_at: datetime | None = None


class MemoryView(ContractModel):
    id: UUID
    tenant_id: UUID
    organization_id: UUID
    user_id: UUID | None
    kind: str
    content: str
    structured_content: dict[str, Any]
    sensitivity: str
    source_type: str
    source_id: UUID | None
    confidence: float
    status: str
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MemorySearchRequest(ContractModel):
    query: str = Field(min_length=1, max_length=2000)
    kinds: list[str] = Field(default_factory=list)
    maximum_sensitivity: str = "CONFIDENTIAL"
    limit: int = Field(default=10, ge=1, le=50)


class ContextSnapshotView(ContractModel):
    id: UUID
    run_id: UUID
    turn_number: int
    token_budget: int
    estimated_tokens: int
    policy_bundle_version: str
    snapshot_hash: str
    items: list[dict[str, Any]]
    created_at: datetime
