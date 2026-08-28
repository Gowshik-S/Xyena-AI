from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings

from .security import verify_runtime_scope
from .service import ledger_service

mcp = MCPServer("xyena-ledger-payment-operations")


@mcp.tool(name="accounts.get_balance")
async def accounts_get_balance(account_id: str, ctx: Context) -> dict[str, Any]:
    return await ledger_service.account_balance(
        verify_runtime_scope(ctx, "ledger.accounts.get_balance"), account_id)


@mcp.tool(name="journals.get")
async def journals_get(journal_id: str, ctx: Context) -> dict[str, Any]:
    return await ledger_service.get_journal(
        verify_runtime_scope(ctx, "ledger.journals.get"), journal_id)


@mcp.tool(name="payments.get_status")
async def payments_get_status(payment_id: str, ctx: Context) -> dict[str, Any]:
    return await ledger_service.payment_status(
        verify_runtime_scope(ctx, "ledger.payments.get_status"), payment_id)


@mcp.tool(name="reconciliation.get")
async def reconciliation_get(payment_id: str, ctx: Context) -> dict[str, Any]:
    return await ledger_service.reconciliation(
        verify_runtime_scope(ctx, "ledger.reconciliation.get"), payment_id)


@mcp.tool(name="disbursements.prepare")
async def disbursements_prepare(financing_case_id: str, source_account_token: str,
                                beneficiary_token: str, amount: str, currency: str,
                                rail: str, client_idempotency_key: str,
                                ctx: Context) -> dict[str, Any]:
    return await ledger_service.prepare_disbursement(
        verify_runtime_scope(ctx, "ledger.disbursements.prepare"), financing_case_id,
        source_account_token, beneficiary_token, amount, currency, rail,
        client_idempotency_key)


@mcp.tool(name="disbursements.execute")
async def disbursements_execute(journal_id: str, canonical_action_hash: str,
                                bank_proposed_action_id: str, bank_action_hash: str,
                                bank_execution_id: str, ctx: Context) -> dict[str, Any]:
    return await ledger_service.execute_disbursement(
        verify_runtime_scope(ctx, "ledger.disbursements.execute"), journal_id,
        canonical_action_hash, bank_proposed_action_id,
        bank_action_hash, bank_execution_id)


@mcp.tool(name="reversals.prepare")
async def reversals_prepare(original_journal_id: str, reason: str,
                            client_idempotency_key: str, ctx: Context) -> dict[str, Any]:
    return await ledger_service.prepare_reversal(
        verify_runtime_scope(ctx, "ledger.reversals.prepare"), original_journal_id,
        reason, client_idempotency_key)


@mcp.tool(name="reversals.execute")
async def reversals_execute(journal_id: str, canonical_action_hash: str,
                            reviewer_approval_id: str,
                            ctx: Context) -> dict[str, Any]:
    return await ledger_service.execute_reversal(
        verify_runtime_scope(ctx, "ledger.reversals.execute"), journal_id,
        canonical_action_hash, reviewer_approval_id)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "ledger-payment:8096",
            "ledger.gowshik.in",
            "localhost:8096",
            "127.0.0.1:8096",
        ],
        allowed_origins=["https://ledger.gowshik.in"],
    ),
)
