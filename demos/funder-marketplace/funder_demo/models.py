from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


money = Numeric(18, 2)
rate = Numeric(9, 4)


class FunderInstitution(Base):
    __tablename__ = "funder_institutions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    institution_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    supported_currencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    supported_rails: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    settlement_account_token: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FundingProgram(Base):
    __tablename__ = "funding_programs"
    __table_args__ = (UniqueConstraint("tenant_id", "program_code"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    funder_id: Mapped[str] = mapped_column(ForeignKey("funder_institutions.id"), nullable=False)
    program_code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    product_type: Mapped[str] = mapped_column(String(60), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    minimum_amount: Mapped[Decimal] = mapped_column(money, nullable=False)
    maximum_amount: Mapped[Decimal] = mapped_column(money, nullable=False)
    total_capacity: Mapped[Decimal] = mapped_column(money, nullable=False)
    reserved_capacity: Mapped[Decimal] = mapped_column(money, nullable=False, default=0)
    committed_capacity: Mapped[Decimal] = mapped_column(money, nullable=False, default=0)
    advance_rate_maximum: Mapped[Decimal] = mapped_column(rate, nullable=False)
    tenor_minimum_days: Mapped[int] = mapped_column(nullable=False)
    tenor_maximum_days: Mapped[int] = mapped_column(nullable=False)
    pricing_model: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    eligible_regions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    eligible_industries: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    required_evidence_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    policy_version: Mapped[int] = mapped_column(nullable=False, default=1)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProgramRule(Base):
    __tablename__ = "program_rules"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("funding_programs.id"), nullable=False, index=True)
    rule_key: Mapped[str] = mapped_column(String(80), nullable=False)
    input_field: Mapped[str] = mapped_column(String(80), nullable=False)
    operator: Mapped[str] = mapped_column(String(30), nullable=False)
    comparison_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(nullable=False, default=1)


class FundingApplication(Base):
    __tablename__ = "funding_applications"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(80), nullable=False)
    msme_id: Mapped[str] = mapped_column(String(80), nullable=False)
    msme_name: Mapped[str] = mapped_column(String(180), nullable=False)
    receivable_id: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_amount: Mapped[Decimal] = mapped_column(money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    tenor_days: Mapped[int] = mapped_column(nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    industry: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_receipt_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    exposure_snapshot_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    exposure_amount: Mapped[Decimal] = mapped_column(money, nullable=False, default=0)
    eligibility_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FundingOffer(Base):
    __tablename__ = "funding_offers"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("funding_applications.id"), nullable=False)
    funder_id: Mapped[str] = mapped_column(ForeignKey("funder_institutions.id"), nullable=False)
    program_id: Mapped[str] = mapped_column(ForeignKey("funding_programs.id"), nullable=False)
    approved_amount: Mapped[Decimal] = mapped_column(money, nullable=False)
    advance_rate: Mapped[Decimal] = mapped_column(rate, nullable=False)
    annual_rate: Mapped[Decimal] = mapped_column(rate, nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(money, nullable=False)
    tenor_days: Mapped[int] = mapped_column(nullable=False)
    repayment_terms: Mapped[str] = mapped_column(String(240), nullable=False)
    conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    offer_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OfferReservation(Base):
    __tablename__ = "offer_reservations"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("funding_offers.id"), nullable=False)
    program_id: Mapped[str] = mapped_column(ForeignKey("funding_programs.id"), nullable=False)
    reserved_amount: Mapped[Decimal] = mapped_column(money, nullable=False)
    case_id: Mapped[str] = mapped_column(String(80), nullable=False)
    msme_id: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    release_reference: Mapped[str | None] = mapped_column(String(120))
    commit_reference: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FundingCommitment(Base):
    __tablename__ = "funding_commitments"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reservation_id: Mapped[str] = mapped_column(ForeignKey("offer_reservations.id"), nullable=False, unique=True)
    committed_amount: Mapped[Decimal] = mapped_column(money, nullable=False)
    guardian_authorization_id: Mapped[str | None] = mapped_column(String(120))
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_token: Mapped[str] = mapped_column(String(140), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    execution_reference: Mapped[str | None] = mapped_column(String(120))
    ledger_reference: Mapped[str | None] = mapped_column(String(120))
    settlement_status: Mapped[str] = mapped_column(String(40), nullable=False, default="PENDING")
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(60), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(60), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (UniqueConstraint("source_application", "event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_application: Mapped[str] = mapped_column(String(100), nullable=False)
    event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)

