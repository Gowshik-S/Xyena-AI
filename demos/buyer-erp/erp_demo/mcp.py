from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings

from .security import RuntimeScope, verify_runtime_scope
from .service import erp_service


mcp = MCPServer("xyena-synthetic-buyer-erp-demo")


def evidence_result(scope: RuntimeScope, kind: str, result: dict[str, Any]) -> dict[str, Any]:
    refs = [
        str(value)
        for key, value in result.items()
        if key in {"id", "business_id", "match_id", "invoice_id", "receipt_number"}
        and value is not None
    ]
    return {
        **result,
        "evidence_receipt_id": erp_service.evidence_receipt(
            scope.call_id, kind, scope.tenant_id, refs
        ),
        "security_flags": ["SYNTHETIC_DATA", "EXTERNAL_EVIDENCE"],
    }


@mcp.tool(name="counterparties.verify")
async def counterparties_verify(
    business_id_or_gstin: str, ctx: Context
) -> dict[str, Any]:
    """Verify an approved buyer or supplier relationship in the signed tenant scope."""
    scope = verify_runtime_scope(ctx, "erp.counterparties.verify")
    result = await erp_service.verify_counterparty(scope.tenant_id, business_id_or_gstin)
    return evidence_result(scope, "counterparties.verify", result)


@mcp.tool(name="purchase_orders.get")
async def purchase_orders_get(order_id_or_number: str, ctx: Context) -> dict[str, Any]:
    """Read a current purchase order and its line-level fulfilment evidence."""
    scope = verify_runtime_scope(ctx, "erp.purchase_orders.get")
    result = await erp_service.get_purchase_order(scope.tenant_id, order_id_or_number)
    return evidence_result(scope, "purchase_orders.get", result)


@mcp.tool(name="purchase_orders.find_by_invoice")
async def purchase_orders_find_by_invoice(
    invoice_id_or_number: str, ctx: Context
) -> dict[str, Any]:
    """Resolve the ERP purchase-order reference for a GST supplier invoice snapshot."""
    scope = verify_runtime_scope(ctx, "erp.purchase_orders.find_by_invoice")
    result = await erp_service.find_purchase_order_by_invoice(
        scope.tenant_id, invoice_id_or_number
    )
    return evidence_result(scope, "purchase_orders.find_by_invoice", result)


@mcp.tool(name="receipts.get")
async def receipts_get(receipt_id_or_number: str, ctx: Context) -> dict[str, Any]:
    """Read posted goods or service receipt evidence and discrepancies."""
    scope = verify_runtime_scope(ctx, "erp.receipts.get")
    result = await erp_service.get_receipt(scope.tenant_id, receipt_id_or_number)
    return evidence_result(scope, "receipts.get", result)


@mcp.tool(name="invoice_matches.get")
async def invoice_matches_get(match_id: str, ctx: Context) -> dict[str, Any]:
    """Read deterministic PO, receipt, and GST invoice matching evidence."""
    scope = verify_runtime_scope(ctx, "erp.invoice_matches.get")
    result = await erp_service.get_invoice_match(scope.tenant_id, match_id)
    return evidence_result(scope, "invoice_matches.get", result)


@mcp.tool(name="invoice_acceptance.get")
async def invoice_acceptance_get(
    match_id_or_invoice_id: str, ctx: Context
) -> dict[str, Any]:
    """Read buyer accounts-payable acceptance and the supported invoice amount."""
    scope = verify_runtime_scope(ctx, "erp.invoice_acceptance.get")
    result = await erp_service.get_invoice_acceptance(
        scope.tenant_id, match_id_or_invoice_id
    )
    return evidence_result(scope, "invoice_acceptance.get", result)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=["buyer-erp:8092", "erp.gowshik.in", "localhost:8092", "127.0.0.1:8092"],
        allowed_origins=["https://erp.gowshik.in"],
    ),
)
