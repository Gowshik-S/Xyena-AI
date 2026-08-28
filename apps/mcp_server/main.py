import json
import secrets
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy import select
from starlette.types import ASGIApp, Receive, Scope, Send

from apps.api.errors import register_error_handlers
from apps.api.middleware import CorrelationMiddleware
from apps.mcp_server.server import mcp, mcp_app
from packages.config import get_settings
from packages.contracts.tools import (
    MCPServerCreate,
    MCPServerReview,
    MCPServerView,
    MCPToolVersionView,
    SafeToolResult,
    ToolCallResume,
    ToolCallSubmit,
    ToolPolicyCreate,
)
from packages.identity.service_auth import require_mcp_admin_token, require_service_token
from packages.observability import configure_logging, configure_telemetry
from packages.persistence import get_database
from packages.persistence.models.mcp import MCPServer
from packages.tools import ToolBrokerError, tool_broker, tool_registry


class MCPServiceAuthMiddleware:
    """Protect the mounted MCP protocol endpoint with the workload service token."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            raw = headers.get(b"authorization", b"").decode("latin-1")
            scheme, _, supplied = raw.partition(" ")
            configured = get_settings().service_token
            valid = (
                configured is not None
                and scheme.lower() == "bearer"
                and secrets.compare_digest(supplied, configured.get_secret_value())
            )
            if not valid:
                body = json.dumps({"code": "UNAUTHORIZED", "detail": "Invalid service token."}).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield
    await get_database().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Xyena MCP Gateway",
        summary="Controlled MCP registry, discovery, broker, and hosted core tools",
        version="0.1.0",
        openapi_version="3.1.0",
        openapi_url="/openapi.json" if settings.env != "production" else None,
        docs_url="/docs" if settings.env != "production" else None,
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationMiddleware)
    app.mount("/mcp", MCPServiceAuthMiddleware(mcp_app))

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-mcp"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with get_database().engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
        return {"status": "ready", "service": "xyena-mcp"}

    @app.post(
        "/internal/mcp/servers",
        response_model=MCPServerView,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_service_token)],
        tags=["registry"],
    )
    async def register_server(
        body: MCPServerCreate,
        request: Request,
        tenant_id: UUID | None = None,
    ) -> MCPServerView:
        async with get_database().session(
            tenant_id=tenant_id, service_role="mcp"
        ) as db:
            try:
                server = await tool_registry.register_server(db, tenant_id, body)
                await db.flush()
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return MCPServerView.model_validate(server)

    @app.get(
        "/internal/mcp/servers",
        response_model=list[MCPServerView],
        dependencies=[Depends(require_service_token)],
        tags=["registry"],
    )
    async def list_servers(tenant_id: UUID | None = None) -> list[MCPServerView]:
        async with get_database().session(tenant_id=tenant_id, service_role="mcp") as db:
            servers = (
                await db.scalars(
                    select(MCPServer)
                    .where(MCPServer.tenant_id == tenant_id)
                    .order_by(MCPServer.label)
                )
            ).all()
            return [MCPServerView.model_validate(server) for server in servers]

    @app.post(
        "/internal/mcp/servers/{server_id}/discover",
        dependencies=[Depends(require_service_token)],
        tags=["registry"],
    )
    async def discover_server(server_id: UUID, tenant_id: UUID | None = None) -> dict[str, str]:
        async with get_database().session(tenant_id=tenant_id, service_role="mcp") as db:
            server = await db.get(MCPServer, server_id)
            if server is None or server.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="MCP server not found.")
            version = await tool_registry.discover(db, server)
            await db.flush()
            return {
                "server_id": str(server.id),
                "server_version_id": str(version.id),
                "discovery_hash": version.discovery_hash,
            }

    @app.post(
        "/internal/mcp/servers/{server_id}/review",
        response_model=MCPServerView,
        dependencies=[Depends(require_mcp_admin_token)],
        tags=["review"],
    )
    async def review_server(
        server_id: UUID, body: MCPServerReview, tenant_id: UUID | None = None
    ) -> MCPServerView:
        async with get_database().session(tenant_id=tenant_id, service_role="mcp") as db:
            server = await db.get(MCPServer, server_id)
            if server is None or server.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="MCP server not found.")
            try:
                value = await tool_registry.review_server(db, server, body)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return MCPServerView.model_validate(value)

    @app.get(
        "/internal/mcp/servers/{server_id}/tools",
        response_model=list[MCPToolVersionView],
        dependencies=[Depends(require_mcp_admin_token)],
        tags=["review"],
    )
    async def list_server_tools(
        server_id: UUID, tenant_id: UUID | None = None
    ) -> list[MCPToolVersionView]:
        async with get_database().session(tenant_id=tenant_id, service_role="mcp") as db:
            server = await db.get(MCPServer, server_id)
            if server is None or server.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="MCP server not found.")
            rows = await tool_registry.list_tool_versions(db, server_id)
            return [
                MCPToolVersionView(
                    tool_id=tool.id,
                    tool_version_id=version.id,
                    server_id=tool.server_id,
                    canonical_name=tool.canonical_name,
                    original_name=tool.original_name,
                    description=tool.description,
                    schema_hash=version.schema_hash,
                    input_schema=version.input_schema,
                    output_schema=version.output_schema,
                    risk_class=version.risk_class,
                    tool_status=tool.status,
                    version_status=version.status,
                    policy_status=policy.status,
                )
                for tool, version, policy in rows
            ]

    @app.post(
        "/internal/mcp/tools/{tool_version_id}/review",
        response_model=MCPToolVersionView,
        dependencies=[Depends(require_mcp_admin_token)],
        tags=["review"],
    )
    async def review_tool_version(
        tool_version_id: UUID, body: ToolPolicyCreate, tenant_id: UUID | None = None
    ) -> MCPToolVersionView:
        async with get_database().session(tenant_id=tenant_id, service_role="mcp") as db:
            try:
                tool, version, policy = await tool_registry.review_tool_version(
                    db, tool_version_id, body, tenant_id
                )
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return MCPToolVersionView(
                tool_id=tool.id,
                tool_version_id=version.id,
                server_id=tool.server_id,
                canonical_name=tool.canonical_name,
                original_name=tool.original_name,
                description=tool.description,
                schema_hash=version.schema_hash,
                input_schema=version.input_schema,
                output_schema=version.output_schema,
                risk_class=version.risk_class,
                tool_status=tool.status,
                version_status=version.status,
                policy_status=policy.status,
            )

    @app.post(
        "/internal/mcp/calls",
        response_model=SafeToolResult,
        dependencies=[Depends(require_service_token)],
        tags=["broker"],
    )
    async def execute_tool(body: ToolCallSubmit) -> SafeToolResult:
        async with get_database().session(
            tenant_id=body.context.tenant_id,
            user_id=body.context.user_id,
            service_role="mcp",
        ) as db:
            try:
                return await tool_broker.execute(db, body)
            except ToolBrokerError as exc:
                raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}") from exc

    @app.post(
        "/internal/mcp/calls/resume",
        response_model=SafeToolResult,
        dependencies=[Depends(require_service_token)],
        tags=["broker"],
    )
    async def resume_tool(body: ToolCallResume) -> SafeToolResult:
        async with get_database().session(
            tenant_id=body.tenant_id, service_role="mcp"
        ) as db:
            try:
                return await tool_broker.resume(db, body)
            except ToolBrokerError as exc:
                raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}") from exc

    register_error_handlers(app)
    configure_telemetry(app, "xyena-mcp")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "apps.mcp_server.main:app",
        host=settings.api_host,
        port=settings.mcp_port,
        reload=False,
    )
