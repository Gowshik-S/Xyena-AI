from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .common import ContractModel


class DataObjectRegisterRequest(ContractModel):
    object_key: str = Field(min_length=1, max_length=1000)
    display_name: str = Field(min_length=1, max_length=300)
    media_type: str = Field(min_length=1, max_length=200)
    size_bytes: int = Field(ge=0, le=5_000_000_000)
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
    schema_name: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataUploadRequest(ContractModel):
    display_name: str = Field(min_length=1, max_length=300)
    media_type: str = Field(min_length=1, max_length=200)
    size_bytes: int = Field(ge=1, le=5_000_000_000)
    content_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
    schema_name: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataUploadTicket(ContractModel):
    object: "DataObjectView"
    upload_url: str
    method: Literal["PUT"] = "PUT"
    required_headers: dict[str, str]
    expires_in_seconds: int


class DataDownloadTicket(ContractModel):
    object_id: UUID
    download_url: str
    expires_in_seconds: int


class DataObjectView(ContractModel):
    id: UUID
    tenant_id: UUID
    organization_id: UUID
    owner_user_id: UUID
    object_key: str
    display_name: str
    media_type: str
    size_bytes: int
    content_hash: str
    classification: str
    schema_name: str | None
    metadata: dict[str, Any] = Field(validation_alias="attributes", serialization_alias="metadata")
    status: str
    created_at: datetime
    updated_at: datetime


class DataGrantCreateRequest(ContractModel):
    grantee_type: Literal["USER", "AGENT", "ORGANIZATION"]
    grantee_id: str = Field(min_length=1, max_length=200)
    purposes: list[str] = Field(min_length=1)
    permissions: list[Literal["READ", "USE_IN_CONTEXT"]] = Field(min_length=1)
    expires_at: datetime | None = None


DataUploadTicket.model_rebuild()
