from datetime import datetime
from decimal import Decimal
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings

from .schemas import (
    ApplicationRequest,
    CommitmentConfirmRequest,
    CommitmentPrepareRequest,
    ReleaseRequest,
    ReserveRequest,
)
from .security import RuntimeScope, verify_runtime_scope
from .service import funder_service


mcp = MCPServer("xyena-synthetic-funder-marketplace-demo")


def evidence_result(scope: RuntimeScope, kind: str, result: dict[str, Any]) -> dict[str, Any]:
    refs = [str(value) for key, value in result.items() if key in {"id", "program_id", "offer_id", "reservation_id", "case_id"} and value is not None]
    return {
        **result,
        "source_system": "xyena-demo-funder",
        "retrieved_at": datetime.now().astimezone().isoformat(),
        "evidence_receipt_id": funder_service.evidence_receipt(scope.call_id, kind, scope.tenant_id, refs),
        "security_flags": ["SYNTHETIC_DATA", "EXTERNAL_MARKETPLACE"],
    }


@mcp.tool(name="programs.search")
async def programs_search(amount: Decimal, tenor_days: int, region: str, industry: str, ctx: Context) -> dict[str, Any]:
    """Search current active funding programs using deterministic eligibility rules."""
    scope = verify_runtime_scope(ctx, "funder.programs.search")
    result = await funder_service.search_programs(scope.tenant_id, amount, tenor_days, region, industry)
    return evidence_result(scope, "programs.search", result)


@mcp.tool(name="offers.request")
async def offers_request(
    case_id: str, msme_id: str, msme_name: str, receivable_id: str,
    requested_amount: Decimal, tenor_days: int, region: str, industry: str,
    evidence_receipt_ids: list[str], exposure_snapshot_reference: str,
    exposure_amount: Decimal, ctx: Context,
) -> dict[str, Any]:
    """Create an eligibility-checked marketplace application; this does not issue or reserve funds."""
    scope = verify_runtime_scope(ctx, "funder.offers.request")
    body = ApplicationRequest(
        case_id=case_id, msme_id=msme_id, msme_name=msme_name,
        receivable_id=receivable_id, requested_amount=requested_amount,
        tenor_days=tenor_days, region=region, industry=industry,
        evidence_receipt_ids=evidence_receipt_ids,
        exposure_snapshot_reference=exposure_snapshot_reference,
        exposure_amount=exposure_amount,
    )
    result = await funder_service.create_application(scope.tenant_id, body, scope.agent_name, scope.correlation_id)
    return evidence_result(scope, "offers.request", result)


@mcp.tool(name="offers.get")
async def offers_get(offer_id: str, ctx: Context) -> dict[str, Any]:
    """Read current immutable offer terms, expiry, hash and status."""
    scope = verify_runtime_scope(ctx, "funder.offers.get")
    result = await funder_service.get_offer(scope.tenant_id, offer_id)
    return evidence_result(scope, "offers.get", result)


@mcp.tool(name="offers.reserve")
async def offers_reserve(offer_id: str, amount: Decimal, idempotency_key: str, expires_at: datetime, ctx: Context) -> dict[str, Any]:
    """Create an idempotent, time-bound capacity reservation without moving money."""
    scope = verify_runtime_scope(ctx, "funder.offers.reserve")
    result = await funder_service.reserve_offer(scope.tenant_id, offer_id, ReserveRequest(amount=amount, idempotency_key=idempotency_key, expires_at=expires_at), scope.agent_name, scope.correlation_id)
    return evidence_result(scope, "offers.reserve", result)


@mcp.tool(name="reservations.release")
async def reservations_release(reservation_id: str, expected_version: int, reason: str, ctx: Context) -> dict[str, Any]:
    """Release an unused active reservation and return capacity to its program."""
    scope = verify_runtime_scope(ctx, "funder.reservations.release")
    result = await funder_service.release_reservation(scope.tenant_id, reservation_id, expected_version, ReleaseRequest(reason=reason, actor=scope.agent_name), scope.correlation_id)
    return evidence_result(scope, "reservations.release", result)


@mcp.tool(name="commitments.prepare")
async def commitments_prepare(reservation_id: str, destination_token: str, ctx: Context) -> dict[str, Any]:
    """Prepare a canonical commitment proposal and exact action hash for Guardian review."""
    scope = verify_runtime_scope(ctx, "funder.commitments.prepare")
    result = await funder_service.prepare_commitment(scope.tenant_id, reservation_id, CommitmentPrepareRequest(destination_token=destination_token), scope.agent_name, scope.correlation_id)
    return evidence_result(scope, "commitments.prepare", result)


@mcp.tool(name="commitments.confirm")
async def commitments_confirm(
    commitment_id: str, guardian_authorization_id: str, action_hash: str,
    execution_reference: str, ctx: Context,
) -> dict[str, Any]:
    """Confirm the exact prepared commitment after Guardian authorization; no bank transfer occurs here."""
    scope = verify_runtime_scope(ctx, "funder.commitments.confirm")
    result = await funder_service.confirm_commitment(
        scope.tenant_id, commitment_id,
        CommitmentConfirmRequest(
            guardian_authorization_id=guardian_authorization_id,
            action_hash=action_hash,
            execution_reference=execution_reference,
        ),
        scope.agent_name, scope.correlation_id,
    )
    return evidence_result(scope, "commitments.confirm", result)


@mcp.tool(name="exposure.get")
async def exposure_get(msme_id: str | None, ctx: Context) -> dict[str, Any]:
    """Read current marketplace exposure and program capacity for the signed tenant scope."""
    scope = verify_runtime_scope(ctx, "funder.exposure.get")
    result = await funder_service.get_exposure(scope.tenant_id, msme_id)
    return evidence_result(scope, "exposure.get", result)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "funder-marketplace:8094",
            "funder.gowshik.in",
            "localhost:8094",
            "127.0.0.1:8094",
        ],
        allowed_origins=["https://funder.gowshik.in"],
    ),
)

