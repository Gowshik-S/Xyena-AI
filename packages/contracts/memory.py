from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .common import ContractModel


class MemoryCreateRequest(ContractModel):
    memory_type: Literal[
        "USER_PREFERENCE", "USER_PROFILE", "ORGANIZATION", "CASE", "SESSION_SUMMARY"
    ]
    content: str = Field(min_length=1, max_length=20_000)
    case_id: UUID | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    sensitivity: str = "CONFIDENTIAL"
    valid_until: datetime | None = None


class MemoryView(ContractModel):
    id: UUID
    memory_type: str
    content: str
    status: str
    confidence: float
    sensitivity: str
    provenance: dict[str, Any]
    case_id: UUID | None
    created_at: datetime
    valid_until: datetime | None


class MemorySearchRequest(ContractModel):
    query: str = Field(min_length=1, max_length=2000)
    memory_types: list[str] = Field(default_factory=list)
    case_id: UUID | None = None
    limit: int = Field(default=10, ge=1, le=50)

