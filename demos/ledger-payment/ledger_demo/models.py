from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    account_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    normal_side: Mapped[str] = mapped_column(String(6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    version: Mapped[int] = mapped_column(nullable=False, default=1)


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),
                      UniqueConstraint("tenant_id", "guardian_call_id"))
    journal_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    financing_case_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_debits: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_credits: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_action_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    guardian_call_id: Mapped[str | None] = mapped_column(String(36))
    guardian_decision_id: Mapped[str | None] = mapped_column(String(100))
    reversal_of_journal_id: Mapped[str | None] = mapped_column(String(80))
    reviewer_approval_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JournalLine(Base):
    __tablename__ = "journal_lines"
    line_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    journal_id: Mapped[str] = mapped_column(ForeignKey("journal_entries.journal_id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("ledger_accounts.account_id"))
    side: Mapped[str] = mapped_column(String(6), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)


class PaymentInstruction(Base):
    __tablename__ = "payment_instructions"
    __table_args__ = (UniqueConstraint("tenant_id", "client_idempotency_key"),)
    payment_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    journal_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    financing_case_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_account_token: Mapped[str] = mapped_column(String(80), nullable=False)
    beneficiary_token: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rail: Mapped[str] = mapped_column(String(60), nullable=False)
    client_idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    bank_proposed_action_id: Mapped[str | None] = mapped_column(String(80))
    bank_action_hash: Mapped[str | None] = mapped_column(String(128))
    bank_execution_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    bank_reference: Mapped[str | None] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SettlementReceipt(Base):
    __tablename__ = "settlement_receipts"
    receipt_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    bank_execution_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    bank_reference: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(128), nullable=False)


class ReconciliationRecord(Base):
    __tablename__ = "reconciliation_records"
    reconciliation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    journal_id: Mapped[str] = mapped_column(String(80), nullable=False)
    settlement_receipt_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    variance_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(String(500))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    call_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(60), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
