from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.contracts.tools import MCPServerCreate, MCPServerReview, ToolPolicyCreate
from packages.mcp_gateway.client import RemoteMCPClient, RemoteServerConfig
from packages.persistence.models.mcp import (
    MCPServer,
    MCPServerVersion,
    MCPTool,
    MCPToolPolicy,
    MCPToolVersion,
)

from .canonical import canonical_hash


class ToolRegistry:
    def __init__(self, client: RemoteMCPClient | None = None) -> None:
        self.client = client or RemoteMCPClient()

    async def register_server(
        self, db: AsyncSession, tenant_id: UUID | None, request: MCPServerCreate
    ) -> MCPServer:
        existing = await db.scalar(
            select(MCPServer).where(MCPServer.tenant_id == tenant_id, MCPServer.label == request.label)
        )
        if existing is not None:
            raise ValueError(f"MCP server label {request.label!r} is already registered")
        server = MCPServer(
            id=uuid4(),
            tenant_id=tenant_id,
            label=request.label,
            description=request.description,
            transport=request.transport.value,
            endpoint=str(request.endpoint),
            auth_type=request.auth_type,
            secret_ref=request.secret_ref,
            trust_tier=request.trust_tier,
            status="PENDING_REVIEW",
            allowed_egress_hosts=request.allowed_egress_hosts,
            timeout_seconds=request.timeout_seconds,
            max_retries=request.max_retries,
        )
        db.add(server)
        return server

    async def discover(self, db: AsyncSession, server: MCPServer) -> MCPServerVersion:
        tools, info = await self.client.list_tools(
            RemoteServerConfig(
                endpoint=server.endpoint,
                auth_type=server.auth_type,
                secret_ref=server.secret_ref,
                timeout_seconds=float(server.timeout_seconds),
                max_retries=server.max_retries,
                allowed_egress_hosts=tuple(server.allowed_egress_hosts),
            )
        )
        discovery = {"server": server.label, "tools": sorted(tools, key=lambda item: item["name"]), **info}
        discovery_hash = canonical_hash(discovery)
        version = await db.scalar(
            select(MCPServerVersion).where(
                MCPServerVersion.server_id == server.id,
                MCPServerVersion.discovery_hash == discovery_hash,
            )
        )
        if version is None:
            version = MCPServerVersion(
                id=uuid4(),
                server_id=server.id,
                discovery_hash=discovery_hash,
                discovery_document=discovery,
                **info,
            )
            db.add(version)
        for discovered in tools:
            await self._upsert_discovered_tool(db, server, discovered)
        server.discovery_hash = discovery_hash
        server.last_discovered_at = datetime.now(UTC)
        server.version += 1
        return version

    async def review_server(
        self, db: AsyncSession, server: MCPServer, review: MCPServerReview
    ) -> MCPServer:
        if server.last_discovered_at is None and review.status == "ACTIVE":
            raise ValueError("Discover the server before activation.")
        server.trust_tier = review.trust_tier
        server.status = review.status
        server.version += 1
        return server

    async def list_tool_versions(
        self, db: AsyncSession, server_id: UUID
    ) -> list[tuple[MCPTool, MCPToolVersion, MCPToolPolicy]]:
        rows = (
            await db.execute(
                select(MCPTool, MCPToolVersion, MCPToolPolicy)
                .join(MCPToolVersion, MCPToolVersion.tool_id == MCPTool.id)
                .join(MCPToolPolicy, MCPToolPolicy.tool_version_id == MCPToolVersion.id)
                .where(MCPTool.server_id == server_id)
                .order_by(MCPTool.canonical_name, MCPToolVersion.created_at.desc())
            )
        ).all()
        return list(rows)

    async def review_tool_version(
        self,
        db: AsyncSession,
        tool_version_id: UUID,
        review: ToolPolicyCreate,
    ) -> tuple[MCPTool, MCPToolVersion, MCPToolPolicy]:
        row = (
            await db.execute(
                select(MCPTool, MCPToolVersion, MCPToolPolicy, MCPServer)
                .join(MCPToolVersion, MCPToolVersion.tool_id == MCPTool.id)
                .join(MCPToolPolicy, MCPToolPolicy.tool_version_id == MCPToolVersion.id)
                .join(MCPServer, MCPServer.id == MCPTool.server_id)
                .where(MCPToolVersion.id == tool_version_id)
                .limit(1)
            )
        ).first()
        if row is None:
            raise LookupError("MCP tool version not found.")
        tool, version, policy, server = row
        if server.status != "ACTIVE":
            raise ValueError("Activate the reviewed MCP server before its tools.")
        if tool.canonical_name != review.canonical_name:
            raise ValueError("Canonical tool name does not match the reviewed version.")
        sibling_ids = select(MCPToolVersion.id).where(
            MCPToolVersion.tool_id == tool.id,
            MCPToolVersion.id != version.id,
        )
        await db.execute(
            update(MCPToolVersion)
            .where(MCPToolVersion.id.in_(sibling_ids))
            .values(status="SUPERSEDED")
        )
        await db.execute(
            update(MCPToolPolicy)
            .where(MCPToolPolicy.tool_version_id.in_(sibling_ids))
            .values(status="DISABLED")
        )
        version.risk_class = review.risk_class.value
        version.side_effects = review.side_effects
        version.idempotent = review.idempotent
        version.parallel_allowed = review.parallel_allowed
        version.hosted_mcp_allowed = review.hosted_mcp_allowed
        version.status = "ACTIVE"
        tool.status = "ACTIVE"
        tool.version += 1
        policy.required_roles = review.required_roles
        policy.required_purposes = review.required_purposes
        policy.required_consents = review.required_consents
        policy.allowed_agents = review.allowed_agents
        policy.approval_mode = review.approval_mode
        policy.timeout_seconds = review.timeout_seconds
        policy.maximum_result_bytes = review.maximum_result_bytes
        policy.status = "ACTIVE"
        policy.version += 1
        return tool, version, policy

    async def _upsert_discovered_tool(
        self, db: AsyncSession, server: MCPServer, discovered: dict[str, Any]
    ) -> MCPToolVersion:
        tool = await db.scalar(
            select(MCPTool).where(
                MCPTool.server_id == server.id,
                MCPTool.original_name == discovered["name"],
            )
        )
        if tool is None:
            canonical_name = f"{server.label}.{discovered['name']}"
            tool = MCPTool(
                id=uuid4(),
                server_id=server.id,
                canonical_name=canonical_name,
                original_name=discovered["name"],
                description=discovered.get("description"),
                status="PENDING_REVIEW",
            )
            db.add(tool)
            await db.flush()
        schema_document = {
            "input": discovered.get("input_schema") or {},
            "output": discovered.get("output_schema") or {},
        }
        schema_hash = canonical_hash(schema_document)
        version = await db.scalar(
            select(MCPToolVersion).where(
                MCPToolVersion.tool_id == tool.id,
                MCPToolVersion.schema_hash == schema_hash,
            )
        )
        if version is None:
            version = MCPToolVersion(
                id=uuid4(),
                tool_id=tool.id,
                schema_hash=schema_hash,
                input_schema=schema_document["input"],
                output_schema=schema_document["output"],
                risk_class="READ",
                side_effects=False,
                idempotent=True,
                parallel_allowed=False,
                hosted_mcp_allowed=False,
                status="PENDING_REVIEW",
            )
            db.add(version)
            await db.flush()
            db.add(
                MCPToolPolicy(
                    id=uuid4(),
                    tool_version_id=version.id,
                    tenant_id=server.tenant_id,
                    approval_mode="POLICY",
                    timeout_seconds=float(server.timeout_seconds),
                    maximum_result_bytes=262_144,
                    status="DRAFT",
                )
            )
        return version


tool_registry = ToolRegistry()
