from datetime import date
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from .security import verify_runtime_scope
from .service import bank_service


mcp = MCPServer("xyena-synthetic-bank-demo")


@mcp.tool(name="accounts.list")
async def accounts_list(ctx: Context) -> dict[str, Any]:
    """List tokenized synthetic accounts in the signed tenant and user scope."""
    scope = verify_runtime_scope(ctx, "bank.accounts.list")
    return await bank_service.list_accounts(scope)


@mcp.tool(name="accounts.get_balance")
async def accounts_get_balance(account_token: str, ctx: Context) -> dict[str, Any]:
    """Read a synthetic current and available balance using an opaque account token."""
    scope = verify_runtime_scope(ctx, "bank.accounts.get_balance")
    return await bank_service.get_balance(scope, account_token)


@mcp.tool(name="transactions.list")
async def transactions_list(
    account_token: str,
    from_date: date,
    to_date: date,
    ctx: Context,
    limit: int = 50,
) -> dict[str, Any]:
    """List up to 100 synthetic transactions within a maximum 90-day window."""
    scope = verify_runtime_scope(ctx, "bank.transactions.list")
    return await bank_service.list_transactions(
        scope, account_token, from_date, to_date, limit
    )


@mcp.tool(name="beneficiaries.verify")
async def beneficiaries_verify(
    beneficiary_token: str, ctx: Context
) -> dict[str, Any]:
    """Return synthetic beneficiary verification evidence for an opaque token."""
    scope = verify_runtime_scope(ctx, "bank.beneficiaries.verify")
    return await bank_service.verify_beneficiary(scope, beneficiary_token)


@mcp.tool(name="limits.get")
async def limits_get(account_token: str, ctx: Context) -> dict[str, Any]:
    """Return synthetic account limits and explicitly report that execution is disabled."""
    scope = verify_runtime_scope(ctx, "bank.limits.get")
    return await bank_service.get_limits(scope, account_token)


@mcp.tool(name="transfers.prepare")
async def transfers_prepare(
    source_account_token: str,
    beneficiary_token: str,
    amount: str,
    currency: str,
    rail: str,
    client_idempotency_key: str,
    ctx: Context,
) -> dict[str, Any]:
    """Prepare and hash a synthetic transfer; this tool never executes money movement."""
    scope = verify_runtime_scope(ctx, "bank.transfers.prepare")
    return await bank_service.prepare_transfer(
        scope,
        source_account_token,
        beneficiary_token,
        amount,
        currency,
        rail,
        client_idempotency_key,
    )


@mcp.tool(name="transfers.get_status")
async def transfers_get_status(
    proposed_action_id: str, ctx: Context
) -> dict[str, Any]:
    """Read the status of a synthetic prepared action in the signed user scope."""
    scope = verify_runtime_scope(ctx, "bank.transfers.get_status")
    return await bank_service.transfer_status(scope, proposed_action_id)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/", stateless_http=True, json_response=True
)
