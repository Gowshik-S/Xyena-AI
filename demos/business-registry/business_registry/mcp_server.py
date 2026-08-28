from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings

from .mcp_security import verify_runtime_scope
from .mcp_service import registry_mcp_service


mcp = MCPServer("xyena-synthetic-business-registry")


@mcp.tool(name="businesses.get")
async def businesses_get(identifier: str, ctx: Context) -> dict[str, Any]:
    """Read a current synthetic business identity record by ID, registry number or GSTIN."""
    scope = verify_runtime_scope(ctx, "registry.businesses.get")
    return await registry_mcp_service.business_get(scope, identifier)


@mcp.tool(name="businesses.verify")
async def businesses_verify(
    identifier: str,
    ctx: Context,
    claimed_legal_name: str | None = None,
    claimed_gstin: str | None = None,
    claimed_status: str | None = None,
) -> dict[str, Any]:
    """Compare claimed business identity fields with the committed registry record."""
    scope = verify_runtime_scope(ctx, "registry.businesses.verify")
    return await registry_mcp_service.business_verify(
        scope, identifier=identifier, claimed_legal_name=claimed_legal_name,
        claimed_gstin=claimed_gstin, claimed_status=claimed_status,
    )


@mcp.tool(name="businesses.search")
async def businesses_search(
    query: str, ctx: Context, status: str | None = None, limit: int = 20
) -> dict[str, Any]:
    """Search bounded synthetic business candidates within the signed tenant scope."""
    scope = verify_runtime_scope(ctx, "registry.businesses.search")
    return await registry_mcp_service.business_search(
        scope, query=query, status=status, limit=limit
    )


@mcp.tool(name="ownership.get")
async def ownership_get(business_id: str, ctx: Context) -> dict[str, Any]:
    """Read current verified synthetic ownership links for a business."""
    scope = verify_runtime_scope(ctx, "registry.ownership.get")
    return await registry_mcp_service.ownership_get(scope, business_id)


@mcp.tool(name="relationships.get")
async def relationships_get(business_id: str, ctx: Context) -> dict[str, Any]:
    """Read approved buyer, seller, group and service-provider relationships."""
    scope = verify_runtime_scope(ctx, "registry.relationships.get")
    return await registry_mcp_service.relationships_get(scope, business_id)


@mcp.tool(name="authorized_persons.get")
async def authorized_persons_get(business_id: str, ctx: Context) -> dict[str, Any]:
    """Read tokenized currently authorized persons for a synthetic business."""
    scope = verify_runtime_scope(ctx, "registry.authorized_persons.get")
    return await registry_mcp_service.authorized_persons_get(scope, business_id)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "business-registry:8093",
            "registry.gowshik.in",
            "localhost:8093",
            "127.0.0.1:8093",
        ],
        allowed_origins=["https://registry.gowshik.in"],
    ),
)
