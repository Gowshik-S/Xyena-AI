from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Account(Base):
    __tablename__ = "accounts"

    account_token: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    masked_number: Mapped[str] = mapped_column(String(40), nullable=False)
    account_type: Mapped[str] = mapped_column(String(40), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    per_transfer_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_token: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    booked_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    beneficiary_token: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    owner_name: Mapped[str] = mapped_column(String(160), nullable=False)
    masked_account: Mapped[str] = mapped_column(String(40), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(160), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    verified: Mapped[bool] = mapped_column(nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")


class Consent(Base):
    __tablename__ = "consents"

    consent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    purpose_prefix: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PreparedTransfer(Base):
    __tablename__ = "prepared_transfers"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    proposed_action_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_account_token: Mapped[str] = mapped_column(String(80), nullable=False)
    beneficiary_token: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rail: Mapped[str] = mapped_column(String(60), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_action_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    call_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AAConsent(Base):
    __tablename__ = "aa_consents"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    consent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    account_tokens: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    information_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinancialInformationRequest(Base):
    __tablename__ = "financial_information_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    request_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    consent_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    information_type: Mapped[str] = mapped_column(String(50), nullable=False)
    account_token: Mapped[str] = mapped_column(String(80), nullable=False)
    from_date: Mapped[date | None] = mapped_column(Date)
    to_date: Mapped[date | None] = mapped_column(Date)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_receipt_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TransferExecution(Base):
    __tablename__ = "transfer_executions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "execution_id"),
        UniqueConstraint("tenant_id", "guardian_call_id"),
        UniqueConstraint("tenant_id", "proposed_action_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    proposed_action_id: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_action_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    guardian_decision_id: Mapped[str] = mapped_column(String(100), nullable=False)
    guardian_call_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    bank_reference: Mapped[str | None] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountHold(Base):
    __tablename__ = "account_holds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key"),
        UniqueConstraint("tenant_id", "guardian_call_id"),
    )

    hold_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    account_token: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    guardian_call_id: Mapped[str] = mapped_column(String(36), nullable=False)
    release_guardian_call_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PreparedBeneficiaryChange(Base):
    __tablename__ = "prepared_beneficiary_changes"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    change_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    beneficiary_token: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_owner_name: Mapped[str] = mapped_column(String(160), nullable=False)
    requested_masked_account: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_bank_name: Mapped[str] = mapped_column(String(160), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_action_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    guardian_call_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PreparedReversal(Base):
    __tablename__ = "prepared_reversals"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    reversal_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    transfer_execution_id: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_action_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_approval_id: Mapped[str | None] = mapped_column(String(100))
    guardian_call_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    bank_reference: Mapped[str | None] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BankOutboxEvent(Base):
    __tablename__ = "bank_outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(60), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
