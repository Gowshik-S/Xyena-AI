from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Enterprise(Base):
    __tablename__ = "enterprises"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trade_name: Mapped[str] = mapped_column(String(160), nullable=False)
    primary_gstin: Mapped[str] = mapped_column(String(15), nullable=False, unique=True)
    declared_classification: Mapped[str] = mapped_column(String(40), nullable=False)
    calculated_classification: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_classification: Mapped[str] = mapped_column(String(40), nullable=False)
    classification_provenance: Mapped[str] = mapped_column(String(40), nullable=False)
    classification_as_of: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EnterpriseMembership(Base):
    __tablename__ = "enterprise_memberships"
    __table_args__ = (UniqueConstraint("user_id", "enterprise_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    enterprise_id: Mapped[str] = mapped_column(
        ForeignKey("enterprises.id"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")


class BrowserSession(Base):
    __tablename__ = "browser_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    enterprise_id: Mapped[str] = mapped_column(
        ForeignKey("enterprises.id"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Taxpayer(Base):
    __tablename__ = "taxpayers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    enterprise_id: Mapped[str] = mapped_column(
        ForeignKey("enterprises.id"), nullable=False, index=True
    )
    gstin: Mapped[str] = mapped_column(String(15), nullable=False, unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trade_name: Mapped[str] = mapped_column(String(160), nullable=False)
    taxpayer_type: Mapped[str] = mapped_column(String(30), nullable=False, default="REGULAR")
    registration_status: Mapped[str] = mapped_column(String(30), nullable=False)
    registration_date: Mapped[date] = mapped_column(Date, nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    registered_address: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ClassificationSnapshot(Base):
    __tablename__ = "msme_classification_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    enterprise_id: Mapped[str] = mapped_column(
        ForeignKey("enterprises.id"), nullable=False, index=True
    )
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    investment_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    annual_turnover: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    declared_classification: Mapped[str] = mapped_column(String(40), nullable=False)
    calculated_classification: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_classification: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "financial_year", "invoice_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    enterprise_id: Mapped[str] = mapped_column(
        ForeignKey("enterprises.id"), nullable=False, index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    invoice_type: Mapped[str] = mapped_column(String(30), nullable=False, default="B2B")
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    seller_gstin: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    buyer_gstin: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    buyer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    purchase_order_id: Mapped[str | None] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    place_of_supply: Mapped[str] = mapped_column(String(2), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cess_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_invoice_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", index=True)
    irn: Mapped[str | None] = mapped_column(String(100), unique=True)
    ack_number: Mapped[str | None] = mapped_column(String(40))
    ack_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    source_document_hash: Mapped[str | None] = mapped_column(String(64))
    security_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (UniqueConstraint("invoice_id", "line_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    hsn_sac: Mapped[str] = mapped_column(String(12), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class InvoiceStatusHistory(Base):
    __tablename__ = "invoice_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    prior_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReturnSummary(Base):
    __tablename__ = "return_summaries"
    __table_args__ = (UniqueConstraint("enterprise_id", "period", "return_type", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    enterprise_id: Mapped[str] = mapped_column(
        ForeignKey("enterprises.id"), nullable=False, index=True
    )
    gstin: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    return_type: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    turnover: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    invoice_count: Mapped[int] = mapped_column(nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    aggregate_version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
