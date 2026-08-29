import os
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

os.environ["BANK_DEMO_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["BANK_DEMO_MCP_TOKEN"] = "test-mcp-token-with-sufficient-entropy"  # noqa: S105
os.environ["BANK_DEMO_UI_TOKEN"] = "test-ui-token-with-sufficient-entropy"  # noqa: S105

from bank_demo.database import Base, engine, initialize_database, session  # noqa: E402
from bank_demo.main import app  # noqa: E402
from bank_demo.models import Account, LedgerEntry, Transaction, TransferExecution  # noqa: E402
from bank_demo.security import BankDemoSecurityError, RuntimeScope  # noqa: E402
from bank_demo.seed import (  # noqa: E402
    DEMO_ORGANIZATION_ID,
    DEMO_TENANT_ID,
    DEMO_USER_ID,
    seed_demo_data,
)
from bank_demo.service import bank_service  # noqa: E402


def scope(tool: str, *, authorized: bool = False) -> RuntimeScope:
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
        guardian_decision_id=str(uuid4()) if authorized else None,
        authorization_id=str(uuid4()) if authorized else None,
        authorization_consumed=authorized,
    )


@pytest.fixture(autouse=True)
async def reset_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await initialize_database()
    await seed_demo_data()


@pytest.mark.asyncio
async def test_guardian_authorized_execution_is_atomic_and_idempotent() -> None:
    idempotency_key = "case-1023-disbursement-1"
    prepared = await bank_service.prepare_transfer(
        scope("bank.transfers.prepare"),
        "acct_demo_operating",
        "ben_demo_verified",
        "75000.00",
        "INR",
        "DEMO_BANK_RAIL",
        idempotency_key,
    )

    with pytest.raises(BankDemoSecurityError):
        await bank_service.execute_transfer(
            scope("bank.transfers.execute"),
            prepared["proposed_action_id"],
            idempotency_key,
        )

    execution_scope = scope("bank.transfers.execute", authorized=True)
    result = await bank_service.execute_transfer(
        execution_scope,
        prepared["proposed_action_id"],
        idempotency_key,
    )
    replay = await bank_service.execute_transfer(
        execution_scope,
        prepared["proposed_action_id"],
        idempotency_key,
    )

    assert result["status"] == "SETTLED"
    assert result["execution_id"] == replay["execution_id"]
    assert result["reconciliation_required"] is False
    assert len(result["ledger"]) == 2
    assert {line["entry_type"] for line in result["ledger"]} == {"DEBIT", "CREDIT"}

    async with session() as db:
        account = await db.get(Account, "acct_demo_operating")
        assert account is not None
        assert account.available_balance == Decimal("742500.00")
        assert account.current_balance == Decimal("767500.00")
        execution_count = await db.scalar(select(func.count()).select_from(TransferExecution))
        transaction_count = await db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.category == "GUARDIAN_AUTHORIZED_TRANSFER")
        )
        ledger_count = await db.scalar(select(func.count()).select_from(LedgerEntry))
        assert execution_count == 1
        assert transaction_count == 1
        assert ledger_count == 2


@pytest.mark.asyncio
async def test_operations_summary_exposes_live_execution_and_ledger_state() -> None:
    idempotency_key = "case-2048-disbursement-1"
    prepared = await bank_service.prepare_transfer(
        scope("bank.transfers.prepare"),
        "acct_demo_operating",
        "ben_demo_verified",
        "12500.00",
        "INR",
        "DEMO_BANK_RAIL",
        idempotency_key,
    )
    await bank_service.execute_transfer(
        scope("bank.transfers.execute", authorized=True),
        prepared["proposed_action_id"],
        idempotency_key,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://bank.test"
    ) as client:
        response = await client.get(
            "/api/v1/demo/summary",
            headers={"X-Demo-Token": "test-ui-token-with-sufficient-entropy"},
        )

    assert response.status_code == 200
    assert "bank_demo_session" in response.cookies
    payload = response.json()
    assert payload["execution_available"] is True
    assert payload["mcp"]["tool_count"] == 8
    assert payload["settled_transfer_count"] == 1
    assert payload["settled_transfer_volume"] == "12500.00"
    assert payload["prepared_actions"][0]["execution"]["status"] == "SETTLED"
    assert len(payload["ledger_entries"]) == 2
