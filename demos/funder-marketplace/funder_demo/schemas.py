from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ApplicationRequest(ContractModel):
    case_id: str
    msme_id: str
    msme_name: str
    receivable_id: str
    requested_amount: Decimal = Field(gt=0)
    currency: Literal["INR"] = "INR"
    tenor_days: int = Field(ge=7, le=180)
    region: str
    industry: str
    evidence_receipt_ids: list[str] = Field(min_length=1)
    exposure_snapshot_reference: str
    exposure_amount: Decimal = Field(ge=0)


class ReviewRequest(ContractModel):
    decision: Literal["APPROVE", "DECLINE"]
    actor: str
    reason: str


class OfferRequest(ContractModel):
    program_id: str
    approved_amount: Decimal = Field(gt=0)
    advance_rate: Decimal = Field(gt=0, le=100)
    annual_rate: Decimal = Field(gt=0, le=100)
    fee_amount: Decimal = Field(ge=0)
    tenor_days: int = Field(ge=7, le=180)
    repayment_terms: str
    conditions: list[str] = Field(default_factory=list)
    expires_at: datetime
    actor: str


class ReserveRequest(ContractModel):
    amount: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=120)
    expires_at: datetime


class ReleaseRequest(ContractModel):
    reason: str
    actor: str


class CommitmentPrepareRequest(ContractModel):
    destination_token: str = Field(min_length=8, max_length=140)


class CommitmentConfirmRequest(ContractModel):
    guardian_authorization_id: str = Field(min_length=8)
    action_hash: str = Field(min_length=64, max_length=64)
    execution_reference: str = Field(min_length=6)


class ProgramTransitionRequest(ContractModel):
    action: Literal["ACTIVATE", "SUSPEND", "CLOSE"]
    actor: str
    reason: str


class ExternalEventEnvelope(ContractModel):
    event_id: str
    event_type: Literal[
        "commitment.disbursed",
        "commitment.execution_failed",
        "commitment.settled",
    ]
    schema_version: Literal["1.0"]
    source_application: Literal["xyena-demo-bank", "xyena-demo-ledger"]
    tenant_id: str
    aggregate: dict[str, Any]
    data: dict[str, Any]
    correlation_id: str
    occurred_at: datetime

