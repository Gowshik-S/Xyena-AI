from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from .database import session
from .models import Account, Beneficiary, Consent, Transaction

DEMO_TENANT_ID = "00000000-0000-4000-8000-000000000101"
DEMO_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000301"
DEMO_USER_ID = "00000000-0000-4000-8000-000000000201"


async def seed_demo_data() -> None:
    async with session() as db:
        if await db.get(Account, "acct_demo_operating") is not None:
            consent = await db.get(Consent, "consent_demo_active")
            if consent is not None:
                consent.valid_until = datetime.now(UTC) + timedelta(days=30)
            return
        db.add_all(
            [
                Account(
                    account_token="acct_demo_operating",
                    tenant_id=DEMO_TENANT_ID,
                    user_id=DEMO_USER_ID,
                    display_name="Synthetic Operating Account",
                    masked_number="XXXXXX4107",
                    account_type="CURRENT",
                    currency="INR",
                    current_balance=Decimal("842500.00"),
                    available_balance=Decimal("817500.00"),
                    per_transfer_limit=Decimal("250000.00"),
                    daily_limit=Decimal("500000.00"),
                    status="ACTIVE",
                ),
                Account(
                    account_token="acct_demo_reserve",
                    tenant_id=DEMO_TENANT_ID,
                    user_id=DEMO_USER_ID,
                    display_name="Synthetic Reserve Account",
                    masked_number="XXXXXX8821",
                    account_type="CURRENT",
                    currency="INR",
                    current_balance=Decimal("315000.00"),
                    available_balance=Decimal("315000.00"),
                    per_transfer_limit=Decimal("100000.00"),
                    daily_limit=Decimal("200000.00"),
                    status="ACTIVE",
                ),
                Beneficiary(
                    beneficiary_token="ben_demo_verified",
                    tenant_id=DEMO_TENANT_ID,
                    owner_name="Synthetic Supplies Private Limited",
                    masked_account="XXXXXX9004",
                    bank_name="XYENA Demonstration Bank",
                    currency="INR",
                    verified=True,
                    status="ACTIVE",
                ),
                Beneficiary(
                    beneficiary_token="ben_demo_unverified",
                    tenant_id=DEMO_TENANT_ID,
                    owner_name="Unverified Demo Counterparty",
                    masked_account="XXXXXX1120",
                    bank_name="XYENA Demonstration Bank",
                    currency="INR",
                    verified=False,
                    status="REVIEW_REQUIRED",
                ),
                Consent(
                    consent_id="consent_demo_active",
                    tenant_id=DEMO_TENANT_ID,
                    user_id=DEMO_USER_ID,
                    purpose_prefix="",
                    status="ACTIVE",
                    valid_until=datetime.now(UTC) + timedelta(days=30),
                ),
            ]
        )
        samples = [
            (
                -1,
                "CREDIT",
                "185000.00",
                "CUSTOMER_RECEIPT",
                "Synthetic buyer receipt",
                "DEMO-CR-1001",
            ),
            (
                -3,
                "DEBIT",
                "62500.00",
                "SUPPLIER_PAYMENT",
                "Synthetic inventory payment",
                "DEMO-DR-1002",
            ),
            (-7, "DEBIT", "28000.00", "PAYROLL", "Synthetic payroll batch", "DEMO-DR-1003"),
            (
                -12,
                "CREDIT",
                "96000.00",
                "CUSTOMER_RECEIPT",
                "Synthetic invoice settlement",
                "DEMO-CR-1004",
            ),
            (-18, "DEBIT", "14250.00", "UTILITIES", "Synthetic utilities payment", "DEMO-DR-1005"),
            (
                -26,
                "CREDIT",
                "210000.00",
                "CUSTOMER_RECEIPT",
                "Synthetic distributor receipt",
                "DEMO-CR-1006",
            ),
        ]
        namespace = UUID("00000000-0000-4000-8000-000000000999")
        for offset, direction, amount, category, description, reference in samples:
            db.add(
                Transaction(
                    id=str(uuid5(namespace, reference)),
                    account_token="acct_demo_operating",
                    booked_on=date.today() + timedelta(days=offset),
                    direction=direction,
                    amount=Decimal(amount),
                    currency="INR",
                    category=category,
                    description=description,
                    reference=reference,
                )
            )
