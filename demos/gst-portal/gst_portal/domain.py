import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditEvent, OutboxEvent


MONEY = Decimal("0.01")
THRESHOLD_VERSION = "INDIA_MSME_2025_04_01"
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z0-9]{10}[0-9A-Z][Z][0-9A-Z]$")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def financial_year(value: date) -> str:
    start = value.year if value.month >= 4 else value.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def classify_msme(investment: Decimal, turnover: Decimal) -> str:
    crore = Decimal("10000000")
    if investment <= Decimal("2.5") * crore and turnover <= Decimal("10") * crore:
        return "MICRO"
    if investment <= Decimal("25") * crore and turnover <= Decimal("100") * crore:
        return "SMALL"
    if investment <= Decimal("125") * crore and turnover <= Decimal("500") * crore:
        return "MEDIUM"
    return "OUTSIDE_MSME_LIMITS"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def calculate_line(
    *,
    quantity: Decimal,
    unit_price: Decimal,
    discount: Decimal,
    gst_rate: Decimal,
    intra_state: bool,
) -> dict[str, Decimal]:
    taxable = money(quantity * unit_price - discount)
    if taxable < 0:
        raise ValueError("A line discount cannot exceed its gross value.")
    tax = money(taxable * gst_rate / Decimal("100"))
    cgst = money(tax / 2) if intra_state else Decimal("0.00")
    sgst = money(tax - cgst) if intra_state else Decimal("0.00")
    igst = Decimal("0.00") if intra_state else tax
    return {
        "taxable_value": taxable,
        "cgst_amount": cgst,
        "sgst_amount": sgst,
        "igst_amount": igst,
        "total_value": money(taxable + tax),
    }


def record_change(
    db: AsyncSession,
    *,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    event_type: str,
    actor_type: str,
    actor_id: str,
    reason: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    correlation_id = str(uuid4())
    db.add(
        AuditEvent(
            id=str(uuid4()),
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            metadata_json=metadata or {},
        )
    )
    db.add(
        OutboxEvent(
            id=str(uuid4()),
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            event_type=event_type,
            payload={"id": aggregate_id, "version": aggregate_version},
            correlation_id=correlation_id,
        )
    )


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()
