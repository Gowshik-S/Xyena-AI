from datetime import datetime
from uuid import UUID

from pydantic import Field

from .common import ContractModel


class AuthenticatedPrincipal(ContractModel):
    subject: str
    tenant_id: UUID
    organization_id: UUID
    user_id: UUID
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    expires_at: datetime | None = None


class ConsentView(ContractModel):
    id: UUID
    purpose: str
    data_classes: list[str] = Field(default_factory=list)
    status: str
    valid_from: datetime
    valid_until: datetime | None = None

