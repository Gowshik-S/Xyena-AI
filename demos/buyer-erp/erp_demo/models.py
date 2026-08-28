from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Counterparty(Base):
    __tablename__ = "counterparties"
    __table_args__ = (UniqueConstraint("tenant_id", "business_id"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    business_id: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(180), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    relationship_status: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(nullable=False, default=30)
    approved_address: Mapped[str] = mapped_column(String(300), nullable=False)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "po_number"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    po_number: Mapped[str] = mapped_column(String(80), nullable=False)
    buyer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    supplier_business_id: Mapped[str] = mapped_column(String(80), nullable=False)
    buyer_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    seller_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (UniqueConstraint("purchase_order_id", "line_number"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    purchase_order_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)


class GoodsServiceReceipt(Base):
    __tablename__ = "goods_service_receipts"
    __table_args__ = (UniqueConstraint("tenant_id", "receipt_number"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    receipt_number: Mapped[str] = mapped_column(String(80), nullable=False)
    purchase_order_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    delivery_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    receipt_type: Mapped[str] = mapped_column(String(30), nullable=False, default="GOODS")
    posting_date: Mapped[date] = mapped_column(Date, nullable=False)
    receiver_token: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    accepted_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rejected_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReceiptLine(Base):
    __tablename__ = "receipt_lines"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    receipt_id: Mapped[str] = mapped_column(
        ForeignKey("goods_service_receipts.id"), nullable=False, index=True
    )
    purchase_order_line_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_order_lines.id"), nullable=False
    )
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    accepted_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discrepancy: Mapped[str | None] = mapped_column(String(240))


class SupplierInvoice(Base):
    __tablename__ = "supplier_invoices"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    seller_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    buyer_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    purchase_order_id: Mapped[str | None] = mapped_column(String(80), index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    claimed_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    gst_status: Mapped[str] = mapped_column(String(30), nullable=False)
    irn_token: Mapped[str | None] = mapped_column(String(100))
    source_version: Mapped[int] = mapped_column(nullable=False)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    matching_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InvoiceMatch(Base):
    __tablename__ = "invoice_matches"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invoice_id: Mapped[str] = mapped_column(
        ForeignKey("supplier_invoices.id"), nullable=False, unique=True
    )
    purchase_order_id: Mapped[str | None] = mapped_column(String(80), index=True)
    receipt_id: Mapped[str | None] = mapped_column(String(80))
    po_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    receipt_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    invoice_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    supported_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tolerance_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=1)
    discrepancies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InvoiceAcceptance(Base):
    __tablename__ = "invoice_acceptances"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    match_id: Mapped[str] = mapped_column(
        ForeignKey("invoice_matches.id"), nullable=False, unique=True
    )
    accepted_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    match_version: Mapped[int] = mapped_column(nullable=False)


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
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
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
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
