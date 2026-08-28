import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from apps.api.dependencies import get_correlation_id, get_principal, get_scoped_session
from packages.audit import append_audit_event
from packages.config import get_settings
from packages.contracts.agent import RunEvent, RunView
from packages.contracts.identity import AuthenticatedPrincipal
from packages.persistence import get_database
from packages.persistence.models.agent import AgentRun, AgentRunEvent

router = APIRouter(prefix="/api/v1/runs", tags=["Runs"])
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED", "BLOCKED"}


async def _get_run(db: AsyncSession, principal: AuthenticatedPrincipal, run_id: UUID) -> AgentRun:
    run = await db.scalar(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == principal.tenant_id,
            AgentRun.user_id == principal.user_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}", operation_id="runs_get", response_model=RunView)
async def get_run(
    run_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> RunView:
    return RunView.model_validate(await _get_run(db, principal, run_id))


@router.post("/{run_id}/cancel", operation_id="runs_cancel", response_model=RunView)
async def cancel_run(
    run_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> RunView:
    run = await _get_run(db, principal, run_id)
    if run.status in TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="Run is already terminal")
    run.status = "CANCELLED"
    run.version += 1
    await append_audit_event(
        db,
        tenant_id=principal.tenant_id,
        actor_type="USER",
        actor_id=str(principal.user_id),
        event_type="agent.run.cancelled",
        subject_type="agent_run",
        subject_id=run.id,
        correlation_id=correlation_id,
    )
    await db.flush()
    return RunView.model_validate(run)


@router.get("/{run_id}/events", operation_id="run_events_stream")
async def stream_run_events(
    run_id: UUID,
    after_sequence: int = Query(default=0, ge=0),
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> EventSourceResponse:
    await _get_run(db, principal, run_id)
    return EventSourceResponse(_event_stream(principal, run_id, after_sequence))


async def _event_stream(
    principal: AuthenticatedPrincipal, run_id: UUID, after_sequence: int
) -> AsyncIterator[dict[str, str]]:
    database = get_database()
    last_sequence = after_sequence
    while True:
        async with database.session(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            service_role="api-stream",
        ) as db:
            events = list(
                await db.scalars(
                    select(AgentRunEvent)
                    .where(
                        AgentRunEvent.run_id == run_id,
                        AgentRunEvent.tenant_id == principal.tenant_id,
                        AgentRunEvent.sequence > last_sequence,
                    )
                    .order_by(AgentRunEvent.sequence.asc())
                )
            )
            run_status = await db.scalar(
                select(AgentRun.status).where(
                    AgentRun.id == run_id, AgentRun.tenant_id == principal.tenant_id
                )
            )
        for event in events:
            last_sequence = event.sequence
            contract = RunEvent.model_validate(event)
            yield {
                "id": str(event.sequence),
                "event": event.event_type,
                "data": contract.model_dump_json(),
            }
        if run_status in TERMINAL_STATES and not events:
            break
        await asyncio.sleep(get_settings().run_event_poll_seconds)

