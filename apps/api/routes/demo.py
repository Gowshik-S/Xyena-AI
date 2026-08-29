import asyncio
import hashlib
import json
import re
import secrets
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from time import monotonic, perf_counter
from typing import Any, Literal
from urllib.parse import unquote
from uuid import UUID, uuid4

import httpx
from agents import Agent, Runner
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import Field
from pypdf import PdfReader
from sqlalchemy import func, select, text

from packages.agents import AgentRuntime
from packages.config import Settings, get_settings
from packages.contracts.common import ContractModel
from packages.contracts.context import RuntimeContext
from packages.contracts.tools import SafeToolResult, ToolCallSubmit, ToolIntent
from packages.persistence import get_database
from packages.persistence.models.guardian import GuardianAuthorization, GuardianDecision
from packages.persistence.models.mcp import MCPServer, MCPTool, MCPToolCall

router = APIRouter(prefix="/demo", tags=["Live demo"])

_proof_lock = asyncio.Lock()
_last_proof_at = 0.0
_minimum_interval_seconds = 10
_trace_lock = asyncio.Lock()
_last_trace_at = 0.0
_trace_interval_seconds = 12
_pdf_scan_lock = asyncio.Lock()
_last_pdf_scan_at = 0.0
_pdf_scan_interval_seconds = 3
_operations_lock = asyncio.Lock()
_last_operations_at = 0.0
_operations_interval_seconds = 5
_maximum_pdf_bytes = 2 * 1024 * 1024
_maximum_pdf_pages = 8
_maximum_extracted_characters = 20_000

_GST_TENANT_ID = UUID("00000000-0000-4000-8000-000000001101")
_GST_ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000001201")
_SHARED_DEMO_TENANT_ID = UUID("00000000-0000-4000-8000-000000000101")
_SHARED_DEMO_ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000301")
_SHARED_DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000201")
_REGISTRY_TENANT_ID = UUID("00000000-0000-4000-8000-000000001301")
_REGISTRY_ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000001201")
_JUDGE_SCENARIOS: dict[str, dict[str, str]] = {
    "platform_network": {
        "label": "Six-platform MCP network tour",
        "invoice_number": "NETWORK/READ-ONLY",
        "search_status": "REGISTERED",
        "claimed_total": "0.00",
        "claimed_buyer_gstin": "",
        "claimed_status": "READ_ONLY",
    },
    "verified_invoice": {
        "label": "Registered invoice — verified",
        "invoice_number": "MICRO/26/101",
        "search_status": "REGISTERED",
        "claimed_total": "545750.00",
        "claimed_buyer_gstin": "29BUYER1234A1Z8",
        "claimed_status": "REGISTERED",
    },
    "amount_mismatch": {
        "label": "Registered invoice — amount mismatch",
        "invoice_number": "MICRO/26/101",
        "search_status": "REGISTERED",
        "claimed_total": "545700.00",
        "claimed_buyer_gstin": "29BUYER1234A1Z8",
        "claimed_status": "REGISTERED",
    },
    "submitted_invoice": {
        "label": "Submitted invoice — not yet eligible",
        "invoice_number": "MICRO/26/102",
        "search_status": "SUBMITTED",
        "claimed_total": "339840.00",
        "claimed_buyer_gstin": "27BUYER5678B1Z6",
        "claimed_status": "REGISTERED",
    },
}

_INJECTION_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        "instruction_override",
        "critical",
        r"ignore\s+(all|any|the)?\s*(previous|prior|system|developer)\s+instructions?",
    ),
    ("authority_impersonation", "high", r"\b(system|developer)\s+(prompt|message|instruction)\b"),
    ("guardian_bypass", "critical", r"(bypass|disable|skip|override)\s+(the\s+)?guardian"),
    (
        "unsafe_tool_request",
        "critical",
        r"\b(call|invoke|execute|run)\s+(the\s+)?(tool|mcp|ledger|payment|disbursement)",
    ),
    (
        "secret_exfiltration",
        "critical",
        r"\b(reveal|print|return|expose)\b.{0,40}\b(api\s*key|secret|token|credential|system\s*prompt)\b",
    ),
    (
        "concealment",
        "high",
        r"(do\s+not|don['’]t)\s+(tell|show|inform)\s+(the\s+)?(user|reviewer|operator)",
    ),
    ("priority_escalation", "high", r"(higher|highest)\s+priority|must\s+obey\s+this\s+document"),
    ("role_manipulation", "medium", r"\bact\s+as\b.{0,35}\b(admin|system|guardian|approver)\b"),
    ("prompt_markup", "medium", r"<\/?(system|assistant|developer|tool)>|\[(system|developer)\]"),
)


class ComponentEvidence(ContractModel):
    status: Literal["verified", "failed"]
    latency_ms: int
    message: str


class RegistryEvidence(ComponentEvidence):
    active_servers: int
    active_tools: int


class ModelEvidence(ComponentEvidence):
    provider: str
    model: str
    output: str | None = None


class LiveProof(ContractModel):
    proof_id: UUID
    status: Literal["verified", "degraded"]
    checked_at: datetime
    duration_ms: int
    scope: Literal["synthetic-read-only"] = "synthetic-read-only"
    state_changed: Literal[False] = False
    database: ComponentEvidence
    registry: RegistryEvidence
    mcp_gateway: ComponentEvidence
    guardian: ComponentEvidence
    model: ModelEvidence


class JudgeTraceRequest(ContractModel):
    scenario: Literal[
        "platform_network", "verified_invoice", "amount_mismatch", "submitted_invoice"
    ] = "verified_invoice"


class GuardianTrace(ContractModel):
    decision_id: UUID | None = None
    outcome: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    risk_class: str | None = None
    request_hash: str | None = None
    authorization_status: str | None = None


class AgentTraceStep(ContractModel):
    sequence: int
    kind: Literal["tool", "model", "decision"]
    actor: str
    title: str
    status: Literal["verified", "failed", "info"]
    started_at: datetime
    latency_ms: int
    tool_name: str | None = None
    call_id: UUID | None = None
    input_data: dict[str, Any]
    output_data: Any = None
    provenance_hash: str | None = None
    security_flags: list[str] = Field(default_factory=list)
    guardian: GuardianTrace | None = None


class ToolRiskEvidence(ContractModel):
    tool_name: str
    platform: str
    risk_class: str
    registered_risk_points: int
    guardian_outcome: str
    guardian_points: int
    execution_points: int
    security_points: int
    subtotal: int
    unexpected_security_flags: list[str] = Field(default_factory=list)
    execution_status: str


class TraceRiskAssessment(ContractModel):
    score: int
    band: Literal["LOW", "GUARDED", "HIGH", "CRITICAL"]
    policy_action: str
    formula_version: Literal["judge-risk-v1"] = "judge-risk-v1"
    calculation: dict[str, int]
    tools: list[ToolRiskEvidence]
    explanation: str


class JudgeTrace(ContractModel):
    trace_id: UUID
    correlation_id: UUID
    scenario: str
    scenario_label: str
    subject: dict[str, str]
    status: Literal["verified", "not_verified", "error"]
    verified: bool
    reason_codes: list[str]
    summary: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    scope: Literal["synthetic-read-only"] = "synthetic-read-only"
    state_changed: Literal[False] = False
    audit_records_created: Literal[True] = True
    risk: TraceRiskAssessment
    steps: list[AgentTraceStep]


