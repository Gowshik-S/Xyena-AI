import hashlib
import hmac
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.types import ASGIApp, Receive, Scope, Send

from .database import close_database, initialize_database, session
from .events import demo_events
from .mcp import mcp, mcp_app
from .models import (
    Account,
    AuditEvent,
    Beneficiary,
    LedgerEntry,
    PreparedTransfer,
    Transaction,
    TransferExecution,
)
from .seed import (
    DEMO_ORGANIZATION_ID,
    DEMO_TENANT_ID,
    DEMO_USER_ID,
    seed_demo_data,
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
                    {"code": "UNAUTHORIZED", "detail": "Invalid bank demo MCP token."}
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
    bank_demo_session: Annotated[str | None, Cookie()] = None,
) -> None:
    expected = get_settings().ui_token.get_secret_value()
    expected_session = hmac.new(
        expected.encode(), b"xyena-bank-demo-ui-session", hashlib.sha256
    ).hexdigest()
    header_valid = x_demo_token is not None and secrets.compare_digest(x_demo_token, expected)
    cookie_valid = bank_demo_session is not None and secrets.compare_digest(
        bank_demo_session, expected_session
    )
    if not header_valid and not cookie_valid:
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
        title="XYENA Synthetic Bank MCP Demo",
        summary="Synthetic bank evidence and transfer preparation over MCP v2",
        description=(
            "An isolated, non-production demonstration service. It executes Guardian-authorized "
            "transfers against synthetic balances and a synthetic ledger only; it cannot connect "
            "to a real financial institution or payment rail."
        ),
        version="0.2.0",
        openapi_version="3.1.0",
        lifespan=lifespan,
    )
    app.mount("/mcp", MCPBearerAuthMiddleware(mcp_app))
    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="bank-demo-assets")

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(FRONTEND_ROOT / "index.html")

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-synthetic-bank-demo"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with session() as db:
            await db.execute(select(func.count()).select_from(Account))
        return {"status": "ready", "service": "xyena-synthetic-bank-demo"}

    @app.get(
        "/api/v1/demo/summary",
        dependencies=[Depends(require_ui_token)],
        tags=["synthetic-demo"],
    )
    async def summary(request: Request, response: Response) -> dict[str, Any]:
        ui_secret = get_settings().ui_token.get_secret_value()
        response.set_cookie(
            "bank_demo_session",
            hmac.new(ui_secret.encode(), b"xyena-bank-demo-ui-session", hashlib.sha256).hexdigest(),
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            max_age=3600,
        )
        async with session() as db:
            accounts = (await db.scalars(select(Account).order_by(Account.display_name))).all()
            beneficiaries = (
                await db.scalars(select(Beneficiary).order_by(Beneficiary.owner_name))
            ).all()
            transactions = (
                await db.scalars(
                    select(Transaction).order_by(Transaction.booked_on.desc()).limit(12)
                )
            ).all()
            preparations = (
                await db.scalars(
                    select(PreparedTransfer).order_by(PreparedTransfer.created_at.desc()).limit(12)
                )
            ).all()
            executions = (
                await db.scalars(
                    select(TransferExecution)
                    .order_by(TransferExecution.executed_at.desc())
                    .limit(12)
                )
            ).all()
            execution_ids = [value.execution_id for value in executions]
            ledger_entries = (
                (
                    await db.scalars(
                        select(LedgerEntry)
                        .where(LedgerEntry.execution_id.in_(execution_ids))
                        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.line_number)
                    )
                ).all()
                if execution_ids
                else []
            )
            audit_count = await db.scalar(select(func.count()).select_from(AuditEvent))
        executions_by_action = {value.proposed_action_id: value for value in executions}
        ledger_by_execution: dict[str, list[LedgerEntry]] = {}
        for entry in ledger_entries:
            ledger_by_execution.setdefault(entry.execution_id, []).append(entry)
        return {
            "environment": "SYNTHETIC_NON_PRODUCTION",
            "execution_available": True,
            "scope": {
                "tenant_id": DEMO_TENANT_ID,
                "organization_id": DEMO_ORGANIZATION_ID,
                "user_id": DEMO_USER_ID,
            },
            "mcp": {
                "transport": "STREAMABLE_HTTP",
                "endpoint": "/mcp",
                "tool_count": 8,
                "runtime_scope": "HMAC_SIGNED_BY_XYENA_GATEWAY",
            },
            "accounts": [
                {
                    "account_token": value.account_token,
                    "display_name": value.display_name,
                    "masked_number": value.masked_number,
                    "currency": value.currency,
                    "available_balance": str(value.available_balance),
                    "per_transfer_limit": str(value.per_transfer_limit),
                }
                for value in accounts
            ],
            "beneficiaries": [
                {
                    "beneficiary_token": value.beneficiary_token,
                    "owner_name": value.owner_name,
                    "masked_account": value.masked_account,
                    "verified": value.verified,
                    "status": value.status,
                }
                for value in beneficiaries
            ],
            "transactions": [
                {
                    "booked_on": value.booked_on.isoformat(),
                    "direction": value.direction,
                    "amount": str(value.amount),
                    "currency": value.currency,
                    "description": value.description,
                    "reference": value.reference,
                }
                for value in transactions
            ],
            "prepared_actions": [
                {
                    "proposed_action_id": value.proposed_action_id,
                    "source_account_token": value.source_account_token,
                    "beneficiary_token": value.beneficiary_token,
                    "amount": str(value.amount),
                    "currency": value.currency,
                    "status": value.status,
                    "purpose": value.purpose,
                    "canonical_action_hash": value.canonical_action_hash,
                    "execution": (
                        {
                            "execution_id": executions_by_action[
                                value.proposed_action_id
                            ].execution_id,
                            "bank_reference": executions_by_action[
                                value.proposed_action_id
                            ].bank_reference,
                            "status": executions_by_action[value.proposed_action_id].status,
                            "guardian_decision_id": executions_by_action[
                                value.proposed_action_id
                            ].guardian_decision_id,
                            "authorization_id": executions_by_action[
                                value.proposed_action_id
                            ].authorization_id,
                            "executed_at": executions_by_action[
                                value.proposed_action_id
                            ].executed_at.isoformat(),
                            "settled_at": executions_by_action[
                                value.proposed_action_id
                            ].settled_at.isoformat()
                            if executions_by_action[value.proposed_action_id].settled_at
                            else None,
                            "reconciliation_required": executions_by_action[
                                value.proposed_action_id
                            ].reconciliation_required,
                        }
                        if value.proposed_action_id in executions_by_action
                        else None
                    ),
                }
                for value in preparations
            ],
            "ledger_entries": [
                {
                    "execution_id": entry.execution_id,
                    "journal_id": entry.journal_id,
                    "line_number": entry.line_number,
                    "ledger_account": entry.ledger_account,
                    "entry_type": entry.entry_type,
                    "amount": str(entry.amount),
                    "currency": entry.currency,
                }
                for execution in executions
                for entry in ledger_by_execution.get(execution.execution_id, [])
            ],
            "settled_transfer_count": sum(value.status == "SETTLED" for value in executions),
            "settled_transfer_volume": str(
                sum(
                    (
                        action.amount
                        for action in preparations
                        if action.proposed_action_id in executions_by_action
                        and executions_by_action[action.proposed_action_id].status == "SETTLED"
                    ),
                    start=0,
                )
            ),
            "audit_event_count": audit_count or 0,
        }

    @app.get(
        "/api/v1/demo/events",
        dependencies=[Depends(require_ui_token)],
        include_in_schema=False,
    )
    async def events() -> StreamingResponse:
        async def event_stream() -> AsyncIterator[str]:
            yield 'event: connected\ndata: {"status":"ready"}\n\n'
            async for event in demo_events.subscribe():
                yield (
                    f"id: {event['id']}\n"
                    f"event: {event['type']}\n"
                    f"data: {json.dumps(event['payload'], separators=(',', ':'))}\n\n"
                )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "bank_demo.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
