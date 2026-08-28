from datetime import date
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from .security import verify_runtime_scope
from .service import bank_service

mcp = MCPServer("xyena-synthetic-bank-aa")


@mcp.tool(name="aa.create_consent")
async def aa_create_consent(account_tokens: list[str], information_types: list[str],
                            valid_days: int, client_idempotency_key: str,
                            ctx: Context) -> dict[str, Any]:
    return await bank_service.create_consent(
        verify_runtime_scope(ctx, "bank.aa.create_consent"), account_tokens,
        information_types, valid_days, client_idempotency_key)


@mcp.tool(name="aa.get_consent")
async def aa_get_consent(consent_id: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.get_consent(
        verify_runtime_scope(ctx, "bank.aa.get_consent"), consent_id)


@mcp.tool(name="aa.revoke_consent")
async def aa_revoke_consent(consent_id: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.revoke_consent(
        verify_runtime_scope(ctx, "bank.aa.revoke_consent"), consent_id)


@mcp.tool(name="aa.fetch_information")
async def aa_fetch_information(consent_id: str, information_type: str,
                               account_token: str, client_idempotency_key: str,
                               ctx: Context, from_date: date | None = None,
                               to_date: date | None = None) -> dict[str, Any]:
    return await bank_service.fetch_information(
        verify_runtime_scope(ctx, "bank.aa.fetch_information"), consent_id,
        information_type, account_token, client_idempotency_key, from_date, to_date)


@mcp.tool(name="accounts.list")
async def accounts_list(ctx: Context) -> dict[str, Any]:
    return await bank_service.list_accounts(verify_runtime_scope(ctx, "bank.accounts.list"))


@mcp.tool(name="accounts.get")
async def accounts_get(account_token: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.get_account(
        verify_runtime_scope(ctx, "bank.accounts.get"), account_token)


@mcp.tool(name="accounts.get_balance")
async def accounts_get_balance(account_token: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.get_balance(
        verify_runtime_scope(ctx, "bank.accounts.get_balance"), account_token)


@mcp.tool(name="transactions.list")
async def transactions_list(account_token: str, from_date: date, to_date: date,
                            ctx: Context, limit: int = 50) -> dict[str, Any]:
    return await bank_service.list_transactions(
        verify_runtime_scope(ctx, "bank.transactions.list"), account_token,
        from_date, to_date, limit)


@mcp.tool(name="beneficiaries.verify")
async def beneficiaries_verify(beneficiary_token: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.verify_beneficiary(
        verify_runtime_scope(ctx, "bank.beneficiaries.verify"), beneficiary_token)


@mcp.tool(name="limits.get")
async def limits_get(account_token: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.get_limits(
        verify_runtime_scope(ctx, "bank.limits.get"), account_token)


@mcp.tool(name="transfers.prepare")
async def transfers_prepare(source_account_token: str, beneficiary_token: str,
                            amount: str, currency: str, rail: str,
                            client_idempotency_key: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.prepare_transfer(
        verify_runtime_scope(ctx, "bank.transfers.prepare"), source_account_token,
        beneficiary_token, amount, currency, rail, client_idempotency_key)


@mcp.tool(name="transfers.execute")
async def transfers_execute(proposed_action_id: str, canonical_action_hash: str,
                            execution_id: str,
                            ctx: Context) -> dict[str, Any]:
    return await bank_service.execute_transfer(
        verify_runtime_scope(ctx, "bank.transfers.execute"), proposed_action_id,
        canonical_action_hash, execution_id)


@mcp.tool(name="transfers.get_status")
async def transfers_get_status(proposed_action_id: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.transfer_status(
        verify_runtime_scope(ctx, "bank.transfers.get_status"), proposed_action_id)


@mcp.tool(name="beneficiaries.prepare_change")
async def beneficiaries_prepare_change(beneficiary_token: str, owner_name: str,
                                       masked_account: str, bank_name: str,
                                       currency: str, client_idempotency_key: str,
                                       ctx: Context) -> dict[str, Any]:
    return await bank_service.prepare_beneficiary_change(
        verify_runtime_scope(ctx, "bank.beneficiaries.prepare_change"), beneficiary_token,
        owner_name, masked_account, bank_name, currency, client_idempotency_key)


@mcp.tool(name="beneficiaries.execute_change")
async def beneficiaries_execute_change(change_id: str, canonical_action_hash: str,
                                       ctx: Context) -> dict[str, Any]:
    return await bank_service.execute_beneficiary_change(
        verify_runtime_scope(ctx, "bank.beneficiaries.execute_change"), change_id,
        canonical_action_hash)


@mcp.tool(name="reversals.prepare")
async def reversals_prepare(transfer_execution_id: str, amount: str, reason: str,
                            client_idempotency_key: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.prepare_reversal(
        verify_runtime_scope(ctx, "bank.reversals.prepare"), transfer_execution_id,
        amount, reason, client_idempotency_key)


@mcp.tool(name="reversals.execute")
async def reversals_execute(reversal_id: str, canonical_action_hash: str,
                            reviewer_approval_id: str,
                            ctx: Context) -> dict[str, Any]:
    return await bank_service.execute_reversal(
        verify_runtime_scope(ctx, "bank.reversals.execute"), reversal_id,
        canonical_action_hash, reviewer_approval_id)


@mcp.tool(name="holds.place")
async def holds_place(account_token: str, amount: str, currency: str,
                      client_idempotency_key: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.place_hold(
        verify_runtime_scope(ctx, "bank.holds.place"), account_token, amount,
        currency, client_idempotency_key)


@mcp.tool(name="holds.release")
async def holds_release(hold_id: str, ctx: Context) -> dict[str, Any]:
    return await bank_service.release_hold(
        verify_runtime_scope(ctx, "bank.holds.release"), hold_id)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/", stateless_http=True, json_response=True)
