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
from .models import OutboxEvent
from .schemas import (
    BusinessCreate,
    ChangeDecision,
    ChangeRequestCreate,
    LoginRequest,
    StatusTransition,
)
from .seed import seed_demo_data
from .service import (
    RegistryConflictError,
    RegistryDomainError,
    RegistryNotFoundError,
    registry_service,
)
from .settings import get_settings


SOURCE_FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
PACKAGED_FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
FRONTEND_ROOT = SOURCE_FRONTEND_ROOT if SOURCE_FRONTEND_ROOT.is_dir() else PACKAGED_FRONTEND_ROOT


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
                    {"code": "UNAUTHORIZED", "detail": "Invalid Registry MCP token."}
                ).encode()
                await send({
                    "type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                })
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
        title="XYENA Synthetic Business Registry",
        summary="Authoritative synthetic business identity and relationship evidence",
        description=(
            "A non-production registry demonstration. It contains synthetic identities and does "
            "not connect to MCA, Udyam, GSTN, Aadhaar, PAN or another government service."
        ),
        version="0.1.0",
        openapi_version="3.1.0",
        lifespan=lifespan,
    )
    app.mount("/mcp", MCPBearerAuthMiddleware(mcp_app))
    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="registry-assets")

    @app.exception_handler(AuthenticationError)
    async def authentication_error(_: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"code": "UNAUTHENTICATED", "detail": str(exc)})

    @app.exception_handler(AuthorizationError)
    async def authorization_error(_: Request, exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"code": "FORBIDDEN", "detail": str(exc)})

    @app.exception_handler(RegistryNotFoundError)
    async def not_found_error(_: Request, exc: RegistryNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND", "detail": str(exc)})

    @app.exception_handler(RegistryConflictError)
    async def conflict_error(_: Request, exc: RegistryConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"code": "CONFLICT", "detail": str(exc)})

    @app.exception_handler(RegistryDomainError)
    async def domain_error(_: Request, exc: RegistryDomainError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"code": "INVALID_OPERATION", "detail": str(exc)})

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/dashboard", status_code=302)

    page_files = {
        "login": "login.html",
        "dashboard": "index.html",
        "businesses": "businesses.html",
        "businesses/new": "business-new.html",
        "business": "business-detail.html",
        "change-requests": "change-requests.html",
        "relationships": "relationships.html",
        "audit": "audit.html",
        "mcp-connection": "mcp-connection.html",
    }
    for route, filename in page_files.items():
        app.add_api_route(
            f"/{route}", _page_handler(filename), methods=["GET"], include_in_schema=False
        )

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-synthetic-business-registry"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with session() as db:
            await db.execute(select(1))
        return {"status": "ready", "service": "xyena-synthetic-business-registry"}

    @app.post("/api/v1/auth/login", tags=["authentication"])
    async def login(body: LoginRequest) -> JSONResponse:
        async with session() as db:
            user = await authenticate(db, body.email, body.password)
            raw_token, csrf_token = await create_browser_session(db, user)
            response = JSONResponse({
                "status": "AUTHENTICATED", "csrf_token": csrf_token, "redirect": "/dashboard"
            })
            response.set_cookie(
                SESSION_COOKIE, raw_token, max_age=8 * 60 * 60, httponly=True,
                secure=settings.cookie_secure, samesite="strict", path="/",
            )
            return response

    @app.get("/api/v1/auth/session", tags=["authentication"])
    async def current_session(request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            result = await registry_service.session_view(scope)
            result["csrf_token"] = rotate_csrf(scope)
            return result

    @app.post("/api/v1/auth/logout", tags=["authentication"])
    async def logout(
        request: Request, x_csrf_token: Annotated[str | None, Header()] = None
    ) -> Response:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            await db.delete(scope.session)
        response = JSONResponse({"status": "SIGNED_OUT"})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/api/v1/dashboard", tags=["registry"])
    async def dashboard(request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await registry_service.dashboard(db, scope)

    @app.get("/api/v1/businesses", tags=["businesses"])
    async def businesses(
        request: Request,
        query: str | None = None,
        business_status: str | None = None,
        business_type: str | None = None,
    ) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await registry_service.list_businesses(
                db, scope, query=query, status=business_status, business_type=business_type
            )

    @app.post("/api/v1/businesses", status_code=status.HTTP_201_CREATED, tags=["businesses"])
    async def create_business(
        body: BusinessCreate,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            return await registry_service.create_business(db, scope, body)

    @app.get("/api/v1/businesses/{business_id}", tags=["businesses"])
    async def business(business_id: str, request: Request) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await registry_service.get_business(db, scope.tenant_id, business_id)

    @app.post("/api/v1/businesses/{business_id}/status", tags=["businesses"])
    async def transition_business(
        business_id: str,
        body: StatusTransition,
        request: Request,
        if_match: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        if if_match is None or not if_match.isdigit():
            raise HTTPException(status_code=428, detail="A numeric If-Match version is required.")
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            return await registry_service.transition_status(
                db, scope, business_id, body, expected_version=int(if_match)
            )

    @app.post("/api/v1/businesses/{business_id}/change-requests", tags=["changes"])
    async def propose_change(
        business_id: str,
        body: ChangeRequestCreate,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            return await registry_service.create_change_request(db, scope, business_id, body)

    @app.get("/api/v1/change-requests", tags=["changes"])
    async def change_requests(
        request: Request, change_status: str | None = None
    ) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await registry_service.list_changes(db, scope, change_status)

    @app.post("/api/v1/change-requests/{change_id}/{decision}", tags=["changes"])
    async def decide_change(
        change_id: str,
        decision: str,
        body: ChangeDecision,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise RegistryDomainError("Decision must be approve or reject.")
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            verify_csrf(scope, x_csrf_token)
            return await registry_service.decide_change(
                db, scope, change_id, approve=decision == "approve",
                decision_reason=body.decision_reason,
            )

    @app.get("/api/v1/businesses/{business_id}/ownership", tags=["relationships"])
    async def ownership(business_id: str, request: Request) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            business_value = await registry_service._business(db, scope.tenant_id, business_id)
            return await registry_service.ownership(db, scope.tenant_id, business_value.id)

    @app.get("/api/v1/businesses/{business_id}/relationships", tags=["relationships"])
    async def business_relationships(business_id: str, request: Request) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            business_value = await registry_service._business(db, scope.tenant_id, business_id)
            return await registry_service.relationships(db, scope.tenant_id, business_value.id)

    @app.get("/api/v1/relationships", tags=["relationships"])
    async def relationships(request: Request) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await registry_service.all_relationships(db, scope)

    @app.get("/api/v1/audit", tags=["audit"])
    async def audit(request: Request) -> list[dict[str, Any]]:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            return await registry_service.audit(db, scope)

    @app.get("/api/v1/events/stream", tags=["events"])
    async def events(request: Request) -> EventSourceResponse:
        async with session() as db:
            scope = await resolve_browser_scope(db, request.cookies.get(SESSION_COOKIE))
            tenant_id = scope.tenant_id

        async def generate() -> AsyncIterator[dict[str, str]]:
            cursor_time = datetime.now(UTC)
            while not await request.is_disconnected():
                async with session() as db:
                    values = (
                        await db.scalars(
                            select(OutboxEvent)
                            .where(
                                OutboxEvent.tenant_id == tenant_id,
                                OutboxEvent.created_at > cursor_time,
                            )
                            .order_by(OutboxEvent.created_at)
                            .limit(20)
                        )
                    ).all()
                for value in values:
                    event_time = value.created_at
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=UTC)
                    cursor_time = max(cursor_time, event_time)
                    yield {"event": value.event_type, "id": value.id, "data": json.dumps(value.payload)}
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
    uvicorn.run("business_registry.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
