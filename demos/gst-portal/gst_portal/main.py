import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth import (
    SESSION_COOKIE,
    AuthenticationError,
    AuthorizationError,
    authenticate,
    create_browser_session,
    resolve_browser_scope,
    rotate_csrf,
    verify_csrf,
)
from .database import close_database, initialize_database, session
from .mcp_server import mcp, mcp_app
from .models import BrowserSession, EnterpriseMembership, OutboxEvent
from .schemas import (
    ClassificationReviewRequest,
    EnterpriseSwitchRequest,
    InvoiceCreate,
    LoginRequest,
    TransitionRequest,
)
from .seed import seed_demo_data
from .service import (
    GstConflictError,
    GstDomainError,
    GstNotFoundError,
    gst_service,
)
from .settings import get_settings


SOURCE_FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
PACKAGED_FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
FRONTEND_ROOT = (
    SOURCE_FRONTEND_ROOT if SOURCE_FRONTEND_ROOT.is_dir() else PACKAGED_FRONTEND_ROOT
)


class DemoStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


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
                    {"code": "UNAUTHORIZED", "detail": "Invalid GST MCP token."}
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await initialize_database()
    await seed_demo_data()
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield
    await close_database()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="XYENA Synthetic GST and e-Invoice Portal",
        summary="Stateful synthetic GST operations portal with read-only MCP evidence tools",
        description=(
            "A non-production demonstration. It does not connect to GSTN, Udyam, Aadhaar, PAN, "
            "a tax authority, or a real taxpayer account."
        ),
        version="0.1.0",
        openapi_version="3.1.0",
        lifespan=lifespan,
    )
    app.mount("/mcp", MCPBearerAuthMiddleware(mcp_app))
    app.mount("/assets", DemoStaticFiles(directory=FRONTEND_ROOT), name="gst-portal-assets")

    @app.exception_handler(AuthenticationError)
    async def authentication_error(_: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"code": "UNAUTHENTICATED", "detail": str(exc)})

    @app.exception_handler(AuthorizationError)
    async def authorization_error(_: Request, exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"code": "FORBIDDEN", "detail": str(exc)})

    @app.exception_handler(GstNotFoundError)
    async def not_found_error(_: Request, exc: GstNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND", "detail": str(exc)})

    @app.exception_handler(GstConflictError)
    async def conflict_error(_: Request, exc: GstConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"code": "CONFLICT", "detail": str(exc)})

    @app.exception_handler(GstDomainError)
    async def domain_error(_: Request, exc: GstDomainError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"code": "INVALID_OPERATION", "detail": str(exc)})

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/dashboard", status_code=302)

    page_files = {
        "login": "login.html",
        "dashboard": "index.html",
        "invoices": "invoices.html",
        "invoices/new": "invoice-new.html",
        "invoice": "invoice-detail.html",
        "taxpayers": "taxpayers.html",
        "returns": "returns.html",
        "classification": "classification.html",
        "audit": "audit.html",
        "mcp-connection": "mcp-connection.html",
    }
    for route, filename in page_files.items():
        app.add_api_route(
            f"/{route}",
            _page_handler(filename),
            methods=["GET"],
            include_in_schema=False,
        )

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-synthetic-gst-portal"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with session() as db:
            await db.execute(select(1))
        return {"status": "ready", "service": "xyena-synthetic-gst-portal"}

    @app.post("/api/v1/auth/login", tags=["authentication"])
    async def login(body: LoginRequest) -> JSONResponse:
        async with session() as db:
            user = await authenticate(db, body.email, body.password)
            _, raw_token, csrf_token = await create_browser_session(db, user)
            response = JSONResponse(
                {
                    "status": "AUTHENTICATED",
                    "csrf_token": csrf_token,
                    "redirect": "/dashboard",
                }
            )
            response.set_cookie(
                SESSION_COOKIE,
                raw_token,
                max_age=8 * 60 * 60,
                httponly=True,
                secure=settings.cookie_secure,
                samesite="strict",
                path="/",
            )
            return response

    @app.get("/api/v1/auth/session", tags=["authentication"])
    async def current_session(request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            result = await gst_service.session_view(db, scope)
            result["csrf_token"] = rotate_csrf(scope)
            return result

    @app.post("/api/v1/auth/logout", tags=["authentication"])
    async def logout(
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            await db.delete(scope.session)
        response = JSONResponse({"status": "SIGNED_OUT"})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.post("/api/v1/auth/enterprise", tags=["authentication"])
    async def switch_enterprise(
        body: EnterpriseSwitchRequest,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            membership = await db.scalar(
                select(EnterpriseMembership).where(
                    EnterpriseMembership.user_id == scope.user.id,
                    EnterpriseMembership.enterprise_id == body.enterprise_id,
                    EnterpriseMembership.status == "ACTIVE",
                )
            )
            if membership is None:
                raise AuthorizationError("The requested enterprise is not assigned to this user.")
            scope.session.enterprise_id = body.enterprise_id
            return {"status": "ENTERPRISE_SWITCHED", "enterprise_id": body.enterprise_id}

    @app.get("/api/v1/dashboard", tags=["operations"])
    async def dashboard(request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await gst_service.dashboard(db, scope)

    @app.get("/api/v1/enterprises/current", tags=["enterprises"])
    async def current_enterprise(request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return gst_service.enterprise_projection(scope.enterprise)

    @app.get("/api/v1/taxpayers", tags=["taxpayers"])
    async def taxpayers(request: Request) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await gst_service.taxpayers(db, scope)

    @app.get("/api/v1/taxpayers/{gstin}", tags=["taxpayers"])
    async def taxpayer(gstin: str, request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            values = await gst_service.taxpayers(db, scope)
            for value in values:
                if value["gstin"] == gstin.upper():
                    return value
            raise GstNotFoundError("Taxpayer was not found in the active enterprise.")

    @app.get("/api/v1/invoices", tags=["invoices"])
    async def invoices(
        request: Request,
        query: str | None = None,
        invoice_status: str | None = None,
    ) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await gst_service.list_invoices(
                db, scope, query=query, status=invoice_status
            )

    @app.post("/api/v1/invoices", status_code=status.HTTP_201_CREATED, tags=["invoices"])
    async def create_invoice(
        body: InvoiceCreate,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            return await gst_service.create_invoice(db, scope, body)

    @app.get("/api/v1/invoices/{invoice_id}", tags=["invoices"])
    async def invoice(invoice_id: str, request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await gst_service.get_invoice(db, scope, invoice_id)

    @app.post("/api/v1/invoices/{invoice_id}/{action}", tags=["invoices"])
    async def transition_invoice(
        invoice_id: str,
        action: str,
        body: TransitionRequest,
        request: Request,
        if_match: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        if if_match is None or not if_match.isdigit():
            raise HTTPException(status_code=428, detail="A numeric If-Match version is required.")
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            return await gst_service.transition_invoice(
                db,
                scope,
                invoice_id,
                action,
                expected_version=int(if_match),
                reason=body.reason,
            )

    @app.get("/api/v1/enterprises/current/classification", tags=["classification"])
    async def classification(request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await gst_service.classification(db, scope)

    @app.post("/api/v1/enterprises/current/classification/recalculate", tags=["classification"])
    async def recalculate_classification(
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            return await gst_service.recalculate_classification(db, scope)

    @app.post("/api/v1/enterprises/current/classification/review", tags=["classification"])
    async def review_classification(
        body: ClassificationReviewRequest,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            return await gst_service.review_classification(db, scope, body)

    @app.get("/api/v1/returns", tags=["returns"])
    async def returns(request: Request) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await gst_service.returns(db, scope)

    @app.get("/api/v1/audit", tags=["audit"])
    async def audit(request: Request) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await gst_service.audit(db, scope)

    @app.get("/api/v1/events/stream", tags=["events"])
    async def events(request: Request) -> EventSourceResponse:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            tenant_id = scope.enterprise.tenant_id

        async def generate() -> AsyncIterator[dict[str, str]]:
            cursor_time = datetime.now(UTC)
            while not await request.is_disconnected():
                async with session() as db:
                    statement = select(OutboxEvent).where(
                        OutboxEvent.tenant_id == tenant_id,
                        OutboxEvent.created_at > cursor_time,
                    )
                    values = (
                        await db.scalars(statement.order_by(OutboxEvent.created_at).limit(20))
                    ).all()
                for value in values:
                    event_time = value.created_at
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=UTC)
                    cursor_time = max(cursor_time, event_time)
                    yield {
                        "event": value.event_type,
                        "id": value.id,
                        "data": json.dumps(value.payload),
                    }
                await asyncio.sleep(1)

        return EventSourceResponse(generate())

    return app


def _page_handler(filename: str) -> Any:
    async def handler() -> FileResponse:
        return FileResponse(FRONTEND_ROOT / filename)

    return handler


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("gst_portal.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
