import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

os.environ["BANK_DEMO_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["BANK_DEMO_MCP_TOKEN"] = "test-mcp-token-with-sufficient-entropy"  # noqa: S105
os.environ["BANK_DEMO_UI_TOKEN"] = "test-ui-token-with-sufficient-entropy"  # noqa: S105

from bank_demo.database import Base, engine, initialize_database, session  # noqa: E402
from bank_demo.models import Account, LedgerEntry, Transaction, TransferExecution  # noqa: E402
from bank_demo.security import RuntimeScope  # noqa: E402
from bank_demo.seed import (  # noqa: E402
    DEMO_ORGANIZATION_ID,
    DEMO_TENANT_ID,
    DEMO_USER_ID,
    seed_demo_data,
)
from bank_demo.service import bank_service  # noqa: E402


def scope(tool: str) -> RuntimeScope:
    return RuntimeScope(
        tenant_id=DEMO_TENANT_ID,
        organization_id=DEMO_ORGANIZATION_ID,
        user_id=DEMO_USER_ID,
        session_id=str(uuid4()),
        run_id=str(uuid4()),
        call_id=str(uuid4()),
        correlation_id=str(uuid4()),
        agent_name="xyena-supervisor",
        canonical_name=tool,
        purpose="Finance verified synthetic receivable INV-1023",
        request_hash=uuid4().hex * 2,
        guardian_decision_id=str(uuid4()),
        authorization_id=str(uuid4()),
        authorization_consumed=True,
    )


@pytest.fixture(autouse=True)
async def reset_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await initialize_database()
    await seed_demo_data()


@pytest.mark.asyncio
async def test_execution_posts_one_transfer_and_balanced_journal() -> None:
    prepared = await bank_service.prepare_transfer(
        scope("bank.transfers.prepare"),
        "acct_demo_operating",
        "ben_demo_verified",
        "75000.00",
        "INR",
        "DEMO_BANK_RAIL",
        "case-1023-disbursement-1",
    )
    execution_scope = scope("bank.transfers.execute")
    result = await bank_service.execute_transfer(
        execution_scope,
        prepared["proposed_action_id"],
        prepared["canonical_action_hash"],
        "execution-case-1023-1",
    )
    replay = await bank_service.execute_transfer(
        execution_scope,
        prepared["proposed_action_id"],
        prepared["canonical_action_hash"],
        "execution-case-1023-1",
    )

    assert result["status"] == "SETTLED"
    assert replay["execution_id"] == result["execution_id"]
    assert result["authorization_consumed"] is True
    assert result["ledger_balanced"] is True

    async with session() as db:
        account = await db.get(Account, "acct_demo_operating")
        assert account is not None
        assert account.available_balance == Decimal("742500.00")
        assert account.current_balance == Decimal("767500.00")
        assert await db.scalar(select(func.count()).select_from(TransferExecution)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.category == "GUARDIAN_PAYMENT")
            )
            == 1
        )
        ledger = (await db.scalars(select(LedgerEntry).order_by(LedgerEntry.line_number))).all()
        assert len(ledger) == 2
        assert {line.entry_type for line in ledger} == {"DEBIT", "CREDIT"}
        assert ledger[0].journal_id == ledger[1].journal_id == result["journal_id"]
        assert ledger[0].amount == ledger[1].amount == Decimal("75000.00")
