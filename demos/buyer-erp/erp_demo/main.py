import hashlib
import hmac
import json
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.types import ASGIApp, Receive, Scope, Send

from .database import close_database, initialize_database, session
from .gst_client import GSTIntegrationError, gst_client
from .mcp import mcp, mcp_app
from .models import PurchaseOrder
from .schemas import (
    AcceptanceCreate,
    DisputeCreate,
    GSTEventEnvelope,
    PurchaseOrderCreate,
    ReceiptCreate,
)
from .seed import DEMO_TENANT_ID, seed_demo_data
from .service import ERPConflictError, ERPDomainError, ERPNotFoundError, erp_service
from .settings import get_settings


SOURCE_FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
PACKAGED_FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
FRONTEND_ROOT = (
    SOURCE_FRONTEND_ROOT if SOURCE_FRONTEND_ROOT.is_dir() else PACKAGED_FRONTEND_ROOT
)
FRONTEND_PAGES = {
    "/": "index.html",
    "/purchase-orders": "purchase-orders.html",
    "/receipts": "receipts.html",
    "/invoice-matching": "invoice-matching.html",
    "/counterparties": "counterparties.html",
    "/activity": "activity.html",
    "/mcp-connection": "mcp-connection.html",
}


class MCPBearerAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            raw = headers.get(b"authorization", b"").decode("latin-1")
            scheme, _, supplied = raw.partition(" ")
            expected = get_settings().mcp_token.get_secret_value()
            if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
                body = json.dumps(
                    {"code": "UNAUTHORIZED", "detail": "Invalid ERP MCP token."}
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
    x_erp_ui_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().ui_token.get_secret_value()
    if x_erp_ui_token is None or not secrets.compare_digest(x_erp_ui_token, expected):
        raise HTTPException(status_code=401, detail="Invalid ERP dashboard token.")


async def require_admin_token(
    x_erp_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().admin_token.get_secret_value()
    if x_erp_admin_token is None or not secrets.compare_digest(x_erp_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid ERP operator token.")


def parse_version(if_match: str) -> int:
    normalized = if_match.strip().strip('W/').strip('"')
    try:
        return int(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="If-Match must contain an integer version.") from exc


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
        title="XYENA Synthetic Buyer ERP",
        summary="Stateful buyer operations and read-only ERP evidence over MCP v2",
        description=(
            "A non-production Buyer ERP demonstration with purchase orders, receipts, "
            "invoice matching, acceptance, audit/outbox records, and a signed GST event inbox."
        ),
        version="0.1.0",
        openapi_version="3.1.0",
        lifespan=lifespan,
    )
    app.mount("/mcp", MCPBearerAuthMiddleware(mcp_app))
    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="erp-assets")

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

    @app.exception_handler(ERPNotFoundError)
    async def not_found_handler(request: Request, exc: ERPNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND", "detail": str(exc)})

    @app.exception_handler(ERPConflictError)
    async def conflict_handler(request: Request, exc: ERPConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"code": "CONFLICT", "detail": str(exc)})

    @app.exception_handler(ERPDomainError)
    async def domain_handler(request: Request, exc: ERPDomainError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"code": "DOMAIN_RULE_REJECTED", "detail": str(exc)}
        )

    @app.exception_handler(GSTIntegrationError)
    async def gst_integration_handler(
        request: Request, exc: GSTIntegrationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"code": "GST_UPSTREAM_FAILED", "detail": str(exc)}
        )

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-buyer-erp-demo"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with session() as db:
            await db.execute(select(func.count()).select_from(PurchaseOrder))
        return {"status": "ready", "service": "xyena-buyer-erp-demo"}

    @app.get(
        "/api/v1/dashboard",
        dependencies=[Depends(require_ui_token)],
        tags=["dashboard"],
    )
    async def dashboard() -> dict[str, Any]:
        return await erp_service.dashboard(DEMO_TENANT_ID)

    @app.get(
        "/api/v1/counterparties",
        dependencies=[Depends(require_ui_token)],
        tags=["counterparties"],
    )
    async def counterparties() -> list[dict[str, Any]]:
        return (await erp_service.dashboard(DEMO_TENANT_ID))["counterparties"]

    @app.get(
        "/api/v1/purchase-orders",
        dependencies=[Depends(require_ui_token)],
        tags=["purchase-orders"],
    )
    async def purchase_orders() -> list[dict[str, Any]]:
        return (await erp_service.dashboard(DEMO_TENANT_ID))["purchase_orders"]

    @app.get(
        "/api/v1/purchase-orders/{order_id}",
        dependencies=[Depends(require_ui_token)],
        tags=["purchase-orders"],
    )
    async def purchase_order(order_id: str) -> dict[str, Any]:
        return await erp_service.get_purchase_order(DEMO_TENANT_ID, order_id)

    @app.post(
        "/api/v1/purchase-orders",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_admin_token)],
        tags=["purchase-orders"],
    )
    async def create_purchase_order(body: PurchaseOrderCreate) -> dict[str, Any]:
        return await erp_service.create_purchase_order(
            DEMO_TENANT_ID, body, "erp_demo_operator", str(uuid4())
        )

    @app.post(
        "/api/v1/purchase-orders/{order_id}/{action}",
        dependencies=[Depends(require_admin_token)],
        tags=["purchase-orders"],
    )
    async def transition_purchase_order(
        order_id: str,
        action: str,
        if_match: Annotated[str, Header()],
    ) -> dict[str, Any]:
        if action not in {"submit", "approve", "reject", "cancel"}:
            raise HTTPException(status_code=404, detail="Purchase-order action not found.")
        return await erp_service.transition_purchase_order(
            DEMO_TENANT_ID,
            order_id,
            action,
            parse_version(if_match),
            "erp_demo_operator",
            str(uuid4()),
        )

    @app.get(
        "/api/v1/receipts/{receipt_id}",
        dependencies=[Depends(require_ui_token)],
        tags=["receipts"],
    )
    async def receipt(receipt_id: str) -> dict[str, Any]:
        return await erp_service.get_receipt(DEMO_TENANT_ID, receipt_id)

    @app.post(
        "/api/v1/receipts",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_admin_token)],
        tags=["receipts"],
    )
    async def create_receipt(body: ReceiptCreate) -> dict[str, Any]:
        return await erp_service.create_receipt(
            DEMO_TENANT_ID, body, "warehouse_demo_operator", str(uuid4())
        )

    @app.post(
        "/api/v1/receipts/{receipt_id}/post",
        dependencies=[Depends(require_admin_token)],
        tags=["receipts"],
    )
    async def post_receipt(
        receipt_id: str, if_match: Annotated[str, Header()]
    ) -> dict[str, Any]:
        return await erp_service.post_receipt(
            DEMO_TENANT_ID,
            receipt_id,
            parse_version(if_match),
            "warehouse_demo_operator",
            str(uuid4()),
        )

    @app.post(
        "/api/v1/invoice-matches/recalculate/{invoice_id}",
        dependencies=[Depends(require_admin_token)],
        tags=["invoice-matching"],
    )
    async def recalculate_match(invoice_id: str) -> dict[str, Any]:
        return await erp_service.recalculate_match(
            DEMO_TENANT_ID, invoice_id, "ap_demo_operator", str(uuid4())
        )

    @app.post(
        "/api/v1/invoice-matches/{match_id}/accept",
        dependencies=[Depends(require_admin_token)],
        tags=["invoice-matching"],
    )
    async def accept_match(
        match_id: str,
        body: AcceptanceCreate,
        if_match: Annotated[str, Header()],
    ) -> dict[str, Any]:
        return await erp_service.accept_match(
            DEMO_TENANT_ID,
            match_id,
            parse_version(if_match),
            body,
            str(uuid4()),
        )

    @app.post(
        "/api/v1/invoice-matches/{match_id}/dispute",
        dependencies=[Depends(require_admin_token)],
        tags=["invoice-matching"],
    )
    async def dispute_match(
        match_id: str,
        body: DisputeCreate,
        if_match: Annotated[str, Header()],
    ) -> dict[str, Any]:
        return await erp_service.dispute_match(
            DEMO_TENANT_ID,
            match_id,
            parse_version(if_match),
            body,
            str(uuid4()),
        )

    @app.post(
        "/api/v1/integrations/gst/events",
        status_code=status.HTTP_202_ACCEPTED,
        tags=["gst-integration"],
    )
    async def consume_gst_event(
        body: GSTEventEnvelope,
        request: Request,
        x_gst_event_signature: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        if not x_gst_event_signature:
            raise HTTPException(status_code=401, detail="GST event signature is required.")
        raw = await request.body()
        expected = hmac.new(
            get_settings().gst_event_secret.get_secret_value().encode(),
            raw,
            hashlib.sha256,
        ).hexdigest()
        if not secrets.compare_digest(x_gst_event_signature, expected):
            raise HTTPException(status_code=401, detail="GST event signature is invalid.")
        if body.tenant_id != DEMO_TENANT_ID or body.aggregate.type != "invoice":
            raise HTTPException(status_code=403, detail="GST event is outside the ERP tenant scope.")
        if body.event_type == "invoice.registered" and "invoice_snapshot" not in body.data:
            snapshot = await gst_client.fetch_invoice(body.aggregate.id)
            if snapshot is not None:
                body = body.model_copy(
                    update={"data": {**body.data, "invoice_snapshot": snapshot}}
                )
        return await erp_service.consume_gst_event(
            body,
            signed_payload_hash=hashlib.sha256(raw).hexdigest(),
        )

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "erp_demo.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
