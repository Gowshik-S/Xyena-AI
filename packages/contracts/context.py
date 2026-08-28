from datetime import datetime
from uuid import UUID

from pydantic import Field

from .common import ContractModel


class RuntimeContext(ContractModel):
    tenant_id: UUID
    organization_id: UUID
    user_id: UUID
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    run_id: UUID | None = None
    case_id: UUID | None = None
    correlation_id: UUID
    roles: tuple[str, ...] = ()
    consent_ids: tuple[UUID, ...] = ()
    policy_bundle_version: str = "platform-default"
    locale: str = "en"
    timezone: str = "UTC"


class ContextItem(ContractModel):
    source_type: str
    source_id: UUID | None = None
    content: dict[str, object] | str
    token_count: int = 0
    sensitivity: str = "INTERNAL"
    trust_class: str = "UNTRUSTED"


class ContextSnapshotContract(ContractModel):
    id: UUID
    run_id: UUID
    turn_number: int
    token_budget: int
    policy_version: str
    snapshot_hash: str
    created_at: datetime
    items: list[ContextItem] = Field(default_factory=list)

