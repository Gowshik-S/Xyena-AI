import asyncio
import json
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .database import close_database, initialize_database, session
from .mcp import mcp, mcp_app
from .models import (
    AuditEvent,
    BuyerAcceptance,
    Delivery,
    DeliveryCorrection,
    DeliveryEvent,
    DeliveryItem,
    ProofOfDelivery,
)
from .seed import seed_demo_data
from .service import delivery_service, sse_listeners
from .settings import get_settings


SOURCE_FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
PACKAGED_FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
FRONTEND_ROOT = (
    SOURCE_FRONTEND_ROOT if SOURCE_FRONTEND_ROOT.is_dir() else PACKAGED_FRONTEND_ROOT
)

FRONTEND_PAGES = {
    "/": "index.html",
    "/deliveries": "deliveries.html",
    "/detail": "detail.html",
}


class MCPBearerAuthMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            raw = headers.get(b"authorization", b"").decode("latin-1")
            scheme, _, supplied = raw.partition(" ")
            expected = get_settings().mcp_token.get_secret_value()
            if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
                body = json.dumps(
                    {"code": "UNAUTHORIZED", "detail": "Invalid delivery demo MCP token."}
                ).encode()
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


async def require_ui_token(
    x_demo_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().ui_token.get_secret_value()
    if x_demo_token is None or not secrets.compare_digest(x_demo_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid demo UI token.",
        )


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
        title="XYENA Synthetic Delivery and Fulfilment Demo",
        description="Isolated synthetic delivery and verification demonstration platform.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.mount("/mcp", MCPBearerAuthMiddleware(mcp_app))
    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="delivery-demo-assets")

    def frontend_page(filename: str) -> Callable[[], Awaitable[FileResponse]]:
        async def page() -> FileResponse:
            return FileResponse(FRONTEND_ROOT / filename)
        return page

    for route, filename in FRONTEND_PAGES.items():
        app.add_api_route(
            route,
            frontend_page(filename),
            methods=["GET"],
            include_in_schema=False,
            name=f"frontend-{filename.removesuffix('.html')}",
        )

    # --- Health Endpoints ---

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-synthetic-delivery-demo"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with session() as db:
            await db.execute(select(func.count()).select_from(Delivery))
        return {"status": "ready", "service": "xyena-synthetic-delivery-demo"}

    # --- SSE Stream Endpoint ---

    @app.get("/api/v1/events/stream", tags=["events"])
    async def events_stream() -> StreamingResponse:
        async def event_generator():
            queue = asyncio.Queue()
            sse_listeners.append(queue)
            try:
                while True:
                    data = await queue.get()
                    yield f"data: {json.dumps(data)}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                sse_listeners.remove(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # --- REST API Endpoints ---

    @app.get("/api/v1/dashboard", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def get_dashboard() -> dict[str, Any]:
        async with session() as db:
            # Counts by status
            deliveries = (await db.scalars(select(Delivery))).all()
            counts = {
                "CREATED": 0,
                "READY_TO_DISPATCH": 0,
                "DISPATCHED": 0,
                "IN_TRANSIT": 0,
                "OUT_FOR_DELIVERY": 0,
                "DELIVERED_PENDING_ACCEPTANCE": 0,
                "PARTIAL_PENDING_ACCEPTANCE": 0,
                "DELIVERED": 0,
                "PARTIALLY_ACCEPTED": 0,
                "REJECTED": 0,
                "DELIVERY_FAILED": 0,
                "CANCELLED": 0,
            }
            for d in deliveries:
                counts[d.status] = counts.get(d.status, 0) + 1

            # Value totals
            total_accepted_val = sum(d.verified_delivered_value for d in deliveries)
            total_declared_val = sum(d.declared_value for d in deliveries)

            # Aging Deliveries (Late)
            # Simulated based on seeded data
            aging = {"1_day": 0, "3_days": 0, "5_plus_days": 0}
            for d in deliveries:
                if d.status in ("DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY") and d.expected_delivery_date:
                    days_over = (date.today() - d.expected_delivery_date).days
                    if days_over >= 5:
                        aging["5_plus_days"] += 1
                    elif days_over >= 3:
                        aging["3_days"] += 1
                    elif days_over >= 1:
                        aging["1_day"] += 1

            # Critical Alerts (Exceptions and POD / Invoice Mismatches)
            alerts = []
            for d in deliveries:
                if d.exception_code:
                    alerts.append({
                        "delivery_id": d.id,
                        "delivery_number": d.delivery_number,
                        "type": d.exception_code,
                        "message": f"Exception code '{d.exception_code}' raised on shipment.",
                    })

            # Query recent audit events
            recent_events = (
                await db.scalars(
                    select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(10)
                )
            ).all()

            return {
                "counts": counts,
                "total_accepted_value": str(total_accepted_val),
                "total_declared_value": str(total_declared_val),
                "aging_report": aging,
                "alerts": alerts,
                "recent_audit_trail": [
                    {
                        "id": audit.id,
                        "event_type": audit.event_type,
                        "aggregate_type": audit.aggregate_type,
                        "aggregate_id": audit.aggregate_id,
                        "actor_id": audit.actor_id,
                        "occurred_at": audit.occurred_at.isoformat(),
                    }
                    for audit in recent_events
                ],
            }

    @app.get("/api/v1/deliveries", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def list_deliveries(
        search: str | None = None,
        seller: str | None = None,
        buyer: str | None = None,
        carrier: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        async with session() as db:
            query = select(Delivery)
            if search:
                query = query.where(
                    Delivery.delivery_number.contains(search)
                    | Delivery.purchase_order_id.contains(search)
                    | Delivery.invoice_number.contains(search)
                )
            if seller:
                query = query.where(Delivery.seller_business_id == seller)
            if buyer:
                query = query.where(Delivery.buyer_id == buyer)
            if carrier:
                query = query.where(Delivery.carrier_id == carrier)
            if status:
                query = query.where(Delivery.status == status)

            deliveries = (await db.scalars(query.order_by(Delivery.created_at.desc()))).all()
            return [
                {
                    "id": d.id,
                    "delivery_number": d.delivery_number,
                    "purchase_order_id": d.purchase_order_id,
                    "invoice_number": d.invoice_number,
                    "seller_business_id": d.seller_business_id,
                    "buyer_id": d.buyer_id,
                    "carrier_id": d.carrier_id,
                    "tracking_number": d.tracking_number,
                    "status": d.status,
                    "declared_value": str(d.declared_value),
                    "verified_delivered_value": str(d.verified_delivered_value),
                    "created_at": d.created_at.isoformat(),
                }
                for d in deliveries
            ]

    @app.post("/api/v1/deliveries", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def create_delivery(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            delivery = await delivery_service.create_delivery(
                tenant_id=payload.get("tenant_id", "00000000-0000-4000-8000-000000000101"),
                delivery_number=payload["delivery_number"],
                purchase_order_id=payload["purchase_order_id"],
                invoice_id=payload.get("invoice_id"),
                invoice_number=payload.get("invoice_number"),
                seller_business_id=payload["seller_business_id"],
                seller_gstin=payload["seller_gstin"],
                buyer_id=payload["buyer_id"],
                buyer_gstin=payload["buyer_gstin"],
                ship_from=payload["ship_from"],
                ship_to=payload["ship_to"],
                currency=payload.get("currency", "INR"),
                declared_value=Decimal(str(payload["declared_value"])),
                items_data=payload["items"],
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS", "delivery_id": delivery.id}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/v1/deliveries/{deliveryId}", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def get_delivery_details(deliveryId: str) -> dict[str, Any]:
        try:
            res = await delivery_service.get_delivery(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
            )
            d = res["delivery"]
            return {
                "id": d.id,
                "delivery_number": d.delivery_number,
                "purchase_order_id": d.purchase_order_id,
                "invoice_id": d.invoice_id,
                "invoice_number": d.invoice_number,
                "seller_business_id": d.seller_business_id,
                "buyer_id": d.buyer_id,
                "carrier_id": d.carrier_id,
                "tracking_number": d.tracking_number,
                "status": d.status,
                "ship_from": json.loads(d.ship_from),
                "ship_to": json.loads(d.ship_to),
                "dispatch_date": d.dispatch_date.isoformat() if d.dispatch_date else None,
                "expected_delivery_date": d.expected_delivery_date.isoformat() if d.expected_delivery_date else None,
                "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
                "currency": d.currency,
                "declared_value": str(d.declared_value),
                "verified_delivered_value": str(d.verified_delivered_value),
                "exception_code": d.exception_code,
                "version": d.version,
                "items": [
                    {
                        "id": item.id,
                        "sku": item.sku,
                        "description": item.description,
                        "unit": item.unit,
                        "ordered_quantity": str(item.ordered_quantity),
                        "dispatched_quantity": str(item.dispatched_quantity),
                        "delivered_quantity": str(item.delivered_quantity),
                        "accepted_quantity": str(item.accepted_quantity),
                        "rejected_quantity": str(item.rejected_quantity),
                        "supported_unit_value": str(item.supported_unit_value),
                        "rejection_reason": item.rejection_reason,
                    }
                    for item in res["items"]
                ],
                "events": [
                    {
                        "event_type": event.event_type,
                        "occurred_at": event.occurred_at.isoformat(),
                        "actor": event.actor,
                        "location": event.location,
                        "notes": event.notes,
                        "prior_status": event.prior_status,
                        "new_status": event.new_status,
                    }
                    for event in res["events"]
                ],
                "proofs": [
                    {
                        "id": pod.id,
                        "proof_type": pod.proof_type,
                        "verification_status": pod.verification_status,
                        "captured_at": pod.captured_at.isoformat(),
                        "recipient_name": pod.recipient_name,
                    }
                    for pod in res["proofs"]
                ],
                "acceptances": [
                    {
                        "status": acc.status,
                        "accepted_value": str(acc.accepted_value),
                        "occurred_at": acc.occurred_at.isoformat(),
                    }
                    for acc in res["acceptances"]
                ],
                "corrections": [
                    {
                        "id": corr.id,
                        "correction_type": corr.correction_type,
                        "reason": corr.reason,
                        "status": corr.status,
                    }
                    for corr in res["corrections"]
                ],
            }
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/api/v1/deliveries/{deliveryId}/ready", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def mark_delivery_ready(deliveryId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            await delivery_service.mark_ready(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/deliveries/{deliveryId}/dispatch", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def dispatch_delivery(deliveryId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            items_dispatch = {
                sku: Decimal(str(qty))
                for sku, qty in payload.get("items_dispatch", {}).items()
            }
            await delivery_service.dispatch_delivery(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                carrier_id=payload["carrier_id"],
                tracking_number=payload["tracking_number"],
                items_dispatch=items_dispatch,
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/deliveries/{deliveryId}/events", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def record_transit_event(deliveryId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            await delivery_service.record_transit_event(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                event_type=payload["event_type"],
                location=payload["location"],
                notes=payload.get("notes"),
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/deliveries/{deliveryId}/delivery-attempt", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def record_attempt(deliveryId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            items_delivered = {
                sku: Decimal(str(qty))
                for sku, qty in payload.get("items_delivered", {}).items()
            }
            await delivery_service.record_delivery_attempt(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                success=payload["success"],
                items_delivered=items_delivered,
                failure_reason=payload.get("failure_reason"),
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/deliveries/{deliveryId}/proofs", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def capture_pod(deliveryId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            pod = await delivery_service.capture_pod(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                proof_type=payload["proof_type"],
                restricted_object_key=payload["restricted_object_key"],
                mime_type=payload["mime_type"],
                recipient_token=payload.get("recipient_token"),
                recipient_name=payload.get("recipient_name"),
                recipient_role=payload.get("recipient_role"),
                security_flags=payload.get("security_flags", []),
                actor=payload.get("actor", "system"),
            )
            # Auto approve POD after capture for demo convenience
            await delivery_service.verify_pod(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                pod_id=pod.id,
                verified=True,
                rejection_reason=None,
                actor="delivery_reviewer",
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/deliveries/{deliveryId}/acceptance", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def record_acceptance(deliveryId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            await delivery_service.record_buyer_acceptance(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                status=payload["status"],
                items_acceptance=payload["items_acceptance"],
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/deliveries/{deliveryId}/cancel", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def cancel_delivery(deliveryId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            await delivery_service.cancel_delivery(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                reason=payload["reason"],
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/deliveries/{deliveryId}/corrections", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def propose_correction(deliveryId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            corr = await delivery_service.propose_correction(
                tenant_id="00000000-0000-4000-8000-000000000101",
                delivery_id=deliveryId,
                correction_type=payload["correction_type"],
                proposed_changes=payload["proposed_changes"],
                reason=payload["reason"],
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS", "correction_id": corr.id}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/corrections/{correctionId}/approve", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def approve_correction(correctionId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            await delivery_service.review_correction(
                tenant_id="00000000-0000-4000-8000-000000000101",
                correction_id=correctionId,
                approve=True,
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/corrections/{correctionId}/reject", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def reject_correction(correctionId: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            await delivery_service.review_correction(
                tenant_id="00000000-0000-4000-8000-000000000101",
                correction_id=correctionId,
                approve=False,
                actor=payload.get("actor", "system"),
            )
            return {"status": "SUCCESS"}
        except DeliveryDemoDomainError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "delivery_demo.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
