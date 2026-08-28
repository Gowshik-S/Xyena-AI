import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.audit import append_audit_event, enqueue_outbox
from packages.contracts.tools import (
    CanonicalToolRequest,
    SafeToolResult,
    ToolCallStatus,
    ToolCallSubmit,
    ToolRiskClass,
)
from packages.mcp_gateway.client import RemoteMCPClient, RemoteServerConfig
from packages.persistence.models.mcp import (
    MCPCallAttempt,
    MCPServer,
    MCPTool,
    MCPToolCall,
    MCPToolPolicy,
    MCPToolResult,
    MCPToolVersion,
)

from .canonical import canonical_hash
from .core_handlers import CORE_HANDLERS


class ToolBrokerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ToolBroker:
    """The only allowed execution path for first-party and remote MCP tools."""

    def __init__(self, remote_client: RemoteMCPClient | None = None) -> None:
        self.remote_client = remote_client or RemoteMCPClient()

    async def execute(self, db: AsyncSession, request: ToolCallSubmit) -> SafeToolResult:
        resolved = await self._resolve(db, request)
        tool, version, policy, server = resolved
        self._validate_access(request, tool, version, policy, server)
        self._validate_arguments(version.input_schema, request.intent.arguments)

        normalized_arguments = json.loads(
            json.dumps(request.intent.arguments, sort_keys=True, separators=(",", ":"))
        )
        call_id = uuid4()
        request_document = {
            "run_id": str(request.run_id),
            "agent_version_id": str(request.agent_version_id) if request.agent_version_id else None,
            "agent_name": request.agent_name,
            "scope": request.context.model_dump(mode="json"),
            "server_id": str(server.id),
            "tool_version_id": str(version.id),
            "canonical_name": tool.canonical_name,
            "original_name": tool.original_name,
            "normalized_arguments": normalized_arguments,
            "purpose": request.intent.purpose,
            "resource_refs": request.intent.resource_refs,
            "idempotency_key": request.intent.idempotency_key,
        }
        request_hash = canonical_hash(request_document)
        canonical_request = CanonicalToolRequest(
            call_id=call_id,
            request_hash=request_hash,
            **request_document,
        )

        existing = await self._find_idempotent_result(db, request, tool, version, request_hash)
        if existing is not None:
            return existing

        call = MCPToolCall(
            id=call_id,
            tenant_id=request.context.tenant_id,
            organization_id=request.context.organization_id,
            user_id=request.context.user_id,
            session_id=request.context.session_id,
            run_id=request.run_id,
            agent_version_id=request.agent_version_id,
            agent_name=request.agent_name,
            server_id=server.id,
            tool_version_id=version.id,
            canonical_name=tool.canonical_name,
            normalized_arguments=normalized_arguments,
            purpose=request.intent.purpose,
            resource_refs=request.intent.resource_refs,
            request_hash=request_hash,
            idempotency_key=request.intent.idempotency_key,
            status=ToolCallStatus.VALIDATED.value,
            correlation_id=request.context.correlation_id,
        )
        db.add(call)
        await db.flush()

        await append_audit_event(
            db,
            tenant_id=request.context.tenant_id,
            actor_type="AGENT",
            actor_id=request.agent_name,
            event_type="mcp.tool_call.validated",
            subject_type="MCP_TOOL_CALL",
            subject_id=call.id,
            correlation_id=request.context.correlation_id,
            payload={
                "canonical_name": tool.canonical_name,
                "request_hash": request_hash,
                "risk_class": version.risk_class,
            },
        )

        # Until Guardian is wired in checkpoint 3, only approved, side-effect-free reads run.
        if version.risk_class != ToolRiskClass.READ.value or policy.approval_mode != "NEVER":
            call.status = ToolCallStatus.BLOCKED.value
            result = await self._store_result(
                db,
                call,
                status="BLOCKED",
                projection=None,
                policy=policy,
                error_code="GUARDIAN_REQUIRED",
                error_message="This tool requires a Guardian decision before execution.",
                flags=["protected_tool"],
            )
            return self._safe_result(result, call.id)

        return await self._call(db, call, canonical_request, server, tool, policy)

    async def _resolve(
        self, db: AsyncSession, request: ToolCallSubmit
    ) -> tuple[MCPTool, MCPToolVersion, MCPToolPolicy, MCPServer]:
        row = (
            await db.execute(
                select(MCPTool, MCPToolVersion, MCPToolPolicy, MCPServer)
                .join(MCPToolVersion, MCPToolVersion.tool_id == MCPTool.id)
                .join(MCPServer, MCPServer.id == MCPTool.server_id)
                .join(MCPToolPolicy, MCPToolPolicy.tool_version_id == MCPToolVersion.id)
                .where(
                    MCPTool.canonical_name == request.intent.requested_name,
                    or_(
                        MCPToolPolicy.tenant_id == request.context.tenant_id,
                        MCPToolPolicy.tenant_id.is_(None),
                    ),
                )
                .order_by(MCPToolPolicy.tenant_id.desc().nulls_last())
                .limit(1)
            )
        ).first()
        if row is None:
            raise ToolBrokerError("TOOL_NOT_FOUND", "The requested tool is not registered.")
        return row

    def _validate_access(
        self,
        request: ToolCallSubmit,
        tool: MCPTool,
        version: MCPToolVersion,
        policy: MCPToolPolicy,
        server: MCPServer,
    ) -> None:
        if request.context.session_id is None:
            raise ToolBrokerError("CONTEXT_INCOMPLETE", "A tool call requires a scoped session.")
        if any(item.status != "ACTIVE" for item in (tool, version, policy, server)):
            raise ToolBrokerError("TOOL_NOT_ACTIVE", "The tool or its policy is not active.")
        if policy.allowed_agents and request.agent_name not in policy.allowed_agents:
            raise ToolBrokerError("AGENT_NOT_GRANTED", "The agent is not granted this tool.")
        missing_roles = set(policy.required_roles) - set(request.context.roles)
        if missing_roles:
            raise ToolBrokerError("ROLE_REQUIRED", "The caller lacks a required role.")
        if policy.required_purposes and request.intent.purpose not in policy.required_purposes:
            raise ToolBrokerError("PURPOSE_NOT_ALLOWED", "The declared purpose is not allowed.")
        consent_ids = {str(value) for value in request.context.consent_ids}
        if set(policy.required_consents) - consent_ids:
            raise ToolBrokerError("CONSENT_REQUIRED", "Required consent is not present.")
        if version.side_effects and not request.intent.idempotency_key:
            raise ToolBrokerError("IDEMPOTENCY_REQUIRED", "Mutating tools require an idempotency key.")

    @staticmethod
    def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
        errors = sorted(Draft202012Validator(schema or {}).iter_errors(arguments), key=lambda e: e.path)
        if errors:
            detail = "; ".join(error.message for error in errors[:5])
            raise ToolBrokerError("TOOL_ARGUMENTS_INVALID", detail)

    async def _find_idempotent_result(
        self,
        db: AsyncSession,
        request: ToolCallSubmit,
        tool: MCPTool,
        version: MCPToolVersion,
        request_hash: str,
    ) -> SafeToolResult | None:
        key = request.intent.idempotency_key
        if not key:
            return None
        existing = await db.scalar(
            select(MCPToolCall)
            .where(
                MCPToolCall.tenant_id == request.context.tenant_id,
                MCPToolCall.tool_version_id == version.id,
                MCPToolCall.idempotency_key == key,
            )
            .with_for_update()
        )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            raise ToolBrokerError(
                "IDEMPOTENCY_CONFLICT", "The idempotency key was already used with a different request."
            )
        result = await db.scalar(select(MCPToolResult).where(MCPToolResult.call_id == existing.id))
        if result is None:
            raise ToolBrokerError("CALL_IN_PROGRESS", "The matching tool call has not completed.")
        return self._safe_result(result, existing.id)

    async def _call(
        self,
        db: AsyncSession,
        call: MCPToolCall,
        request: CanonicalToolRequest,
        server: MCPServer,
        tool: MCPTool,
        policy: MCPToolPolicy,
    ) -> SafeToolResult:
        now = datetime.now(UTC)
        attempt = MCPCallAttempt(
            id=uuid4(),
            tenant_id=call.tenant_id,
            call_id=call.id,
            attempt_number=1,
            status="CALLING",
            started_at=now,
        )
        db.add(attempt)
        call.status = ToolCallStatus.CALLING.value
        try:
            handler = CORE_HANDLERS.get(tool.canonical_name)
            if handler is not None:
                projection = await handler(request.normalized_arguments)
            else:
                projection = await self.remote_client.call_tool(
                    RemoteServerConfig(
                        endpoint=server.endpoint,
                        auth_type=server.auth_type,
                        secret_ref=server.secret_ref,
                        timeout_seconds=float(policy.timeout_seconds),
                        max_retries=server.max_retries,
                    ),
                    tool.original_name,
                    request.normalized_arguments,
                )
            encoded = json.dumps(projection, default=str, separators=(",", ":")).encode()
            if len(encoded) > policy.maximum_result_bytes:
                raise ToolBrokerError("RESULT_TOO_LARGE", "The tool result exceeded its policy limit.")
            attempt.status = "SUCCEEDED"
            attempt.completed_at = datetime.now(UTC)
            call.status = ToolCallStatus.SUCCEEDED.value
            result = await self._store_result(db, call, "SUCCEEDED", projection, policy)
        except Exception as exc:
            attempt.status = "FAILED"
            attempt.completed_at = datetime.now(UTC)
            attempt.error_class = type(exc).__name__
            attempt.error_detail = str(exc)[:4000]
            call.status = ToolCallStatus.FAILED.value
            code = exc.code if isinstance(exc, ToolBrokerError) else "TOOL_EXECUTION_FAILED"
            result = await self._store_result(
                db,
                call,
                "FAILED",
                None,
                policy,
                error_code=code,
                error_message="The tool could not be completed.",
            )

        await enqueue_outbox(
            db,
            tenant_id=call.tenant_id,
            aggregate_type="MCP_TOOL_CALL",
            aggregate_id=call.id,
            aggregate_version=call.version,
            event_type=f"mcp.tool_call.{call.status.lower()}",
            correlation_id=call.correlation_id,
            payload={"canonical_name": call.canonical_name, "status": call.status},
        )
        return self._safe_result(result, call.id)

    async def _store_result(
        self,
        db: AsyncSession,
        call: MCPToolCall,
        status: str,
        projection: Any,
        policy: MCPToolPolicy,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        flags: list[str] | None = None,
    ) -> MCPToolResult:
        flags = flags or []
        normalized_hash = canonical_hash({"status": status, "projection": projection, "flags": flags})
        result = MCPToolResult(
            id=uuid4(),
            tenant_id=call.tenant_id,
            call_id=call.id,
            status=status,
            model_projection=projection,
            normalized_hash=normalized_hash,
            classification=flags,
            error_code=error_code,
            error_message=error_message,
        )
        db.add(result)
        return result

    @staticmethod
    def _safe_result(result: MCPToolResult, call_id: UUID) -> SafeToolResult:
        return SafeToolResult(
            call_id=call_id,
            status=result.status,
            model_projection=result.model_projection,
            result_ref=result.id,
            provenance_hash=result.normalized_hash,
            security_flags=result.classification,
            error_code=result.error_code,
            error_message=result.error_message,
        )


tool_broker = ToolBroker()
