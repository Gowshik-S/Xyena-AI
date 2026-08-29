import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import Context

from .settings import get_settings


class BankDemoSecurityError(RuntimeError):
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
    authorization_consumed: bool


def verify_runtime_scope(ctx: Context, expected_tool: str) -> RuntimeScope:
    meta: dict[str, Any] = {}
    if ctx.request_context and ctx.request_context.meta:
        meta = dict(ctx.request_context.meta)
    envelope = meta.get("ai.xyena/runtime")
    supplied_signature = meta.get("ai.xyena/signature")
    algorithm = meta.get("ai.xyena/signature-algorithm")
    if not isinstance(envelope, dict) or not isinstance(supplied_signature, str):
        raise BankDemoSecurityError("Signed Xyena runtime scope is required.")
    if algorithm != "hmac-sha256":
        raise BankDemoSecurityError("Unsupported runtime scope signature algorithm.")
    secret = get_settings().mcp_token.get_secret_value()
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"), default=str).encode()
    expected_signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise BankDemoSecurityError("Xyena runtime scope signature is invalid.")
    required = set(RuntimeScope.__dataclass_fields__)
    if required - set(envelope):
        raise BankDemoSecurityError("Xyena runtime scope is incomplete.")
    if envelope["canonical_name"] != expected_tool:
        raise BankDemoSecurityError("Runtime scope tool name does not match this handler.")
    if not str(envelope["purpose"]).strip():
        raise BankDemoSecurityError("A signed purpose is required.")
    if (
        not envelope["guardian_decision_id"]
        or not envelope["authorization_id"]
        or envelope["authorization_consumed"] is not True
    ):
        raise BankDemoSecurityError("Guardian decision and consumed authorization are required.")
    values = {key: str(envelope[key]) for key in required if key != "authorization_consumed"}
    values["authorization_consumed"] = True
    return RuntimeScope(**values)
