from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ApiProblem(ContractModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    code: str
    correlation_id: UUID
    errors: list[dict[str, Any]] = Field(default_factory=list)


class CursorPage(ContractModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


class HealthStatus(ContractModel):
    status: str
    service: str
    version: str
    checked_at: datetime


class AcceptedResponse(ContractModel):
    id: UUID
    status: str
    correlation_id: UUID

