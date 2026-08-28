import asyncio
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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.types import ASGIApp, Receive, Scope, Send

from .database import close_database, initialize_database, session
from .mcp import mcp, mcp_app
from .models import FundingProgram, OutboxEvent
from .schemas import (
    ApplicationRequest,
    CommitmentConfirmRequest,
    CommitmentPrepareRequest,
    ExternalEventEnvelope,
    OfferRequest,
    ProgramTransitionRequest,
    ReleaseRequest,
    ReserveRequest,
    ReviewRequest,
)
from .seed import DEMO_TENANT_ID, seed_demo_data
from .service import FunderConflictError, FunderDomainError, FunderNotFoundError, funder_service
from .settings import get_settings


SOURCE_FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
PACKAGED_FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
FRONTEND_ROOT = SOURCE_FRONTEND_ROOT if SOURCE_FRONTEND_ROOT.is_dir() else PACKAGED_FRONTEND_ROOT
FRONTEND_PAGES = {
    "/": "index.html",
    "/funders": "funders.html",
    "/programs": "programs.html",
    "/applications": "applications.html",
    "/offers": "offers.html",
    "/reservations": "reservations.html",
    "/commitments": "commitments.html",
    "/exposure": "exposure.html",
    "/activity": "activity.html",
    "/mcp-connection": "mcp-connection.html",
}


class MCPBearerAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            scheme, _, supplied = headers.get(b"authorization", b"").decode("latin-1").partition(" ")
            expected = get_settings().mcp_token.get_secret_value()
            if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
                body = json.dumps({"code": "UNAUTHORIZED", "detail": "Invalid Funder MCP token."}).encode()
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


