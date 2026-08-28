from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(StrictModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class BusinessCreate(StrictModel):
    registry_number: str = Field(pattern=r"^[A-Z0-9/-]{6,40}$")
    business_id: str = Field(pattern=r"^[a-z0-9_-]{6,80}$")
    business_type: Literal["PROPRIETORSHIP", "PARTNERSHIP", "LLP", "COMPANY", "OTHER"]
    legal_name: str = Field(min_length=3, max_length=200)
    trade_name: str | None = Field(default=None, max_length=160)
    incorporation_date: date
    registered_state_code: str = Field(pattern=r"^[0-9]{2}$")
    address_line1: str = Field(min_length=5, max_length=180)
    city: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(pattern=r"^[0-9]{6}$")
    industry_code: str | None = Field(default=None, max_length=20)
    msme_classification: Literal["MICRO", "SMALL", "MEDIUM"] | None = None
    primary_gstin: str | None = Field(default=None, pattern=r"^[0-9A-Z]{15}$")

    @field_validator("registry_number", "primary_gstin", mode="before")
    @classmethod
    def uppercase_identifiers(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


class StatusTransition(StrictModel):
    target_status: Literal["ACTIVE", "SUSPENDED", "DISSOLVED", "REJECTED"]
    reason: str = Field(min_length=10, max_length=500)


class ChangeRequestCreate(StrictModel):
    target_version: int = Field(ge=1)
    legal_name: str | None = Field(default=None, min_length=3, max_length=200)
    trade_name: str | None = Field(default=None, max_length=160)
    registered_address: dict[str, str] | None = None
    industry_code: str | None = Field(default=None, max_length=20)
    msme_classification: Literal["MICRO", "SMALL", "MEDIUM"] | None = None
    primary_gstin: str | None = Field(default=None, pattern=r"^[0-9A-Z]{15}$")
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("primary_gstin", mode="before")
    @classmethod
    def uppercase_gstin(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


class ChangeDecision(StrictModel):
    decision_reason: str = Field(min_length=10, max_length=500)
