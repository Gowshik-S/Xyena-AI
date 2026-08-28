import json
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select
from starlette.types import ASGIApp, Receive, Scope, Send

from .database import close_database, initialize_database, session
from .mcp import mcp, mcp_app
from .models import (AuditEvent, JournalEntry, JournalLine, LedgerAccount,
                     PaymentInstruction, ReconciliationRecord, SettlementReceipt)
from .seed import DEMO_ORGANIZATION_ID, DEMO_TENANT_ID, DEMO_USER_ID, seed_demo_data
from .service import ledger_service
from .settings import get_settings

SOURCE_FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
PACKAGED_FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
FRONTEND_ROOT = SOURCE_FRONTEND_ROOT if SOURCE_FRONTEND_ROOT.is_dir() else PACKAGED_FRONTEND_ROOT
PAGES = {"/": "index.html", "/accounts": "accounts.html", "/journals": "journals.html",
         "/payments": "payments.html", "/reconciliation": "reconciliation.html",
         "/mcp-connection": "mcp-connection.html"}


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
                body = json.dumps({"code": "UNAUTHORIZED", "detail": "Invalid ledger MCP token."}).encode()
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


async def require_ui_token(x_demo_token: Annotated[str | None, Header()] = None) -> None:
    if x_demo_token is None or not secrets.compare_digest(
            x_demo_token, get_settings().ui_token.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid ledger dashboard token.")


async def require_event_token(x_settlement_token: Annotated[str | None, Header()] = None) -> None:
    if x_settlement_token is None or not secrets.compare_digest(
            x_settlement_token, get_settings().settlement_event_token.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid settlement event token.")


class BankSettlement(BaseModel):
    event_id: str
    tenant_id: str
    payment_id: str
    bank_execution_id: str
    bank_reference: str
    amount: str
    currency: str
    settled_at: datetime


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await initialize_database()
    await seed_demo_data()
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield
    await close_database()


def create_app() -> FastAPI:
    app = FastAPI(title="XYENA Ledger and Payment Operations",
                  summary="Double-entry journals, governed disbursements and settlement reconciliation",
                  description="Synthetic non-production payment ledger connected to Xyena Guardian and Bank MCP.",
                  version="1.0.0", openapi_version="3.1.0", lifespan=lifespan)
    app.mount("/mcp", MCPBearerAuthMiddleware(mcp_app))
    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="ledger-assets")
    def page(filename: str) -> Callable[[], Awaitable[FileResponse]]:
        async def value() -> FileResponse:
            return FileResponse(FRONTEND_ROOT / filename)
        return value
    for route, filename in PAGES.items():
        app.add_api_route(route, page(filename), methods=["GET"], include_in_schema=False)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-ledger-payment"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with session() as db:
            await db.execute(select(func.count()).select_from(LedgerAccount))
        return {"status": "ready", "service": "xyena-ledger-payment"}

    @app.post("/internal/v1/bank-settlements", dependencies=[Depends(require_event_token)],
              tags=["settlement-events"])
    async def bank_settlement(value: BankSettlement) -> dict[str, Any]:
        return await ledger_service.accept_bank_settlement(**value.model_dump())

    @app.get("/api/v1/demo/summary", dependencies=[Depends(require_ui_token)], tags=["operations"])
    async def summary() -> dict[str, Any]:
        async with session() as db:
            accounts = (await db.scalars(select(LedgerAccount).order_by(LedgerAccount.code))).all()
            journals = (await db.scalars(select(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(20))).all()
            payments = (await db.scalars(select(PaymentInstruction).order_by(PaymentInstruction.created_at.desc()).limit(20))).all()
            reconciliations = (await db.scalars(select(ReconciliationRecord).limit(20))).all()
            receipts = await db.scalar(select(func.count()).select_from(SettlementReceipt)) or 0
            audit_count = await db.scalar(select(func.count()).select_from(AuditEvent)) or 0
            journal_views = []
            for journal in journals:
                lines = (await db.scalars(select(JournalLine).where(JournalLine.journal_id == journal.journal_id))).all()
                journal_views.append(ledger_service._journal_projection(journal, lines))
        return {"environment": "SYNTHETIC_NON_PRODUCTION",
                "scope": {"tenant_id": DEMO_TENANT_ID, "organization_id": DEMO_ORGANIZATION_ID,
                          "user_id": DEMO_USER_ID},
                "mcp": {"endpoint": "/mcp", "transport": "STREAMABLE_HTTP", "tool_count": 8,
                        "runtime_scope": "HMAC_SIGNED_BY_XYENA_GATEWAY"},
                "invariants": ["DEBITS_EQUAL_CREDITS", "POSTED_JOURNALS_IMMUTABLE",
                               "GUARDIAN_CALL_SINGLE_USE", "UNKNOWN_NEVER_BLINDLY_RETRIED"],
                "accounts": [ledger_service._account_projection(v) for v in accounts],
                "journals": journal_views,
                "payments": [ledger_service._payment_projection(v) for v in payments],
                "reconciliations": [ledger_service._reconciliation_projection(v) for v in reconciliations],
                "settlement_receipt_count": receipts, "audit_event_count": audit_count}
    return app


app = create_app()


def run() -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run("ledger_demo.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