class PdfThreatFinding(ContractModel):
    category: str
    severity: Literal["medium", "high", "critical"]
    page: int | None = None
    snippet: str


class PdfStructureEvidence(ContractModel):
    encrypted: bool
    has_open_action: bool
    has_additional_actions: bool
    has_javascript: bool
    has_embedded_files: bool
    annotation_count: int


class PdfScanReport(ContractModel):
    scan_id: UUID
    file_name: str
    sha256: str
    size_bytes: int
    page_count: int
    classification: Literal[
        "BLOCKED_PROMPT_INJECTION",
        "AMOUNT_MISMATCH",
        "VERIFIED_SOURCE_MATCH",
        "REVIEW_REQUIRED",
        "NO_INJECTION_FOUND",
    ]
    flagged: bool
    risk_score: int
    reason_codes: list[str]
    findings: list[PdfThreatFinding]
    structure: PdfStructureEvidence
    extracted_preview: str
    document_verification: Literal[
        "BLOCKED", "SOURCE_MATCH", "SOURCE_MISMATCH", "NOT_CHECKED"
    ] = "NOT_CHECKED"
    claim_checks: dict[str, Any] = Field(default_factory=dict)
    tool_steps: list[AgentTraceStep] = Field(default_factory=list)
    scanned_at: datetime
    content_forwarded_to_model: Literal[False] = False
    tool_calls_executed: int = Field(default=0, ge=0, le=4)
    business_state_changed: Literal[False] = False
    handling: str = "Document evidence has not yet been matched to an independent source."


class OperationsSnapshotRequest(ContractModel):
    registry_identifier: str = Field(default="29ABCDE1234F1Z5", min_length=3, max_length=80)
    gst_invoice_number: str = Field(default="MICRO/26/101", min_length=3, max_length=80)
    gst_status: str = Field(default="REGISTERED", min_length=3, max_length=30)
    erp_order_reference: str = Field(default="PO-1007", min_length=3, max_length=80)
    delivery_seller_id: str = Field(default="seller_global_tech", min_length=3, max_length=80)
    delivery_invoice_number: str = Field(default="INV-8942", min_length=3, max_length=80)
    bank_account_token: str = Field(default="acct_demo_operating", min_length=3, max_length=80)


class OperationsSnapshot(ContractModel):
    snapshot_id: UUID
    correlation_id: UUID
    status: Literal["verified", "partial", "failed"]
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    inputs: dict[str, str]
    steps: list[AgentTraceStep]
    successful_calls: int
    total_calls: int
    evidence_matched_calls: int
    evidence_matches: dict[str, bool]
    evidence_complete: bool
    funding_gate: Literal["READ_ONLY_EVIDENCE_COMPLETE", "BLOCKED_MISSING_EVIDENCE"]
    amount_transferred: Literal["0.00"] = "0.00"
    source_apps: dict[str, str]
    scope: Literal["synthetic-live-operations"] = "synthetic-live-operations"
    state_changed: Literal[False] = False


