import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import Context

from .settings import get_settings


class LedgerSecurityError(RuntimeError):
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
    guardian_decision_id: str
    authorization_id: str


def verify_runtime_scope(ctx: Context, expected_tool: str) -> RuntimeScope:
    meta: dict[str, Any] = dict(ctx.request_context.meta or {}) if ctx.request_context else {}
    envelope, supplied = meta.get("ai.xyena/runtime"), meta.get("ai.xyena/signature")
    if not isinstance(envelope, dict) or not isinstance(supplied, str):
        raise LedgerSecurityError("Signed Xyena runtime scope is required.")
    if meta.get("ai.xyena/signature-algorithm") != "hmac-sha256":
        raise LedgerSecurityError("Unsupported runtime signature algorithm.")
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"), default=str).encode()
    expected = hmac.new(get_settings().mcp_token.get_secret_value().encode(), canonical,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise LedgerSecurityError("Runtime scope signature is invalid.")
    required = set(RuntimeScope.__dataclass_fields__)
    if required - set(envelope) or envelope["canonical_name"] != expected_tool:
        raise LedgerSecurityError("Runtime scope is incomplete or bound to another tool.")
    if not str(envelope["purpose"]).strip():
        raise LedgerSecurityError("A signed purpose is required.")
    if not envelope["guardian_decision_id"] or not envelope["authorization_id"]:
        raise LedgerSecurityError("Guardian decision and consumed authorization are required.")
    return RuntimeScope(**{key: str(envelope[key]) for key in required})
