from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PurchaseOrderLineCreate(ContractModel):
    sku: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: Decimal = Field(gt=0)
    tax_rate: Decimal = Field(ge=0, le=100)


class PurchaseOrderCreate(ContractModel):
    po_number: str = Field(pattern=r"^[A-Z0-9][A-Z0-9/-]{2,79}$")
    buyer_id: str = Field(min_length=1, max_length=80)
    supplier_business_id: str = Field(min_length=1, max_length=80)
    order_date: date
    expected_delivery_date: date | None = None
    currency: Literal["INR"] = "INR"
    payment_terms_days: int = Field(ge=0, le=180)
    lines: list[PurchaseOrderLineCreate] = Field(min_length=1, max_length=100)


class ReceiptLineCreate(ContractModel):
    purchase_order_line_id: str = Field(min_length=1, max_length=80)
    received_quantity: Decimal = Field(gt=0)
    accepted_quantity: Decimal = Field(ge=0)
    rejected_quantity: Decimal = Field(ge=0)
    discrepancy: str | None = Field(default=None, max_length=240)


class ReceiptCreate(ContractModel):
    receipt_number: str = Field(pattern=r"^[A-Z0-9][A-Z0-9/-]{2,79}$")
    purchase_order_id: str = Field(min_length=1, max_length=80)
    delivery_reference: str = Field(min_length=1, max_length=100)
    receipt_type: Literal["GOODS", "SERVICE"] = "GOODS"
    posting_date: date
    receiver_token: str = Field(min_length=1, max_length=80)
    lines: list[ReceiptLineCreate] = Field(min_length=1, max_length=100)


class AcceptanceCreate(ContractModel):
    accepted_amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    actor: str = Field(min_length=1, max_length=100)


class DisputeCreate(ContractModel):
    reason: str = Field(min_length=3, max_length=500)
    actor: str = Field(min_length=1, max_length=100)


class GSTAggregate(ContractModel):
    type: str
    id: str
    version: int = Field(ge=1)


class GSTEventEnvelope(ContractModel):
    event_id: str = Field(min_length=1, max_length=80)
    event_type: Literal["invoice.registered", "invoice.cancelled"]
    schema_version: Literal["1.0"]
    source_application: Literal["xyena-demo-gst"]
    tenant_id: str
    aggregate: GSTAggregate
    data: dict[str, Any]
    correlation_id: str
    occurred_at: datetime
    signature: str | None = None


class GSTInvoiceSnapshot(ContractModel):
    id: str
    tenant_id: str
    invoice_number: str
    seller_gstin: str
    buyer_gstin: str
    purchase_order_id: str | None = None
    invoice_date: date
    currency: Literal["INR"] = "INR"
    total_invoice_value: Decimal = Field(gt=0)
    status: Literal["REGISTERED", "CANCELLED"]
    irn: str | None = None
    version: int = Field(ge=1)
    source_document_hash: str
