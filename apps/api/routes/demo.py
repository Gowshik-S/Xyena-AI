import asyncio
import secrets
from datetime import UTC, datetime
from time import monotonic, perf_counter
from typing import Literal
from uuid import UUID, uuid4

import httpx
from agents import Agent, Runner
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select, text

from packages.agents import AgentRuntime
from packages.config import Settings, get_settings
from packages.contracts.common import ContractModel
from packages.persistence import get_database
from packages.persistence.models.mcp import MCPServer, MCPTool

router = APIRouter(prefix="/demo", tags=["Live demo"])

_proof_lock = asyncio.Lock()
_last_proof_at = 0.0
_minimum_interval_seconds = 10


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


def _authorize_demo(
    token: str | None = Header(default=None, alias="X-Demo-Token"),
    settings: Settings = Depends(get_settings),
) -> Settings:
    if not settings.live_demo_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Live demo is disabled.")
    configured = settings.live_demo_token
    if configured is None or token is None or not secrets.compare_digest(
        token, configured.get_secret_value()
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


@router.post(
    "/live-proof",
    operation_id="create_live_demo_proof",
    response_model=LiveProof,
    summary="Create a read-only proof that the live platform is connected",
)
async def create_live_proof(settings: Settings = Depends(_authorize_demo)) -> LiveProof:
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
    proof_status = "verified" if all(item.status == "verified" for item in components) else "degraded"
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
