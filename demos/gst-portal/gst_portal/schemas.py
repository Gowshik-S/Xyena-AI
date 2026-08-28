from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(StrictModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class InvoiceLineCreate(StrictModel):
    description: str = Field(min_length=2, max_length=300)
    hsn_sac: str = Field(pattern=r"^[0-9]{4,8}$")
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit: str = Field(pattern=r"^[A-Z]{2,10}$")
    unit_price: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    gst_rate: Decimal = Field(ge=0, le=28, max_digits=5, decimal_places=2)


class InvoiceCreate(StrictModel):
    invoice_number: str = Field(pattern=r"^[A-Z0-9][A-Z0-9/-]{2,39}$")
    invoice_type: Literal["B2B", "CREDIT_NOTE", "DEBIT_NOTE", "EXPORT"] = "B2B"
    invoice_date: date
    buyer_gstin: str = Field(pattern=r"^[0-9A-Z]{15}$")
    buyer_name: str = Field(min_length=2, max_length=200)
    purchase_order_id: str | None = Field(default=None, max_length=80)
    place_of_supply: str = Field(pattern=r"^[0-9]{2}$")
    lines: list[InvoiceLineCreate] = Field(min_length=1, max_length=100)

    @field_validator("invoice_number", "buyer_gstin", mode="after")
    @classmethod
    def uppercase_identifiers(cls, value: str) -> str:
        return value.upper()


class TransitionRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=500)


class ClassificationReviewRequest(StrictModel):
    effective_classification: Literal[
        "MICRO", "SMALL", "MEDIUM", "OUTSIDE_MSME_LIMITS", "UNKNOWN"
    ]
    reason: str = Field(min_length=10, max_length=500)


class EnterpriseSwitchRequest(StrictModel):
    enterprise_id: str = Field(min_length=36, max_length=36)
