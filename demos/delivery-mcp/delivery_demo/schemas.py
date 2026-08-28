from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Gstin = Annotated[str, StringConstraints(pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-fA-F0-9]{64}$")]
PositiveQuantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=3)]
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Address(ContractModel):
    name: NonBlank
    address: NonBlank
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")] | None = None


class DeliveryItemCreate(ContractModel):
    po_line_id: NonBlank
    invoice_line_id: str | None = None
    sku: NonBlank
    description: NonBlank
    unit: NonBlank
    ordered_quantity: PositiveQuantity
    supported_unit_value: Money


class DeliveryCreate(ContractModel):
    delivery_number: NonBlank
    purchase_order_id: NonBlank
    invoice_id: str | None = None
    invoice_number: str | None = None
    seller_business_id: NonBlank
    seller_gstin: Gstin
    buyer_id: NonBlank
    buyer_gstin: Gstin
    ship_from: Address
    ship_to: Address
    expected_delivery_date: date | None = None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] = "INR"
    declared_value: Money
    items: Annotated[list[DeliveryItemCreate], Field(min_length=1, max_length=250)]

    @model_validator(mode="after")
    def validate_lines_and_value(self) -> "DeliveryCreate":
        skus = [item.sku for item in self.items]
        po_lines = [item.po_line_id for item in self.items]
        if len(set(skus)) != len(skus) or len(set(po_lines)) != len(po_lines):
            raise ValueError("Each SKU and purchase-order line must occur exactly once per delivery.")
        calculated = sum(
            (item.ordered_quantity * item.supported_unit_value for item in self.items),
            Decimal("0"),
        ).quantize(Decimal("0.01"))
        if calculated != self.declared_value:
            raise ValueError(f"Declared value must equal the delivery line total ({calculated}).")
        return self


class DispatchRequest(ContractModel):
    carrier_id: NonBlank
    item_quantities: dict[str, PositiveQuantity]


class TransitEventRequest(ContractModel):
    event_type: Literal["IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERY_DELAYED", "DELIVERY_RESUMED"]
    location: Address | None = None
    occurred_at: datetime | None = None
    notes: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("occurred_at must include a UTC offset.")
        return value


class DeliveryAttemptRequest(ContractModel):
    success: bool
    item_quantities: dict[str, Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=3)]] = Field(default_factory=dict)
    failure_reason: Annotated[str, Field(min_length=3, max_length=240)] | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "DeliveryAttemptRequest":
        if self.success and not self.item_quantities:
            raise ValueError("A successful attempt requires delivered item quantities.")
        if not self.success and not self.failure_reason:
            raise ValueError("A failed attempt requires a failure reason.")
        return self


class ProofCreate(ContractModel):
    proof_type: Literal["SIGNATURE", "PHOTO", "OTP", "DOCUMENT"]
    restricted_object_key: NonBlank
    content_hash: Sha256
    mime_type: NonBlank
    recipient_token: str | None = None
    recipient_role: str | None = None
    security_flags: list[str] = Field(default_factory=list)


class ProofReview(ContractModel):
    verified: bool
    rejection_reason: Annotated[str, Field(min_length=3, max_length=240)] | None = None

    @model_validator(mode="after")
    def validate_rejection(self) -> "ProofReview":
        if not self.verified and not self.rejection_reason:
            raise ValueError("Rejected proof requires a rejection reason.")
        return self


class ItemAcceptance(ContractModel):
    sku: NonBlank
    accepted_quantity: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=3)]
    rejected_quantity: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=3)]
    reason: Annotated[str, Field(max_length=240)] | None = None


class AcceptanceCreate(ContractModel):
    items: Annotated[list[ItemAcceptance], Field(min_length=1)]
    reason: Annotated[str, Field(max_length=240)] | None = None


class CancellationRequest(ContractModel):
    reason: Annotated[str, Field(min_length=3, max_length=240)]


class CorrectionCreate(ContractModel):
    correction_type: Literal["IDENTITY", "REFERENCE", "TRACKING", "ADDRESS"]
    proposed_changes: dict[str, str]
    reason: Annotated[str, Field(min_length=3, max_length=240)]


class CorrectionReview(ContractModel):
    approve: bool
    reason: Annotated[str, Field(max_length=240)] | None = None


class ExternalAggregate(ContractModel):
    type: Literal["purchase_order", "invoice", "business"]
    id: NonBlank
    version: Annotated[int, Field(gt=0)]


class ExternalEventEnvelope(ContractModel):
    schema_version: Literal["1.0"]
    event_id: NonBlank
    event_type: Literal["purchase_order.cancelled", "invoice.cancelled", "business.updated"]
    source_application: NonBlank
    tenant_id: NonBlank
    occurred_at: datetime
    correlation_id: NonBlank
    aggregate: ExternalAggregate
    data: dict[str, object] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_event_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a UTC offset.")
        return value


class FulfilmentClaim(ContractModel):
    purchase_order_id: NonBlank
    invoice_id: NonBlank
    po_line_id: str | None = None
    invoice_line_id: str | None = None
    sku: str | None = None
    claimed_quantity: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=3)]
    claimed_unit_value: Money

    @model_validator(mode="after")
    def require_line_identity(self) -> "FulfilmentClaim":
        if not any((self.po_line_id, self.invoice_line_id, self.sku)):
            raise ValueError("po_line_id, invoice_line_id, or sku is required.")
        return self
