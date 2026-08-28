from decimal import Decimal

from .database import session
from .models import LedgerAccount

DEMO_TENANT_ID = "00000000-0000-4000-8000-000000000101"
DEMO_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000301"
DEMO_USER_ID = "00000000-0000-4000-8000-000000000201"


async def seed_demo_data() -> None:
    async with session() as db:
        if await db.get(LedgerAccount, "ledger_cash_clearing") is not None:
            return
        db.add_all([
            LedgerAccount(account_id="ledger_cash_clearing", tenant_id=DEMO_TENANT_ID,
                          code="1010", name="Cash clearing", account_type="ASSET",
                          normal_side="DEBIT", currency="INR", balance=Decimal("2500000.00")),
            LedgerAccount(account_id="ledger_loan_receivable", tenant_id=DEMO_TENANT_ID,
                          code="1210", name="Loan receivable", account_type="ASSET",
                          normal_side="DEBIT", currency="INR", balance=Decimal("0.00")),
            LedgerAccount(account_id="ledger_funder_payable", tenant_id=DEMO_TENANT_ID,
                          code="2010", name="Funder payable", account_type="LIABILITY",
                          normal_side="CREDIT", currency="INR", balance=Decimal("0.00")),
            LedgerAccount(account_id="ledger_disbursement_control", tenant_id=DEMO_TENANT_ID,
                          code="9010", name="Disbursement control", account_type="CONTROL",
                          normal_side="DEBIT", currency="INR", balance=Decimal("0.00")),
        ])
