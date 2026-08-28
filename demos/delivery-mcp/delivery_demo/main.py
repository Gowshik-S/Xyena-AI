import asyncio
import hashlib
import hmac
import json
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .auth import ActorScope, authenticate_token, require_roles
from .constants import READ_ROLES
from .database import close_database, initialize_database, session
from .mcp import mcp, mcp_app
from .models import AuditEvent, Delivery, OutboxEvent
from .schemas import (
    AcceptanceCreate,
    CancellationRequest,
    CorrectionCreate,
    CorrectionReview,
    DeliveryAttemptRequest,
    DeliveryCreate,
    DispatchRequest,
    ExternalEventEnvelope,
    ProofCreate,
    ProofReview,
    TransitEventRequest,
)
from .seed import seed_demo_data
from .service import DeliveryDemoDomainError, delivery_service
from .settings import get_settings

SOURCE_FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
PACKAGED_FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
FRONTEND_ROOT = SOURCE_FRONTEND_ROOT if SOURCE_FRONTEND_ROOT.is_dir() else PACKAGED_FRONTEND_ROOT
FRONTEND_PAGES = {"/": "index.html", "/deliveries": "deliveries.html", "/detail": "detail.html"}


class MCPBearerAuthMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            scheme, _, supplied = headers.get(b"authorization", b"").decode("latin-1").partition(" ")
            expected = get_settings().mcp_token.get_secret_value()
            if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
                body = json.dumps({"code": "UNAUTHORIZED", "detail": "Invalid delivery MCP token."}).encode()
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def _if_match(value: str) -> int:
    normalized = value.strip().strip('W/').strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail="If-Match must contain a positive delivery version.")
    return int(normalized)


