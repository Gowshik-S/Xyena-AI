from datetime import date
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings

from .mcp_security import verify_runtime_scope
from .mcp_service import gst_mcp_service


mcp = MCPServer("xyena-synthetic-gst-demo")


@mcp.tool(name="enterprises.get_classification")
async def enterprises_get_classification(ctx: Context) -> dict[str, Any]:
    """Read the current synthetic enterprise MSME classification and provenance."""
    scope = verify_runtime_scope(ctx, "gst.enterprises.get_classification")
    return await gst_mcp_service.classification(scope)


@mcp.tool(name="taxpayers.get")
async def taxpayers_get(gstin: str, ctx: Context) -> dict[str, Any]:
    """Read a synthetic taxpayer record in the signed enterprise scope."""
    scope = verify_runtime_scope(ctx, "gst.taxpayers.get")
    return await gst_mcp_service.taxpayer(scope, gstin)


@mcp.tool(name="registrations.verify")
async def registrations_verify(gstin: str, ctx: Context) -> dict[str, Any]:
    """Verify current synthetic GST registration status."""
    scope = verify_runtime_scope(ctx, "gst.registrations.verify")
    return await gst_mcp_service.registration(scope, gstin)


@mcp.tool(name="invoices.get")
async def invoices_get(
    ctx: Context,
    invoice_id: str | None = None,
    seller_gstin: str | None = None,
    invoice_number: str | None = None,
    financial_year: str | None = None,
) -> dict[str, Any]:
    """Read an invoice by ID or seller, number and financial year."""
    scope = verify_runtime_scope(ctx, "gst.invoices.get")
    return await gst_mcp_service.invoice_get(
        scope,
        invoice_id=invoice_id,
        seller_gstin=seller_gstin,
        invoice_number=invoice_number,
        financial_year=financial_year,
    )


@mcp.tool(name="invoices.verify")
async def invoices_verify(
    invoice_id: str,
    ctx: Context,
    claimed_total: str | None = None,
    claimed_buyer_gstin: str | None = None,
    claimed_status: str | None = None,
) -> dict[str, Any]:
    """Compare claimed invoice fields against the committed synthetic source record."""
    scope = verify_runtime_scope(ctx, "gst.invoices.verify")
    return await gst_mcp_service.invoice_verify(
        scope,
        invoice_id=invoice_id,
        claimed_total=claimed_total,
        claimed_buyer_gstin=claimed_buyer_gstin,
        claimed_status=claimed_status,
    )


@mcp.tool(name="invoices.search")
async def invoices_search(
    ctx: Context,
    query: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search up to 100 synthetic invoices within the signed enterprise scope."""
    scope = verify_runtime_scope(ctx, "gst.invoices.search")
    return await gst_mcp_service.invoice_search(
        scope, query=query, status=status, limit=limit
    )


@mcp.tool(name="invoices.check_duplicate")
async def invoices_check_duplicate(
    seller_gstin: str,
    invoice_number: str,
    invoice_date: date,
    total_invoice_value: str,
    ctx: Context,
) -> dict[str, Any]:
    """Find exact or deterministic duplicate candidates for synthetic invoice claims."""
    scope = verify_runtime_scope(ctx, "gst.invoices.check_duplicate")
    return await gst_mcp_service.duplicate_check(
        scope,
        seller_gstin=seller_gstin,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        total_invoice_value=total_invoice_value,
    )


@mcp.tool(name="returns.get_summary")
async def returns_get_summary(
    period: str, return_type: str, ctx: Context
) -> dict[str, Any]:
    """Read the latest synthetic return summary for a period and return type."""
    scope = verify_runtime_scope(ctx, "gst.returns.get_summary")
    return await gst_mcp_service.return_summary(scope, period, return_type)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=["gst-portal:8091", "gst.gowshik.in", "localhost:8091", "127.0.0.1:8091"],
        allowed_origins=["https://gst.gowshik.in"],
    ),
)
