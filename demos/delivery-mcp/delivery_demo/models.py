from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    delivery_number: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    purchase_order_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    seller_business_id: Mapped[str] = mapped_column(String(80), nullable=False)
    seller_gstin: Mapped[str] = mapped_column(String(80), nullable=False)
    buyer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    buyer_gstin: Mapped[str] = mapped_column(String(80), nullable=False)
    carrier_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ship_from: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    ship_to: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    dispatch_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    declared_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    verified_delivered_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    exception_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), server_onupdate=func.now())
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)


class DeliveryItem(Base):
    __tablename__ = "delivery_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    po_line_id: Mapped[str] = mapped_column(String(80), nullable=False)
    invoice_line_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    dispatched_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    delivered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    supported_unit_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_channel_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prior_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class ProofOfDelivery(Base):
    __tablename__ = "proofs_of_delivery"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    proof_type: Mapped[str] = mapped_column(String(80), nullable=False)  # SIGNATURE, PHOTO, OTP, etc.
    restricted_object_key: Mapped[str] = mapped_column(String(240), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    recipient_token: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recipient_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), nullable=False)  # CAPTURED, PENDING_VERIFICATION, VERIFIED, REJECTED
    verification_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verifier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    replacement_link: Mapped[str | None] = mapped_column(String(240), nullable=True)
    security_flags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON string array


class BuyerAcceptance(Base):
    __tablename__ = "buyer_acceptances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(nullable=False)
    buyer_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # ACCEPTED, PARTIALLY_ACCEPTED, REJECTED
    accepted_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    item_level_acceptance: Mapped[str] = mapped_column(Text, nullable=False)  # JSON snapshot string
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DeliveryCorrection(Base):
    __tablename__ = "delivery_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    aggregate_version: Mapped[int] = mapped_column(nullable=False)
    correction_type: Mapped[str] = mapped_column(String(80), nullable=False)
    proposed_changes: Mapped[str] = mapped_column(Text, nullable=False)  # JSON proposed modifications
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    requester: Mapped[str] = mapped_column(String(80), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")  # PENDING, APPROVED, REJECTED
    applied_version: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")  # PENDING, APPROVED, REJECTED


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    application_id: Mapped[str] = mapped_column(String(80), nullable=False, default="xyena-demo-delivery")
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(40), nullable=False)  # USER, SERVICE, AGENT, SYSTEM
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON detail string
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(10), nullable=False, default="1.0")
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON payload
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (UniqueConstraint("source_application", "event_id"),)

    source_application: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # RECEIVED, PROCESSED, REJECTED, FAILED
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