def _summary(delivery: Delivery) -> dict[str, Any]:
    return {
        "id": delivery.id, "delivery_number": delivery.delivery_number,
        "purchase_order_id": delivery.purchase_order_id, "invoice_id": delivery.invoice_id,
        "invoice_number": delivery.invoice_number, "seller_business_id": delivery.seller_business_id,
        "buyer_id": delivery.buyer_id, "carrier_id": delivery.carrier_id,
        "tracking_number": delivery.tracking_number, "status": delivery.status,
        "declared_value": str(delivery.declared_value),
        "verified_delivered_value": str(delivery.verified_delivered_value),
        "exception_code": delivery.exception_code, "version": delivery.version,
        "created_at": delivery.created_at.isoformat(), "updated_at": delivery.updated_at.isoformat(),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await initialize_database()
    await seed_demo_data()
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield
    await close_database()


def create_app() -> FastAPI:
    app = FastAPI(
        title="XYENA Delivery MCP",
        description="Tenant-scoped synthetic delivery operations and source-evidence MCP service.",
        version="1.0.0", openapi_version="3.1.0", lifespan=lifespan,
    )
    app.mount("/mcp", MCPBearerAuthMiddleware(mcp_app))
    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="delivery-demo-assets")

    def frontend_page(filename: str) -> Callable[[], Awaitable[FileResponse]]:
        async def page() -> FileResponse:
            return FileResponse(FRONTEND_ROOT / filename)
        return page

    for route, filename in FRONTEND_PAGES.items():
        app.add_api_route(route, frontend_page(filename), methods=["GET"], include_in_schema=False)

    @app.exception_handler(DeliveryDemoDomainError)
    async def domain_error(_: Request, exc: DeliveryDemoDomainError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"code": exc.__class__.__name__, "detail": str(exc)})

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-delivery-mcp"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with session() as db:
            await db.execute(select(func.count()).select_from(Delivery))
        return {"status": "ready", "service": "xyena-delivery-mcp"}

    read_scope = require_roles(*READ_ROLES)

    @app.get("/api/v1/session", tags=["operations"])
    async def current_session(actor: ActorScope = Depends(read_scope)) -> dict[str, str]:
        return {"role": actor.role, "actor_id": actor.actor_id, "tenant_id": actor.tenant_id}

    @app.get("/api/v1/dashboard", tags=["operations"])
    async def dashboard(actor: ActorScope = Depends(read_scope)) -> dict[str, Any]:
        return await delivery_service.dashboard(actor.tenant_id)

    @app.get("/api/v1/deliveries", tags=["operations"])
    async def list_deliveries(
        search: str | None = None, delivery_status: str | None = Query(None, alias="status"),
        actor: ActorScope = Depends(read_scope),
    ) -> list[dict[str, Any]]:
        return [_summary(d) for d in await delivery_service.list_deliveries(actor.tenant_id, search, delivery_status)]

    @app.post("/api/v1/deliveries", status_code=201, tags=["operations"])
    async def create_delivery(
        body: DeliveryCreate, actor: ActorScope = Depends(require_roles("SELLER_OPERATOR", "DEMO_ADMIN")),
    ) -> dict[str, Any]:
        delivery = await delivery_service.create_delivery(actor, body)
        return _summary(delivery)

    @app.get("/api/v1/deliveries/{delivery_id}", tags=["operations"])
    async def get_delivery(delivery_id: str, actor: ActorScope = Depends(read_scope)) -> dict[str, Any]:
        result = await delivery_service.get_delivery(actor.tenant_id, delivery_id)
        delivery = result["delivery"]
        return {
            **_summary(delivery),
            "seller_gstin": delivery.seller_gstin, "buyer_gstin": delivery.buyer_gstin,
            "ship_from": json.loads(delivery.ship_from), "ship_to": json.loads(delivery.ship_to),
            "dispatch_date": delivery.dispatch_date.isoformat() if delivery.dispatch_date else None,
            "expected_delivery_date": delivery.expected_delivery_date.isoformat() if delivery.expected_delivery_date else None,
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
            "currency": delivery.currency,
            "items": [{"id": i.id, "po_line_id": i.po_line_id, "invoice_line_id": i.invoice_line_id, "sku": i.sku, "description": i.description, "unit": i.unit, "ordered_quantity": str(i.ordered_quantity), "dispatched_quantity": str(i.dispatched_quantity), "delivered_quantity": str(i.delivered_quantity), "accepted_quantity": str(i.accepted_quantity), "rejected_quantity": str(i.rejected_quantity), "supported_unit_value": str(i.supported_unit_value), "rejection_reason": i.rejection_reason, "version": i.version} for i in result["items"]],
            "events": [{"id": e.id, "event_type": e.event_type, "occurred_at": e.occurred_at.isoformat(), "actor": e.actor, "location": json.loads(e.location) if e.location else None, "notes": e.notes, "prior_status": e.prior_status, "new_status": e.new_status, "version": e.version} for e in result["events"]],
            "proofs": [{"id": p.id, "proof_type": p.proof_type, "content_hash": p.content_hash, "mime_type": p.mime_type, "verification_status": p.verification_status, "captured_at": p.captured_at.isoformat(), "security_flags": json.loads(p.security_flags or "[]")} for p in result["proofs"]],
            "acceptances": [{"id": a.id, "status": a.status, "accepted_value": str(a.accepted_value), "occurred_at": a.occurred_at.isoformat(), "items": json.loads(a.item_level_acceptance)} for a in result["acceptances"]],
            "corrections": [{"id": c.id, "correction_type": c.correction_type, "reason": c.reason, "status": c.status, "requester": c.requester, "reviewer": c.reviewer, "proposed_changes": json.loads(c.proposed_changes)} for c in result["corrections"]],
        }

    Match = Annotated[str, Header(alias="If-Match")]

    @app.post("/api/v1/deliveries/{delivery_id}/ready", tags=["workflow"])
    async def mark_ready(delivery_id: str, if_match: Match, actor: ActorScope = Depends(require_roles("SELLER_OPERATOR", "DEMO_ADMIN"))) -> dict[str, Any]:
        return _summary(await delivery_service.mark_ready(actor, delivery_id, _if_match(if_match)))

    @app.post("/api/v1/deliveries/{delivery_id}/dispatch", tags=["workflow"])
    async def dispatch(delivery_id: str, body: DispatchRequest, if_match: Match, actor: ActorScope = Depends(require_roles("SELLER_OPERATOR", "DEMO_ADMIN"))) -> dict[str, Any]:
        return _summary(await delivery_service.dispatch_delivery(actor, delivery_id, _if_match(if_match), body))

    @app.post("/api/v1/deliveries/{delivery_id}/events", tags=["workflow"])
    async def transit(delivery_id: str, body: TransitEventRequest, if_match: Match, actor: ActorScope = Depends(require_roles("CARRIER_OPERATOR", "DEMO_ADMIN"))) -> dict[str, Any]:
        return _summary(await delivery_service.record_transit_event(actor, delivery_id, _if_match(if_match), body))

    @app.post("/api/v1/deliveries/{delivery_id}/delivery-attempt", tags=["workflow"])
    async def attempt(delivery_id: str, body: DeliveryAttemptRequest, if_match: Match, actor: ActorScope = Depends(require_roles("CARRIER_OPERATOR", "DEMO_ADMIN"))) -> dict[str, Any]:
        return _summary(await delivery_service.record_delivery_attempt(actor, delivery_id, _if_match(if_match), body))

    @app.post("/api/v1/deliveries/{delivery_id}/proofs", status_code=201, tags=["workflow"])
    async def capture_proof(delivery_id: str, body: ProofCreate, if_match: Match, actor: ActorScope = Depends(require_roles("CARRIER_OPERATOR", "DEMO_ADMIN"))) -> dict[str, Any]:
        proof = await delivery_service.capture_pod(actor, delivery_id, _if_match(if_match), body)
        return {"id": proof.id, "verification_status": proof.verification_status, "content_hash": proof.content_hash}

    @app.post("/api/v1/deliveries/{delivery_id}/proofs/{proof_id}/review", tags=["workflow"])
    async def review_proof(delivery_id: str, proof_id: str, body: ProofReview, if_match: Match, actor: ActorScope = Depends(require_roles("DELIVERY_REVIEWER"))) -> dict[str, Any]:
        return _summary(await delivery_service.verify_pod(actor, delivery_id, proof_id, _if_match(if_match), body.verified, body.rejection_reason))

    @app.post("/api/v1/deliveries/{delivery_id}/acceptance", tags=["workflow"])
    async def acceptance(delivery_id: str, body: AcceptanceCreate, if_match: Match, actor: ActorScope = Depends(require_roles("BUYER_RECEIVER", "DEMO_ADMIN"))) -> dict[str, Any]:
        return _summary(await delivery_service.record_buyer_acceptance(actor, delivery_id, _if_match(if_match), body))

    @app.post("/api/v1/deliveries/{delivery_id}/cancel", tags=["workflow"])
    async def cancel(delivery_id: str, body: CancellationRequest, if_match: Match, actor: ActorScope = Depends(require_roles("SELLER_OPERATOR", "DELIVERY_REVIEWER"))) -> dict[str, Any]:
        return _summary(await delivery_service.cancel_delivery(actor, delivery_id, _if_match(if_match), body.reason))

    @app.post("/api/v1/deliveries/{delivery_id}/corrections", status_code=201, tags=["workflow"])
    async def correction(delivery_id: str, body: CorrectionCreate, if_match: Match, actor: ActorScope = Depends(require_roles("SELLER_OPERATOR", "CARRIER_OPERATOR", "BUYER_RECEIVER"))) -> dict[str, Any]:
        record = await delivery_service.propose_correction(actor, delivery_id, _if_match(if_match), body)
        return {"id": record.id, "status": record.status}

    @app.post("/api/v1/corrections/{correction_id}/review", tags=["workflow"])
    async def review_correction(correction_id: str, body: CorrectionReview, if_match: Match, actor: ActorScope = Depends(require_roles("DELIVERY_REVIEWER"))) -> dict[str, Any]:
        return _summary(await delivery_service.review_correction(actor, correction_id, _if_match(if_match), body.approve, body.reason))

    @app.post("/api/v1/events/inbox", tags=["integration"])
    async def receive_event(request: Request, x_xyena_signature: Annotated[str, Header(alias="X-Xyena-Signature")]) -> dict[str, str]:
        raw = await request.body()
        expected = hmac.new(get_settings().event_signing_key.get_secret_value().encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(x_xyena_signature, expected):
            raise HTTPException(status_code=401, detail="Invalid event signature.")
        envelope = ExternalEventEnvelope.model_validate_json(raw)
        result = await delivery_service.consume_external_event(envelope, hashlib.sha256(raw).hexdigest())
        return {"status": result, "event_id": envelope.event_id}

    @app.get("/api/v1/events/stream", tags=["events"])
    async def event_stream(token: str = Query(...), after: str | None = Query(None)) -> StreamingResponse:
        actor = authenticate_token(token)

        async def generator():
            cursor_time = datetime.now(UTC)
            if after:
                async with session() as db:
                    previous = await db.scalar(
                        select(OutboxEvent).where(
                            OutboxEvent.id == after,
                            OutboxEvent.tenant_id == actor.tenant_id,
                        )
                    )
                if previous:
                    cursor_time = previous.created_at
                    if cursor_time.tzinfo is None:
                        cursor_time = cursor_time.replace(tzinfo=UTC)
            while True:
                async with session() as db:
                    query = select(OutboxEvent).where(
                        OutboxEvent.tenant_id == actor.tenant_id,
                        OutboxEvent.created_at > cursor_time,
                    )
                    events = (await db.scalars(query.order_by(OutboxEvent.created_at).limit(100))).all()
                if events:
                    for event in events:
                        cursor_time = event.created_at
                        if cursor_time.tzinfo is None:
                            cursor_time = cursor_time.replace(tzinfo=UTC)
                        yield f"id: {event.id}\nevent: delivery\ndata: {event.payload}\n\n"
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/v1/audit", tags=["administration"])
    async def audit(actor: ActorScope = Depends(require_roles("DELIVERY_REVIEWER", "DEMO_ADMIN"))) -> list[dict[str, Any]]:
        async with session() as db:
            rows = (await db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == actor.tenant_id).order_by(AuditEvent.occurred_at.desc()).limit(250))).all()
            return [{"id": r.id, "event_type": r.event_type, "aggregate_id": r.aggregate_id, "aggregate_version": r.aggregate_version, "actor_id": r.actor_id, "reason": r.reason, "before_hash": r.before_hash, "after_hash": r.after_hash, "correlation_id": r.correlation_id, "occurred_at": r.occurred_at.isoformat()} for r in rows]

    @app.get("/metrics", include_in_schema=False)
    async def metrics(actor: ActorScope = Depends(require_roles("DELIVERY_REVIEWER", "DEMO_ADMIN"))):
        from fastapi.responses import PlainTextResponse
        async with session() as db:
            count = await db.scalar(select(func.count()).select_from(Delivery).where(Delivery.tenant_id == actor.tenant_id))
        return PlainTextResponse(f"xyena_delivery_records {count or 0}\n")

    @app.get("/api/v1/admin/scenarios", tags=["administration"])
    async def scenarios(_: ActorScope = Depends(require_roles("DEMO_ADMIN"))) -> list[dict[str, str]]:
        return [
            {"id": "accepted", "purpose": "fully accepted delivery"},
            {"id": "partial", "purpose": "short and partially accepted delivery"},
            {"id": "source-mismatch", "purpose": "invoice identity exception"},
            {"id": "proof-review", "purpose": "rejected and replacement proof"},
            {"id": "untrusted-note", "purpose": "prompt-injection-shaped business text"},
        ]

    return app


app = create_app()


def run() -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run("delivery_demo.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