def _authorize_demo(
    token: str | None = Header(default=None, alias="X-Demo-Token"),
    settings: Settings = Depends(get_settings),  # noqa: B008 - FastAPI dependency declaration
) -> Settings:
    if not settings.live_demo_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Live demo is disabled.")
    configured = settings.live_demo_token
    if (
        configured is None
        or token is None
        or not secrets.compare_digest(token, configured.get_secret_value())
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid demo token.")
    return settings


async def _database_and_registry_evidence() -> tuple[ComponentEvidence, RegistryEvidence]:
    started = perf_counter()
    try:
        async with get_database().session(service_role="live-demo") as db:
            await db.execute(text("SELECT 1"))
            active_servers = await db.scalar(
                select(func.count()).select_from(MCPServer).where(MCPServer.status == "ACTIVE")
            )
            active_tools = await db.scalar(
                select(func.count()).select_from(MCPTool).where(MCPTool.status == "ACTIVE")
            )
        latency = round((perf_counter() - started) * 1000)
        return (
            ComponentEvidence(
                status="verified",
                latency_ms=latency,
                message="PostgreSQL accepted a live read-only query.",
            ),
            RegistryEvidence(
                status="verified",
                latency_ms=latency,
                message="The MCP registry was queried from PostgreSQL.",
                active_servers=int(active_servers or 0),
                active_tools=int(active_tools or 0),
            ),
        )
    except Exception:
        latency = round((perf_counter() - started) * 1000)
        return (
            ComponentEvidence(
                status="failed",
                latency_ms=latency,
                message="The PostgreSQL proof query did not complete.",
            ),
            RegistryEvidence(
                status="failed",
                latency_ms=latency,
                message="Registry evidence was unavailable.",
                active_servers=0,
                active_tools=0,
            ),
        )


async def _service_evidence(base_url: str, service_name: str) -> ComponentEvidence:
    started = perf_counter()
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            response = await client.get(f"{base_url.rstrip('/')}/health/ready")
            response.raise_for_status()
            body = response.json()
        ready = body.get("status") in {"ok", "ready"}
        return ComponentEvidence(
            status="verified" if ready else "failed",
            latency_ms=round((perf_counter() - started) * 1000),
            message=(
                f"{service_name} returned a current readiness response."
                if ready
                else f"{service_name} did not report ready."
            ),
        )
    except Exception:
        return ComponentEvidence(
            status="failed",
            latency_ms=round((perf_counter() - started) * 1000),
            message=f"{service_name} readiness could not be verified.",
        )


async def _model_evidence(settings: Settings) -> ModelEvidence:
    started = perf_counter()
    if settings.model_api_key is None:
        return ModelEvidence(
            status="failed",
            latency_ms=0,
            message="The configured model provider has no API credential.",
            provider=settings.model_provider,
            model=settings.openai_model,
        )
    try:
        runtime = AgentRuntime()
        proof_agent = Agent(
            name="Xyena Live Proof Agent",
            model=runtime._model(),
            instructions="Return exactly XYENA_LIVE and nothing else. Do not call tools.",
        )
        result = await asyncio.wait_for(
            Runner.run(proof_agent, "Return the live proof phrase now.", max_turns=1),
            timeout=45,
        )
        output = str(result.final_output).strip()
        verified = output == "XYENA_LIVE"
        return ModelEvidence(
            status="verified" if verified else "failed",
            latency_ms=round((perf_counter() - started) * 1000),
            message=(
                "The configured model returned the expected fresh proof phrase."
                if verified
                else "The model responded, but the proof phrase did not match."
            ),
            provider=settings.model_provider,
            model=settings.openai_model,
            output=output[:120],
        )
    except Exception:
        return ModelEvidence(
            status="failed",
            latency_ms=round((perf_counter() - started) * 1000),
            message="The configured model did not complete the proof request.",
            provider=settings.model_provider,
            model=settings.openai_model,
        )


async def _guardian_trace(tenant_id: UUID, call_id: UUID) -> GuardianTrace:
    async with get_database().session(tenant_id=tenant_id, service_role="mcp") as db:
        call = await db.scalar(select(MCPToolCall).where(MCPToolCall.id == call_id))
        decision = await db.scalar(
            select(GuardianDecision)
            .where(GuardianDecision.tool_call_id == call_id)
            .order_by(GuardianDecision.created_at.desc())
            .limit(1)
        )
        authorization = await db.scalar(
            select(GuardianAuthorization)
            .where(GuardianAuthorization.tool_call_id == call_id)
            .order_by(GuardianAuthorization.created_at.desc())
            .limit(1)
        )
    return GuardianTrace(
        decision_id=decision.id if decision else None,
        outcome=decision.outcome if decision else None,
        reason_codes=list(decision.reason_codes) if decision else [],
        risk_class=decision.risk_class if decision else None,
        request_hash=call.request_hash if call else None,
        authorization_status=authorization.status if authorization else None,
    )


async def _invoke_judge_tool(
    settings: Settings,
    *,
    sequence: int,
    title: str,
    tool_name: str,
    arguments: dict[str, Any],
    run_id: UUID,
    session_id: UUID,
    user_id: UUID,
    correlation_id: UUID,
    tenant_id: UUID = _GST_TENANT_ID,
    organization_id: UUID = _GST_ORGANIZATION_ID,
    purpose: str = "judge_demo_invoice_verification",
) -> tuple[AgentTraceStep, SafeToolResult | None]:
    started_at = datetime.now(UTC)
    started = perf_counter()
    if purpose == "judge_demo_cross_platform_read":
        actor = "Xyena Supervisor"
    elif purpose == "judge_demo_live_operations_snapshot":
        actor = "Xyena Operations Supervisor"
    else:
        actor = "Xyena Invoice Agent"
    service_token = settings.service_token
    if service_token is None:
        return (
            AgentTraceStep(
                sequence=sequence,
                kind="tool",
                actor=actor,
                title=title,
                status="failed",
                started_at=started_at,
                latency_ms=0,
                tool_name=tool_name,
                input_data=arguments,
                output_data={"error": "MCP service authentication is unavailable."},
            ),
            None,
        )
    request = ToolCallSubmit(
        run_id=run_id,
        agent_name="xyena-supervisor",
        context=RuntimeContext(
            tenant_id=tenant_id,
            organization_id=organization_id,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            correlation_id=correlation_id,
            roles=("judge-demo",),
            policy_bundle_version="platform-default",
            locale="en-IN",
            timezone="Asia/Calcutta",
        ),
        intent=ToolIntent(
            requested_name=tool_name,
            arguments=arguments,
            purpose=purpose,
            resource_refs=[
                "synthetic:"
                + str(arguments.get("query") or arguments.get("invoice_id") or "gst-demo")
            ],
        ),
    )
    try:
        async with httpx.AsyncClient(base_url=str(settings.mcp_base_url), timeout=45) as client:
            response = await client.post(
                "/internal/mcp/calls",
                json=request.model_dump(mode="json"),
                headers={"Authorization": f"Bearer {service_token.get_secret_value()}"},
            )
        if response.is_error:
            body = (
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            detail = body.get("detail") if isinstance(body, dict) else None
            raise RuntimeError(str(detail or f"MCP Gateway returned HTTP {response.status_code}."))
        result = SafeToolResult.model_validate(response.json())
        guardian = await _guardian_trace(tenant_id, result.call_id)
        succeeded = result.status == "SUCCEEDED" and guardian.outcome == "ALLOW"
        step = AgentTraceStep(
            sequence=sequence,
            kind="tool",
            actor=actor,
            title=title,
            status="verified" if succeeded else "failed",
            started_at=started_at,
            latency_ms=round((perf_counter() - started) * 1000),
            tool_name=tool_name,
            call_id=result.call_id,
            input_data=arguments,
            output_data=result.model_projection
            if result.model_projection is not None
            else {"error_code": result.error_code, "error_message": result.error_message},
            provenance_hash=result.provenance_hash,
            security_flags=result.security_flags,
            guardian=guardian,
        )
        return step, result
    except Exception as exc:
        return (
            AgentTraceStep(
                sequence=sequence,
                kind="tool",
                actor=actor,
                title=title,
                status="failed",
                started_at=started_at,
                latency_ms=round((perf_counter() - started) * 1000),
                tool_name=tool_name,
                input_data=arguments,
                output_data={"error": str(exc)[:300]},
            ),
            None,
        )


async def _trace_model_summary(
    settings: Settings,
    *,
    sequence: int,
    evidence: dict[str, Any],
) -> AgentTraceStep:
    started_at = datetime.now(UTC)
    started = perf_counter()
    if settings.model_api_key is None:
        return AgentTraceStep(
            sequence=sequence,
            kind="model",
            actor="Xyena Supervisor",
            title="Synthesize the evidence",
            status="failed",
            started_at=started_at,
            latency_ms=0,
            input_data=evidence,
            output_data={"error": "The model provider is not configured."},
        )
    try:
        agent = Agent(
            name="Xyena Judge Trace Supervisor",
            model=AgentRuntime()._model(),
            instructions=(
                "Summarize the supplied synthetic evidence in one plain sentence. "
                "State whether the deterministic checks verified it and name the decisive reason. "
                "Do not authorize an action, call tools, or add facts."
            ),
        )
        result = await asyncio.wait_for(
            Runner.run(
                agent,
                "Evidence JSON:\n" + json.dumps(evidence, sort_keys=True, default=str),
                max_turns=1,
            ),
            timeout=45,
        )
        return AgentTraceStep(
            sequence=sequence,
            kind="model",
            actor="Xyena Supervisor",
            title="Synthesize the evidence",
            status="verified",
            started_at=started_at,
            latency_ms=round((perf_counter() - started) * 1000),
            input_data=evidence,
            output_data={
                "provider": settings.model_provider,
                "model": settings.openai_model,
                "summary": str(result.final_output).strip()[:800],
                "authority": "advisory-only",
            },
        )
    except Exception:
        return AgentTraceStep(
            sequence=sequence,
            kind="model",
            actor="Xyena Supervisor",
            title="Synthesize the evidence",
            status="failed",
            started_at=started_at,
            latency_ms=round((perf_counter() - started) * 1000),
            input_data=evidence,
            output_data={"error": "The model summary did not complete."},
        )


def _source_data(step: AgentTraceStep) -> dict[str, Any]:
    if not isinstance(step.output_data, dict):
        return {}
    data = step.output_data.get("data")
    return data if isinstance(data, dict) else {}


def _operation_step_has_evidence(step: AgentTraceStep) -> bool:
    """Separate a successful tool execution from a successful source-record match."""
    if step.status != "verified" or not step.tool_name:
        return False
    data = _source_data(step)
    if str(data.get("status", "")).upper() in {"NOT_FOUND", "FAILED", "ERROR"}:
        return False
    if step.tool_name == "registry.businesses.get":
        return bool(data.get("business_id") and data.get("legal_name"))
    if step.tool_name == "gst.invoices.search":
        return bool(data.get("items"))
    if step.tool_name == "erp.purchase_orders.get":
        return bool(data.get("po_number") or data.get("order_number"))
    if step.tool_name == "delivery.deliveries.find_by_invoice":
        return bool(data.get("deliveries"))
    if step.tool_name == "bank.accounts.get_balance":
        return bool(data.get("account_token") and data.get("available_balance") is not None)
    if step.tool_name == "bank.transactions.list":
        return bool(data.get("account_token") and isinstance(data.get("transactions"), list))
    return False


def _calculate_trace_risk(steps: list[AgentTraceStep]) -> TraceRiskAssessment:
    """Produce an explainable risk score from recorded policy evidence, never model output."""
    risk_weights = {"READ": 5, "SENSITIVE_READ": 15, "MUTATE": 45, "PRIVILEGED": 75}
    outcome_modifiers = {"ALLOW": 0, "VERIFY": 8, "ESCALATE": 20, "BLOCK": 40}
    expected_demo_flags = {"SYNTHETIC_DATA", "EXTERNAL_EVIDENCE"}
    tools: list[ToolRiskEvidence] = []
    platforms: set[str] = set()
    for step in steps:
        if step.kind != "tool" or step.tool_name is None:
            continue
        platform = step.tool_name.split(".", 1)[0]
        platforms.add(platform)
        risk_class = step.guardian.risk_class if step.guardian else "UNKNOWN"
        guardian_outcome = step.guardian.outcome if step.guardian else "MISSING"
        unexpected_flags = sorted(set(step.security_flags) - expected_demo_flags)
        registered_risk_points = risk_weights.get(risk_class or "UNKNOWN", 90)
        guardian_points = outcome_modifiers.get(guardian_outcome or "MISSING", 40)
        execution_points = 15 if step.status != "verified" else 0
        security_points = min(15, len(unexpected_flags) * 5)
        tools.append(
            ToolRiskEvidence(
                tool_name=step.tool_name,
                platform=platform,
                risk_class=risk_class or "UNKNOWN",
                registered_risk_points=registered_risk_points,
                guardian_outcome=guardian_outcome or "MISSING",
                guardian_points=guardian_points,
                execution_points=execution_points,
                security_points=security_points,
                subtotal=min(
                    100,
                    registered_risk_points
                    + guardian_points
                    + execution_points
                    + security_points,
                ),
                unexpected_security_flags=unexpected_flags,
                execution_status=step.status,
            )
        )

    highest_tool_subtotal = max((item.subtotal for item in tools), default=100)
    cross_platform_breadth = min(10, max(0, len(platforms) - 1) * 2)
    call_volume = min(5, max(0, len(tools) - 3))
    protected_read_reduction = 0
    if tools and all(
        item.risk_class in {"READ", "SENSITIVE_READ"}
        and item.guardian_outcome == "ALLOW"
        and item.execution_status == "verified"
        and not item.unexpected_security_flags
        for item in tools
    ):
        protected_read_reduction = -5

    calculation = {
        "highest_tool_subtotal": highest_tool_subtotal,
        "cross_platform_breadth": cross_platform_breadth,
        "call_volume": call_volume,
        "protected_read_reduction": protected_read_reduction,
    }
    score = max(0, min(100, sum(calculation.values())))
    if score <= 24:
        band, policy_action = "LOW", "Allow within the registered read-only scope"
    elif score <= 49:
        band, policy_action = "GUARDED", "Require additional deterministic verification"
    elif score <= 74:
        band, policy_action = "HIGH", "Escalate for human approval before execution"
    else:
        band, policy_action = "CRITICAL", "Block execution until risk is resolved"
    return TraceRiskAssessment(
        score=score,
        band=band,
        policy_action=policy_action,
        calculation=calculation,
        tools=tools,
        explanation=(
            "Each tool subtotal = registered risk + Guardian + execution + security points. "
            "Final score = highest tool subtotal + platform breadth + call volume, then a "
            "five-point reduction only when every call is an allowed successful read."
        ),
    )


def _pdf_object(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def _pdf_structure(reader: PdfReader) -> PdfStructureEvidence:
    root = _pdf_object(reader.trailer.get("/Root")) or {}
    names = _pdf_object(root.get("/Names")) or {}
    has_open_action = "/OpenAction" in root
    has_additional_actions = "/AA" in root
    has_javascript = "/JavaScript" in names
    has_embedded_files = "/EmbeddedFiles" in names
    annotation_count = 0
    for page in reader.pages:
        page_object = _pdf_object(page)
        annotations = _pdf_object(page_object.get("/Annots")) or []
        annotation_count += len(annotations)
        has_additional_actions = has_additional_actions or "/AA" in page_object
    return PdfStructureEvidence(
        encrypted=reader.is_encrypted,
        has_open_action=has_open_action,
        has_additional_actions=has_additional_actions,
        has_javascript=has_javascript,
        has_embedded_files=has_embedded_files,
        annotation_count=annotation_count,
    )


def _scan_pdf_document(payload: bytes, file_name: str) -> PdfScanReport:
    try:
        reader = PdfReader(BytesIO(payload), strict=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is not a readable PDF document.",
        ) from exc
    if len(reader.pages) > _maximum_pdf_pages:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"The judge scanner accepts at most {_maximum_pdf_pages} PDF pages.",
        )

    structure = _pdf_structure(reader)
    page_text: list[tuple[int, str]] = []
    if not structure.encrypted:
        remaining = _maximum_extracted_characters
        for page_number, page in enumerate(reader.pages, start=1):
            if remaining <= 0:
                break
            try:
                extracted = (page.extract_text() or "")[:remaining]
            except Exception:
                extracted = ""
            page_text.append((page_number, extracted))
            remaining -= len(extracted)

    metadata_text = ""
    if reader.metadata:
        metadata_text = " ".join(str(value) for value in reader.metadata.values() if value)
    findings: list[PdfThreatFinding] = []
    for category, severity, expression in _INJECTION_PATTERNS:
        pattern = re.compile(expression, re.IGNORECASE | re.DOTALL)
        sources: list[tuple[int | None, str]] = [
            (page, text_value) for page, text_value in page_text
        ]
        if metadata_text:
            sources.append((None, metadata_text))
        for page_number, source in sources:
            match = pattern.search(source)
            if match is None:
                continue
            start = max(0, match.start() - 55)
            end = min(len(source), match.end() + 85)
            snippet = re.sub(r"\s+", " ", source[start:end]).strip()
            findings.append(
                PdfThreatFinding(
                    category=category,
                    severity=severity,
                    page=page_number,
                    snippet=snippet[:240],
                )
            )

    structural_reasons: list[str] = []
    if structure.encrypted:
        structural_reasons.append("ENCRYPTED_DOCUMENT")
    if structure.has_javascript:
        structural_reasons.append("EMBEDDED_JAVASCRIPT")
    if structure.has_open_action:
        structural_reasons.append("AUTOMATIC_OPEN_ACTION")
    if structure.has_additional_actions:
        structural_reasons.append("ADDITIONAL_PDF_ACTIONS")
    if structure.has_embedded_files:
        structural_reasons.append("EMBEDDED_FILES")
    injection_reasons = list(dict.fromkeys(item.category.upper() for item in findings))
    reason_codes = [*injection_reasons, *structural_reasons]
    score_weights = {"medium": 10, "high": 20, "critical": 35}
    risk_score = min(100, sum(score_weights[item.severity] for item in findings))
    risk_score = min(100, risk_score + (15 * len(structural_reasons)))
    if findings:
        classification = "BLOCKED_PROMPT_INJECTION"
    elif structural_reasons:
        classification = "REVIEW_REQUIRED"
    else:
        classification = "NO_INJECTION_FOUND"
    combined_text = "\n\n".join(text_value for _, text_value in page_text)
    preview = re.sub(r"[ \t]+", " ", combined_text).strip()[:1400]
    return PdfScanReport(
        scan_id=uuid4(),
        file_name=file_name,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        page_count=len(reader.pages),
        classification=classification,
        flagged=classification != "NO_INJECTION_FOUND",
        risk_score=risk_score,
        reason_codes=reason_codes,
        findings=findings,
        structure=structure,
        extracted_preview=preview,
        document_verification=(
            "BLOCKED" if classification != "NO_INJECTION_FOUND" else "NOT_CHECKED"
        ),
        claim_checks={
            "explicit_verification_required": True,
            "intake_decision": "INDEPENDENT_SOURCE_VERIFICATION_REQUIRED",
        },
        scanned_at=datetime.now(UTC),
        handling=(
            "Document quarantined from agent instructions and authorization context."
            if findings
            else "Document contains no detected injection; source verification is still required."
        ),
    )


def _extract_invoice_claims(text_value: str) -> dict[str, str]:
    patterns = {
        "invoice_number": r"Invoice reference\s+([A-Z0-9/-]+)",
        "buyer_gstin": r"Buyer GSTIN\s+([A-Z0-9]{15})",
        "claimed_status": r"Claimed status\s+([A-Z_]+)",
        "claimed_total": r"Invoice total\s+(?:INR|Rs\.?|₹)?\s*([0-9,]+\.\d{2})",
    }
    claims: dict[str, str] = {}
    for key, expression in patterns.items():
        match = re.search(expression, text_value, re.IGNORECASE)
        if match:
            claims[key] = match.group(1).replace(",", "").upper()
    return claims


@router.post(
    "/live-proof",
    operation_id="create_live_demo_proof",
    response_model=LiveProof,
    summary="Create a read-only proof that the live platform is connected",
)
async def create_live_proof(
    settings: Settings = Depends(_authorize_demo),  # noqa: B008 - FastAPI dependency declaration
) -> LiveProof:
    global _last_proof_at

    async with _proof_lock:
        elapsed = monotonic() - _last_proof_at
        if elapsed < _minimum_interval_seconds:
            retry_after = max(1, round(_minimum_interval_seconds - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="A live proof was generated recently.",
                headers={"Retry-After": str(retry_after)},
            )
        _last_proof_at = monotonic()

    started = perf_counter()
    database_task = _database_and_registry_evidence()
    mcp_task = _service_evidence(str(settings.mcp_base_url), "MCP Gateway")
    guardian_task = _service_evidence(str(settings.guardian_base_url), "Guardian")
    model_task = _model_evidence(settings)
    (database, registry), mcp_gateway, guardian, model = await asyncio.gather(
        database_task,
        mcp_task,
        guardian_task,
        model_task,
    )
    components = (database, registry, mcp_gateway, guardian, model)
    proof_status = (
        "verified" if all(item.status == "verified" for item in components) else "degraded"
    )
    return LiveProof(
        proof_id=uuid4(),
        status=proof_status,
        checked_at=datetime.now(UTC),
        duration_ms=round((perf_counter() - started) * 1000),
        database=database,
        registry=registry,
        mcp_gateway=mcp_gateway,
        guardian=guardian,
        model=model,
    )


@router.post(
    "/scan-pdf",
    operation_id="scan_judge_pdf_for_prompt_injection",
    response_model=PdfScanReport,
    summary="Inspect invoice evidence and independently verify safe claims through GST MCP",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/pdf": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                        "maxLength": _maximum_pdf_bytes,
                    }
                }
            },
        }
    },
)
async def scan_judge_pdf(
    request: Request,
    file_name_header: str | None = Header(default=None, alias="X-File-Name"),
    settings: Settings = Depends(_authorize_demo),  # noqa: B008 - FastAPI dependency declaration
) -> PdfScanReport:
    global _last_pdf_scan_at

    async with _pdf_scan_lock:
        elapsed = monotonic() - _last_pdf_scan_at
        if elapsed < _pdf_scan_interval_seconds:
            retry_after = max(1, round(_pdf_scan_interval_seconds - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="A PDF scan was generated recently.",
                headers={"Retry-After": str(retry_after)},
            )
        _last_pdf_scan_at = monotonic()

    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload one PDF using application/pdf.",
        )
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > _maximum_pdf_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The judge scanner accepts PDF files up to 2 MB.",
            )
        payload.extend(chunk)
    if not payload.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded content does not have a PDF signature.",
        )
    decoded_name = unquote(file_name_header or "judge-upload.pdf")
    safe_name = decoded_name.replace("\\", "/").rsplit("/", 1)[-1][:120]
    if not safe_name.lower().endswith(".pdf"):
        safe_name = f"{safe_name}.pdf"
    report = _scan_pdf_document(bytes(payload), safe_name)
    if report.flagged:
        return report

    claims = _extract_invoice_claims(report.extracted_preview)
    intake_evidence = {
        "explicit_verification_required": True,
        "intake_decision": "INDEPENDENT_SOURCE_VERIFICATION_REQUIRED",
    }
    required_claims = {"invoice_number", "buyer_gstin", "claimed_status", "claimed_total"}
    missing_claims = sorted(required_claims - set(claims))
    if missing_claims:
        return report.model_copy(
            update={
                "classification": "REVIEW_REQUIRED",
                "flagged": True,
                "risk_score": 35,
                "reason_codes": ["INVOICE_CLAIMS_INCOMPLETE"],
                "document_verification": "NOT_CHECKED",
                "claim_checks": {
                    **intake_evidence,
                    "claims": claims,
                    "missing_fields": missing_claims,
                },
                "handling": "Clean document, but required invoice claims could not be extracted.",
            }
        )

    correlation_id = uuid4()
    run_id = uuid4()
    session_id = uuid4()
    user_id = _SHARED_DEMO_USER_ID
    tool_steps: list[AgentTraceStep] = []
    search_step, search_result = await _invoke_judge_tool(
        settings,
        sequence=1,
        title="Find the authoritative GST invoice",
        tool_name="gst.invoices.search",
        arguments={
            "query": claims["invoice_number"],
            "status": claims["claimed_status"],
            "limit": 5,
        },
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
        purpose="judge_demo_document_claim_verification",
    )
    tool_steps.append(search_step)
    items = _source_data(search_step).get("items", [])
    if (
        search_result is None
        or search_step.status != "verified"
        or not isinstance(items, list)
        or not items
        or not isinstance(items[0], dict)
    ):
        return report.model_copy(
            update={
                "classification": "REVIEW_REQUIRED",
                "flagged": True,
                "risk_score": 45,
                "reason_codes": ["AUTHORITATIVE_INVOICE_NOT_FOUND"],
                "claim_checks": {
                    **intake_evidence,
                    "claims": claims,
                    "source_match": False,
                },
                "tool_steps": tool_steps,
                "tool_calls_executed": len(tool_steps),
                "handling": "Document was clean, but its invoice reference could not be verified.",
            }
        )

    invoice_id = str(items[0].get("id", ""))
    verify_step, verify_result = await _invoke_judge_tool(
        settings,
        sequence=2,
        title="Compare document claims with GST source",
        tool_name="gst.invoices.verify",
        arguments={
            "invoice_id": invoice_id,
            "claimed_total": claims["claimed_total"],
            "claimed_buyer_gstin": claims["buyer_gstin"],
            "claimed_status": claims["claimed_status"],
        },
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
        purpose="judge_demo_document_claim_verification",
    )
    tool_steps.append(verify_step)
    verification = _source_data(verify_step)
    if verify_result is None or verify_step.status != "verified":
        return report.model_copy(
            update={
                "classification": "REVIEW_REQUIRED",
                "flagged": True,
                "risk_score": 45,
                "reason_codes": ["GST_CLAIM_CHECK_FAILED"],
                "claim_checks": {
                    **intake_evidence,
                    "claims": claims,
                    "source_match": False,
                },
                "tool_steps": tool_steps,
                "tool_calls_executed": len(tool_steps),
                "handling": "The GST comparison did not complete; the document remains unverified.",
            }
        )

    comparisons = verification.get("comparisons", {})
    verified = verification.get("verified") is True
    mismatch_codes = [
        f"{str(name).upper()}_MISMATCH"
        for name, comparison in comparisons.items()
        if isinstance(comparison, dict) and comparison.get("match") is not True
    ]
    return report.model_copy(
        update={
            "classification": "VERIFIED_SOURCE_MATCH" if verified else "AMOUNT_MISMATCH",
            "flagged": not verified,
            "risk_score": 0 if verified else 70,
            "reason_codes": [] if verified else mismatch_codes or ["DOCUMENT_CLAIM_MISMATCH"],
            "document_verification": "SOURCE_MATCH" if verified else "SOURCE_MISMATCH",
            "claim_checks": {
                **intake_evidence,
                "claims": claims,
                "invoice_id": invoice_id,
                "comparisons": comparisons,
                "source_match": verified,
            },
            "tool_steps": tool_steps,
            "tool_calls_executed": len(tool_steps),
            "handling": (
                "Document claims matched the independently retrieved GST source."
                if verified
                else "Document claims disagree with the independently retrieved GST source."
            ),
        }
    )