async def require_ui_token(x_funder_ui_token: Annotated[str | None, Header()] = None) -> None:
    if x_funder_ui_token is None or not secrets.compare_digest(x_funder_ui_token, get_settings().ui_token.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid marketplace dashboard token.")


async def require_operator_token(x_funder_operator_token: Annotated[str | None, Header()] = None) -> None:
    if x_funder_operator_token is None or not secrets.compare_digest(x_funder_operator_token, get_settings().operator_token.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid funder operator token.")


async def require_execution_token(x_execution_gateway_token: Annotated[str | None, Header()] = None) -> None:
    if x_execution_gateway_token is None or not secrets.compare_digest(x_execution_gateway_token, get_settings().execution_token.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid execution gateway token.")


def parse_version(if_match: str) -> int:
    normalized = if_match.strip().removeprefix("W/").strip('"')
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
        title="XYENA Synthetic Funder Marketplace",
        summary="Stateful funding programs, offers and Guardian-protected commitments",
        description="A non-production marketplace for deterministic eligibility, time-bound offer reservations and exact-action commitments.",
        version="0.1.0", openapi_version="3.1.0", lifespan=lifespan,
    )
    app.mount("/mcp", MCPBearerAuthMiddleware(mcp_app))
    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="funder-assets")

    def frontend_page(filename: str) -> Callable[[], Awaitable[FileResponse]]:
        async def page() -> FileResponse:
            return FileResponse(FRONTEND_ROOT / filename)
        return page

    for route, filename in FRONTEND_PAGES.items():
        app.add_api_route(route, frontend_page(filename), methods=["GET"], include_in_schema=False, name=f"frontend-{filename.removesuffix('.html')}")

    @app.exception_handler(FunderNotFoundError)
    async def not_found(_: Request, exc: FunderNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND", "detail": str(exc)})

    @app.exception_handler(FunderConflictError)
    async def conflict(_: Request, exc: FunderConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"code": "CONFLICT", "detail": str(exc)})

    @app.exception_handler(FunderDomainError)
    async def domain_error(_: Request, exc: FunderDomainError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"code": "DOMAIN_RULE_REJECTED", "detail": str(exc)})

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-funder-marketplace-demo"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with session() as db:
            await db.execute(select(func.count()).select_from(FundingProgram))
        return {"status": "ready", "service": "xyena-funder-marketplace-demo"}

    @app.get("/api/v1/dashboard", dependencies=[Depends(require_ui_token)], tags=["dashboard"])
    async def dashboard() -> dict[str, Any]:
        return await funder_service.dashboard(DEMO_TENANT_ID)

    @app.get("/api/v1/funders", dependencies=[Depends(require_ui_token)], tags=["funders"])
    async def funders() -> list[dict[str, Any]]:
        return (await funder_service.dashboard(DEMO_TENANT_ID))["funders"]

    @app.get("/api/v1/programs", dependencies=[Depends(require_ui_token)], tags=["programs"])
    async def programs() -> list[dict[str, Any]]:
        return (await funder_service.dashboard(DEMO_TENANT_ID))["programs"]

    @app.post("/api/v1/programs/{program_id}/transition", dependencies=[Depends(require_operator_token)], tags=["programs"])
    async def transition_program(program_id: str, body: ProgramTransitionRequest, if_match: Annotated[str, Header()]) -> dict[str, Any]:
        return await funder_service.transition_program(DEMO_TENANT_ID, program_id, parse_version(if_match), body, str(uuid4()))

    @app.get("/api/v1/applications", dependencies=[Depends(require_ui_token)], tags=["applications"])
    async def applications() -> list[dict[str, Any]]:
        return (await funder_service.dashboard(DEMO_TENANT_ID))["applications"]

    @app.post("/api/v1/applications", dependencies=[Depends(require_operator_token)], status_code=status.HTTP_201_CREATED, tags=["applications"])
    async def create_application(body: ApplicationRequest) -> dict[str, Any]:
        return await funder_service.create_application(DEMO_TENANT_ID, body, "funder_operator", str(uuid4()))

    @app.post("/api/v1/applications/{application_id}/review", dependencies=[Depends(require_operator_token)], tags=["applications"])
    async def review_application(application_id: str, body: ReviewRequest, if_match: Annotated[str, Header()]) -> dict[str, Any]:
        return await funder_service.review_application(DEMO_TENANT_ID, application_id, parse_version(if_match), body, str(uuid4()))

    @app.post("/api/v1/applications/{application_id}/offers", dependencies=[Depends(require_operator_token)], status_code=status.HTTP_201_CREATED, tags=["offers"])
    async def issue_offer(application_id: str, body: OfferRequest, if_match: Annotated[str, Header()]) -> dict[str, Any]:
        return await funder_service.issue_offer(DEMO_TENANT_ID, application_id, parse_version(if_match), body, str(uuid4()))

    @app.get("/api/v1/offers/{offer_id}", dependencies=[Depends(require_ui_token)], tags=["offers"])
    async def offer(offer_id: str) -> dict[str, Any]:
        return await funder_service.get_offer(DEMO_TENANT_ID, offer_id)

    @app.get("/api/v1/offers", dependencies=[Depends(require_ui_token)], tags=["offers"])
    async def offers() -> list[dict[str, Any]]:
        return (await funder_service.dashboard(DEMO_TENANT_ID))["offers"]

    @app.post("/api/v1/offers/{offer_id}/reserve", dependencies=[Depends(require_operator_token)], tags=["reservations"])
    async def reserve_offer(offer_id: str, body: ReserveRequest) -> dict[str, Any]:
        return await funder_service.reserve_offer(DEMO_TENANT_ID, offer_id, body, "funder_operator", str(uuid4()))

    @app.get("/api/v1/reservations", dependencies=[Depends(require_ui_token)], tags=["reservations"])
    async def reservations() -> list[dict[str, Any]]:
        return (await funder_service.dashboard(DEMO_TENANT_ID))["reservations"]

    @app.post("/api/v1/reservations/{reservation_id}/release", dependencies=[Depends(require_operator_token)], tags=["reservations"])
    async def release_reservation(reservation_id: str, body: ReleaseRequest, if_match: Annotated[str, Header()]) -> dict[str, Any]:
        return await funder_service.release_reservation(DEMO_TENANT_ID, reservation_id, parse_version(if_match), body, str(uuid4()))

    @app.post("/api/v1/reservations/{reservation_id}/commitments", dependencies=[Depends(require_operator_token)], tags=["commitments"])
    async def prepare_commitment(reservation_id: str, body: CommitmentPrepareRequest) -> dict[str, Any]:
        return await funder_service.prepare_commitment(DEMO_TENANT_ID, reservation_id, body, "funder_operator", str(uuid4()))

    @app.get("/api/v1/commitments", dependencies=[Depends(require_ui_token)], tags=["commitments"])
    async def commitments() -> list[dict[str, Any]]:
        return (await funder_service.dashboard(DEMO_TENANT_ID))["commitments"]

    @app.post("/api/v1/commitments/{commitment_id}/confirm", dependencies=[Depends(require_execution_token)], tags=["commitments"])
    async def confirm_commitment(commitment_id: str, body: CommitmentConfirmRequest) -> dict[str, Any]:
        return await funder_service.confirm_commitment(DEMO_TENANT_ID, commitment_id, body, "execution_gateway", str(uuid4()))

    @app.get("/api/v1/exposure", dependencies=[Depends(require_ui_token)], tags=["exposure"])
    async def exposure(msme_id: str | None = None) -> dict[str, Any]:
        return await funder_service.get_exposure(DEMO_TENANT_ID, msme_id)

    @app.get("/api/v1/events/stream", dependencies=[Depends(require_ui_token)], tags=["events"])
    async def events_stream() -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            seen: set[str] = set()
            while True:
                async with session() as db:
                    values = (await db.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == DEMO_TENANT_ID).order_by(OutboxEvent.created_at.desc()).limit(50))).all()
                for value in reversed(values):
                    if value.id in seen:
                        continue
                    seen.add(value.id)
                    payload = {"event_id": value.id, "event_type": value.event_type, "aggregate_id": value.aggregate_id, "version": value.aggregate_version, "occurred_at": value.created_at.isoformat()}
                    yield f"event: marketplace\ndata: {json.dumps(payload)}\n\n"
                yield ": keepalive\n\n"
                await asyncio.sleep(15)
        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/v1/integrations/events", status_code=status.HTTP_202_ACCEPTED, tags=["integrations"])
    async def consume_event(body: ExternalEventEnvelope, request: Request, x_event_signature: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        if not x_event_signature:
            raise HTTPException(status_code=401, detail="Event signature is required.")
        raw = await request.body()
        expected = hmac.new(get_settings().event_secret.get_secret_value().encode(), raw, hashlib.sha256).hexdigest()
        if not secrets.compare_digest(x_event_signature, expected):
            raise HTTPException(status_code=401, detail="Event signature is invalid.")
        if body.tenant_id != DEMO_TENANT_ID or body.aggregate.get("type") != "commitment":
            raise HTTPException(status_code=403, detail="Event is outside the marketplace tenant scope.")
        return await funder_service.consume_external_event(body, hashlib.sha256(raw).hexdigest())

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("funder_demo.main:app", host=settings.host, port=settings.port, reload=False)
