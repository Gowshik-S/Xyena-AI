import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import Context

from .settings import get_settings


class ERPSecurityError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeScope:
    tenant_id: str
    organization_id: str
    user_id: str
    session_id: str
    run_id: str
    call_id: str
    correlation_id: str
    agent_name: str
    canonical_name: str
    purpose: str
    request_hash: str


def verify_runtime_scope(ctx: Context, expected_tool: str) -> RuntimeScope:
    meta: dict[str, Any] = {}
    if ctx.request_context and ctx.request_context.meta:
        meta = dict(ctx.request_context.meta)
    envelope = meta.get("ai.xyena/runtime")
    signature = meta.get("ai.xyena/signature")
    algorithm = meta.get("ai.xyena/signature-algorithm")
    if not isinstance(envelope, dict) or not isinstance(signature, str):
        raise ERPSecurityError("Signed Xyena runtime scope is required.")
    if algorithm != "hmac-sha256":
        raise ERPSecurityError("Unsupported runtime signature algorithm.")
    canonical = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    expected = hmac.new(
        get_settings().mcp_token.get_secret_value().encode(), canonical, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ERPSecurityError("Xyena runtime scope signature is invalid.")
    required = {
        "tenant_id",
        "organization_id",
        "user_id",
        "session_id",
        "run_id",
        "call_id",
        "correlation_id",
        "agent_name",
        "canonical_name",
        "purpose",
        "request_hash",
    }
    if required - set(envelope):
        raise ERPSecurityError("Xyena runtime scope is incomplete.")
    if envelope["canonical_name"] != expected_tool:
        raise ERPSecurityError("Runtime tool name does not match this ERP handler.")
    if not str(envelope["purpose"]).strip():
        raise ERPSecurityError("A signed evidence purpose is required.")
    return RuntimeScope(**{key: str(envelope[key]) for key in required})