@router.post(
    "/operations-snapshot",
    operation_id="create_live_operations_snapshot",
    response_model=OperationsSnapshot,
    summary="Read the judge-selected business workflow from five Guardian-governed MCP platforms",
)
async def create_operations_snapshot(
    body: OperationsSnapshotRequest,
    settings: Settings = Depends(_authorize_demo),  # noqa: B008 - FastAPI dependency declaration
) -> OperationsSnapshot:
    global _last_operations_at

    async with _operations_lock:
        elapsed = monotonic() - _last_operations_at
        if elapsed < _operations_interval_seconds:
            retry_after = max(1, round(_operations_interval_seconds - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="A live operations snapshot was generated recently.",
                headers={"Retry-After": str(retry_after)},
            )
        _last_operations_at = monotonic()

    started_at = datetime.now(UTC)
    started = perf_counter()
    correlation_id = uuid4()
    run_id = uuid4()
    session_id = uuid4()
    user_id = _SHARED_DEMO_USER_ID
    steps: list[AgentTraceStep] = []
    today = date.today()
    requests = [
        {
            "title": "Read the business registry record",
            "tool_name": "registry.businesses.get",
            "arguments": {"identifier": body.registry_identifier.strip()},
            "tenant_id": _REGISTRY_TENANT_ID,
            "organization_id": _REGISTRY_ORGANIZATION_ID,
        },
        {
            "title": "Search the GST invoice register",
            "tool_name": "gst.invoices.search",
            "arguments": {
                "query": body.gst_invoice_number.strip(),
                "status": body.gst_status.strip().upper(),
                "limit": 5,
            },
            "tenant_id": _GST_TENANT_ID,
            "organization_id": _GST_ORGANIZATION_ID,
        },
        {
            "title": "Read the buyer purchase order",
            "tool_name": "erp.purchase_orders.get",
            "arguments": {"order_id_or_number": body.erp_order_reference.strip()},
            "tenant_id": _SHARED_DEMO_TENANT_ID,
            "organization_id": _SHARED_DEMO_ORGANIZATION_ID,
        },
        {
            "title": "Read the current delivery status",
            "tool_name": "delivery.deliveries.find_by_invoice",
            "arguments": {
                "invoice_id": None,
                "seller_id": body.delivery_seller_id.strip(),
                "invoice_number": body.delivery_invoice_number.strip(),
            },
            "tenant_id": _SHARED_DEMO_TENANT_ID,
            "organization_id": _SHARED_DEMO_ORGANIZATION_ID,
        },
        {
            "title": "Read the live bank balance",
            "tool_name": "bank.accounts.get_balance",
            "arguments": {"account_token": body.bank_account_token.strip()},
            "tenant_id": _SHARED_DEMO_TENANT_ID,
            "organization_id": _SHARED_DEMO_ORGANIZATION_ID,
        },
        {
            "title": "Read recent bank credits and debits",
            "tool_name": "bank.transactions.list",
            "arguments": {
                "account_token": body.bank_account_token.strip(),
                "from_date": (today - timedelta(days=30)).isoformat(),
                "to_date": today.isoformat(),
                "limit": 20,
            },
            "tenant_id": _SHARED_DEMO_TENANT_ID,
            "organization_id": _SHARED_DEMO_ORGANIZATION_ID,
        },
    ]
    for sequence, tool_request in enumerate(requests, start=1):
        step, _ = await _invoke_judge_tool(
            settings,
            sequence=sequence,
            title=str(tool_request["title"]),
            tool_name=str(tool_request["tool_name"]),
            arguments=dict(tool_request["arguments"]),
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            correlation_id=correlation_id,
            tenant_id=tool_request["tenant_id"],
            organization_id=tool_request["organization_id"],
            purpose="judge_demo_live_operations_snapshot",
        )
        steps.append(step)

    successful_calls = sum(step.status == "verified" for step in steps)
    evidence_matches = {
        str(step.tool_name): _operation_step_has_evidence(step)
        for step in steps
        if step.tool_name
    }
    evidence_matched_calls = sum(evidence_matches.values())
    evidence_complete = evidence_matched_calls == len(steps)
    overall_status: Literal["verified", "partial", "failed"]
    if evidence_complete:
        overall_status = "verified"
    elif evidence_matched_calls:
        overall_status = "partial"
    else:
        overall_status = "failed"
    completed_at = datetime.now(UTC)
    return OperationsSnapshot(
        snapshot_id=uuid4(),
        correlation_id=correlation_id,
        status=overall_status,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=round((perf_counter() - started) * 1000),
        inputs={key: str(value) for key, value in body.model_dump().items()},
        steps=steps,
        successful_calls=successful_calls,
        total_calls=len(steps),
        evidence_matched_calls=evidence_matched_calls,
        evidence_matches=evidence_matches,
        evidence_complete=evidence_complete,
        funding_gate=(
            "READ_ONLY_EVIDENCE_COMPLETE" if evidence_complete else "BLOCKED_MISSING_EVIDENCE"
        ),
        source_apps={
            "registry": "https://registry.gowshik.in/businesses",
            "gst": "https://gst.gowshik.in/invoices",
            "erp": "https://erp.gowshik.in/purchase-orders",
            "delivery": "https://delivery.gowshik.in/deliveries",
            "bank": "https://bank.gowshik.in/transactions",
        },
    )


@router.post(
    "/judge-trace",
    operation_id="create_judge_agent_trace",
    response_model=JudgeTrace,
    summary="Run a synthetic read-only invoice verification through Xyena, Guardian, and MCP",
)
async def create_judge_trace(
    body: JudgeTraceRequest,
    settings: Settings = Depends(_authorize_demo),  # noqa: B008 - FastAPI dependency declaration
) -> JudgeTrace:
    global _last_trace_at

    async with _trace_lock:
        elapsed = monotonic() - _last_trace_at
        if elapsed < _trace_interval_seconds:
            retry_after = max(1, round(_trace_interval_seconds - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="A judge trace was generated recently.",
                headers={"Retry-After": str(retry_after)},
            )
        _last_trace_at = monotonic()

    trace_id = uuid4()
    correlation_id = uuid4()
    run_id = uuid4()
    session_id = uuid4()
    user_id = _SHARED_DEMO_USER_ID
    started_at = datetime.now(UTC)
    started = perf_counter()
    scenario = _JUDGE_SCENARIOS[body.scenario]
    steps: list[AgentTraceStep] = []

    def finish_error(message: str, reason: str) -> JudgeTrace:
        completed_at = datetime.now(UTC)
        steps.append(
            AgentTraceStep(
                sequence=len(steps) + 1,
                kind="decision",
                actor="Deterministic Verification Policy",
                title="Issue the verification result",
                status="failed",
                started_at=completed_at,
                latency_ms=0,
                input_data={
                    "completed_tool_calls": len([item for item in steps if item.kind == "tool"])
                },
                output_data={"verified": False, "reason_codes": [reason], "message": message},
            )
        )
        return JudgeTrace(
            trace_id=trace_id,
            correlation_id=correlation_id,
            scenario=body.scenario,
            scenario_label=scenario["label"],
            subject={"invoice_number": scenario["invoice_number"], "source": "synthetic-gst"},
            status="error",
            verified=False,
            reason_codes=[reason],
            summary=message,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round((perf_counter() - started) * 1000),
            risk=_calculate_trace_risk(steps),
            steps=steps,
        )

    if body.scenario == "platform_network":
        platform_calls = [
            {
                "title": "Verify the supplier in Business Registry",
                "tool_name": "registry.businesses.verify",
                "arguments": {
                    "identifier": "29ABCDE1234F1Z5",
                    "claimed_legal_name": "Kaveri Precision Components Private Limited",
                    "claimed_gstin": "29ABCDE1234F1Z5",
                    "claimed_status": "ACTIVE",
                },
                "tenant_id": _REGISTRY_TENANT_ID,
                "organization_id": _REGISTRY_ORGANIZATION_ID,
            },
            {
                "title": "Read the registered GST invoice",
                "tool_name": "gst.invoices.search",
                "arguments": {"query": "MICRO/26/101", "status": "REGISTERED", "limit": 1},
                "tenant_id": _GST_TENANT_ID,
                "organization_id": _GST_ORGANIZATION_ID,
            },
            {
                "title": "Read the buyer purchase order",
                "tool_name": "erp.purchase_orders.get",
                "arguments": {"order_id_or_number": "PO-1007"},
                "tenant_id": _SHARED_DEMO_TENANT_ID,
                "organization_id": _SHARED_DEMO_ORGANIZATION_ID,
            },
            {
                "title": "Read delivery and tracking evidence",
                "tool_name": "delivery.deliveries.find_by_invoice",
                "arguments": {"invoice_id": "INV-2023-0001"},
                "tenant_id": _SHARED_DEMO_TENANT_ID,
                "organization_id": _SHARED_DEMO_ORGANIZATION_ID,
            },
            {
                "title": "List tokenized bank accounts",
                "tool_name": "bank.accounts.list",
                "arguments": {},
                "tenant_id": _SHARED_DEMO_TENANT_ID,
                "organization_id": _SHARED_DEMO_ORGANIZATION_ID,
            },
            {
                "title": "Read the ledger clearing balance",
                "tool_name": "ledger.accounts.get_balance",
                "arguments": {"account_id": "ledger_cash_clearing"},
                "tenant_id": _SHARED_DEMO_TENANT_ID,
                "organization_id": _SHARED_DEMO_ORGANIZATION_ID,
            },
        ]
        for sequence, call in enumerate(platform_calls, start=1):
            step, _ = await _invoke_judge_tool(
                settings,
                sequence=sequence,
                title=str(call["title"]),
                tool_name=str(call["tool_name"]),
                arguments=dict(call["arguments"]),
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                correlation_id=correlation_id,
                tenant_id=call["tenant_id"],
                organization_id=call["organization_id"],
                purpose="judge_demo_cross_platform_read",
            )
            steps.append(step)

        checks = {
            "six_independent_mcp_sources_called": len(steps) == len(platform_calls),
            "guardian_allowed_every_tool": all(
                item.guardian is not None and item.guardian.outcome == "ALLOW" for item in steps
            ),
            "all_mcp_calls_succeeded": all(item.status == "verified" for item in steps),
            "only_read_tools_used": all(
                item.tool_name
                in {
                    "registry.businesses.verify",
                    "gst.invoices.search",
                    "erp.purchase_orders.get",
                    "delivery.deliveries.find_by_invoice",
                    "bank.accounts.list",
                    "ledger.accounts.get_balance",
                }
                for item in steps
            ),
        }
        reason_codes: list[str] = []
        if not checks["six_independent_mcp_sources_called"]:
            reason_codes.append("PLATFORM_SOURCE_MISSING")
        if not checks["guardian_allowed_every_tool"]:
            reason_codes.append("GUARDIAN_NOT_ALLOWED")
        if not checks["all_mcp_calls_succeeded"]:
            reason_codes.append("MCP_CALL_FAILED")
        if not checks["only_read_tools_used"]:
            reason_codes.append("NON_READ_TOOL_REQUESTED")
        verified = not reason_codes

        model_step = await _trace_model_summary(
            settings,
            sequence=len(steps) + 1,
            evidence={
                "scenario": scenario["label"],
                "platforms": ["registry", "gst", "erp", "delivery", "bank", "ledger"],
                "checks": checks,
                "verified": verified,
                "reason_codes": reason_codes,
            },
        )
        steps.append(model_step)
        model_summary = (
            model_step.output_data.get("summary")
            if isinstance(model_step.output_data, dict)
            else None
        )
        summary = str(
            model_summary
            or (
                "Six independent MCP platforms returned governed read-only evidence."
                if verified
                else "One or more platform evidence calls did not complete or pass Guardian."
            )
        )
        decision_at = datetime.now(UTC)
        steps.append(
            AgentTraceStep(
                sequence=len(steps) + 1,
                kind="decision",
                actor="Deterministic Verification Policy",
                title="Issue the network proof result",
                status="verified" if verified else "failed",
                started_at=decision_at,
                latency_ms=0,
                input_data={"checks": checks},
                output_data={
                    "verified": verified,
                    "reason_codes": reason_codes,
                    "model_authority": "advisory-only",
                    "state_changed": False,
                    "audit_records_created": True,
                },
            )
        )
        completed_at = datetime.now(UTC)
        return JudgeTrace(
            trace_id=trace_id,
            correlation_id=correlation_id,
            scenario=body.scenario,
            scenario_label=scenario["label"],
            subject={
                "reference": "NETWORK/READ-ONLY",
                "source": "six-independent-mcp-platforms",
            },
            status="verified" if verified else "not_verified",
            verified=verified,
            reason_codes=reason_codes,
            summary=summary,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round((perf_counter() - started) * 1000),
            risk=_calculate_trace_risk(steps),
            steps=steps,
        )

    sequence = 1
    search_step, search_result = await _invoke_judge_tool(
        settings,
        sequence=sequence,
        title="Locate the source invoice",
        tool_name="gst.invoices.search",
        arguments={
            "query": scenario["invoice_number"],
            "status": scenario["search_status"],
            "limit": 5,
        },
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
    )
    steps.append(search_step)
    if search_result is None or search_step.status == "failed":
        return finish_error("The invoice search tool did not complete.", "INVOICE_SEARCH_FAILED")
    items = _source_data(search_step).get("items", [])
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return finish_error("No source invoice matched the selected scenario.", "INVOICE_NOT_FOUND")
    invoice_id = str(items[0].get("id", ""))
    if not invoice_id:
        return finish_error(
            "The source invoice did not include an identifier.", "INVOICE_ID_MISSING"
        )

    sequence += 1
    invoice_step, invoice_result = await _invoke_judge_tool(
        settings,
        sequence=sequence,
        title="Fetch the authoritative invoice",
        tool_name="gst.invoices.get",
        arguments={"invoice_id": invoice_id},
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
    )
    steps.append(invoice_step)
    if invoice_result is None or invoice_step.status == "failed":
        return finish_error(
            "The authoritative invoice could not be retrieved.", "INVOICE_FETCH_FAILED"
        )
    invoice = _source_data(invoice_step)
    seller_gstin = str(invoice.get("seller_gstin", ""))
    if not seller_gstin:
        return finish_error(
            "The source invoice did not include the seller GSTIN.", "SELLER_GSTIN_MISSING"
        )

    sequence += 1
    verify_step, verify_result = await _invoke_judge_tool(
        settings,
        sequence=sequence,
        title="Compare the submitted claim",
        tool_name="gst.invoices.verify",
        arguments={
            "invoice_id": invoice_id,
            "claimed_total": scenario["claimed_total"],
            "claimed_buyer_gstin": scenario["claimed_buyer_gstin"],
            "claimed_status": scenario["claimed_status"],
        },
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
    )
    steps.append(verify_step)
    if verify_result is None or verify_step.status == "failed":
        return finish_error(
            "The invoice comparison tool did not complete.", "INVOICE_VERIFY_FAILED"
        )

    sequence += 1
    registration_step, registration_result = await _invoke_judge_tool(
        settings,
        sequence=sequence,
        title="Verify the seller registration",
        tool_name="gst.registrations.verify",
        arguments={"gstin": seller_gstin},
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
    )
    steps.append(registration_step)
    if registration_result is None or registration_step.status == "failed":
        return finish_error(
            "The GST registration tool did not complete.", "REGISTRATION_VERIFY_FAILED"
        )

    sequence += 1
    classification_step, classification_result = await _invoke_judge_tool(
        settings,
        sequence=sequence,
        title="Verify the MSME classification",
        tool_name="gst.enterprises.get_classification",
        arguments={},
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
    )
    steps.append(classification_step)
    if classification_result is None or classification_step.status == "failed":
        return finish_error(
            "The MSME classification tool did not complete.", "CLASSIFICATION_FAILED"
        )

    verification = _source_data(verify_step)
    registration = _source_data(registration_step)
    classification = _source_data(classification_step)
    checks = {
        "claim_fields_match": verification.get("verified") is True,
        "invoice_is_registered": verification.get("eligible_registered_invoice") is True,
        "seller_registration_active": registration.get("active_match") is True,
        "msme_classification_verified": classification.get("verification_status") == "VERIFIED",
        "guardian_allowed_every_tool": all(
            item.guardian is not None and item.guardian.outcome == "ALLOW"
            for item in steps
            if item.kind == "tool"
        ),
        "all_mcp_calls_succeeded": all(
            item.status == "verified" for item in steps if item.kind == "tool"
        ),
    }
    reason_codes: list[str] = []
    if not checks["claim_fields_match"]:
        reason_codes.append("CLAIM_MISMATCH")
    if not checks["invoice_is_registered"]:
        reason_codes.append("INVOICE_NOT_REGISTERED")
    if not checks["seller_registration_active"]:
        reason_codes.append("SELLER_REGISTRATION_INACTIVE")
    if not checks["msme_classification_verified"]:
        reason_codes.append("MSME_CLASSIFICATION_UNVERIFIED")
    if not checks["guardian_allowed_every_tool"]:
        reason_codes.append("GUARDIAN_NOT_ALLOWED")
    if not checks["all_mcp_calls_succeeded"]:
        reason_codes.append("MCP_CALL_FAILED")
    verified = not reason_codes

    sequence += 1
    model_step = await _trace_model_summary(
        settings,
        sequence=sequence,
        evidence={
            "invoice_number": scenario["invoice_number"],
            "scenario": scenario["label"],
            "checks": checks,
            "verified": verified,
            "reason_codes": reason_codes,
        },
    )
    steps.append(model_step)
    model_summary = (
        model_step.output_data.get("summary") if isinstance(model_step.output_data, dict) else None
    )
    summary = str(
        model_summary
        or (
            "All deterministic source, policy, and claim checks passed."
            if verified
            else "The deterministic verification found one or more exceptions."
        )
    )

    sequence += 1
    decision_at = datetime.now(UTC)
    steps.append(
        AgentTraceStep(
            sequence=sequence,
            kind="decision",
            actor="Deterministic Verification Policy",
            title="Issue the verification result",
            status="verified" if verified else "failed",
            started_at=decision_at,
            latency_ms=0,
            input_data={"checks": checks},
            output_data={
                "verified": verified,
                "reason_codes": reason_codes,
                "model_authority": "advisory-only",
                "state_changed": False,
                "audit_records_created": True,
            },
        )
    )
    completed_at = datetime.now(UTC)
    return JudgeTrace(
        trace_id=trace_id,
        correlation_id=correlation_id,
        scenario=body.scenario,
        scenario_label=scenario["label"],
        subject={"invoice_number": scenario["invoice_number"], "source": "synthetic-gst"},
        status="verified" if verified else "not_verified",
        verified=verified,
        reason_codes=reason_codes,
        summary=summary,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=round((perf_counter() - started) * 1000),
        risk=_calculate_trace_risk(steps),
        steps=steps,
    )
