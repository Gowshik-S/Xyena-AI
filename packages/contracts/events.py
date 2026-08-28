from datetime import datetime
from typing import Any
from uuid import UUID

from .common import ContractModel


class EventEnvelope(ContractModel):
    event_id: UUID
    event_type: str
    schema_version: str = "1.0"
    source_application: str
    tenant_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    data: dict[str, Any]
    correlation_id: UUID
    occurred_at: datetime

