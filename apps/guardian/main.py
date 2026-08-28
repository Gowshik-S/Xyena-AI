from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select

from apps.api.errors import register_error_handlers
from apps.api.middleware import CorrelationMiddleware
from packages.config import get_settings
from packages.contracts.guardian import (
    ApprovalActionCreate,
    ApprovalActionResult,
    ApprovalView,
    ApprovedAuthorizationRequest,
    AuthorizationConsumeRequest,
    AuthorizationConsumeResult,
    GuardianEvaluationRequest,
    GuardianEvaluationResponse,
)
from packages.guardian.service import GuardianService, GuardianServiceError
from packages.identity.service_auth import require_service_token
from packages.observability import configure_logging, configure_telemetry
from packages.persistence import get_database
from packages.persistence.models.guardian import GuardianApprovalRequest

guardian_service = GuardianService()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield
    await get_database().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Xyena Guardian",
        summary="Independent policy, approval, and exact-request authorization plane",
        version="0.1.0",
        openapi_version="3.1.0",
        openapi_url="/openapi.json" if settings.env != "production" else None,
        docs_url="/docs" if settings.env != "production" else None,
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationMiddleware)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live", "service": "xyena-guardian"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with get_database().engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
        return {"status": "ready", "service": "xyena-guardian"}

    @app.post(
        "/internal/guardian/evaluate",
        response_model=GuardianEvaluationResponse,
        dependencies=[Depends(require_service_token)],
        tags=["decisions"],
    )
    async def evaluate(body: GuardianEvaluationRequest) -> GuardianEvaluationResponse:
        scope = body.request.scope
        async with get_database().session(
            tenant_id=scope.tenant_id,
            user_id=scope.user_id,
            service_role="guardian",
        ) as db:
            try:
                return await guardian_service.evaluate(db, body)
            except GuardianServiceError as exc:
                raise HTTPException(status_code=503, detail=f"{exc.code}: {exc}") from exc

    @app.post(
        "/internal/guardian/authorizations/consume",
        response_model=AuthorizationConsumeResult,
        dependencies=[Depends(require_service_token)],
        tags=["authorizations"],
    )
    async def consume(
        body: AuthorizationConsumeRequest, tenant_id: UUID
    ) -> AuthorizationConsumeResult:
        async with get_database().session(tenant_id=tenant_id, service_role="guardian") as db:
            try:
                return await guardian_service.consume(db, body)
            except GuardianServiceError as exc:
                raise HTTPException(status_code=403, detail=f"{exc.code}: {exc}") from exc

    @app.post(
        "/internal/guardian/authorizations/approved",
        response_model=GuardianEvaluationResponse,
        dependencies=[Depends(require_service_token)],
        tags=["authorizations"],
    )
    async def authorize_approved(
        body: ApprovedAuthorizationRequest, tenant_id: UUID
    ) -> GuardianEvaluationResponse:
        async with get_database().session(tenant_id=tenant_id, service_role="guardian") as db:
            try:
                return await guardian_service.authorize_approved(db, tenant_id, body)
            except GuardianServiceError as exc:
                raise HTTPException(status_code=403, detail=f"{exc.code}: {exc}") from exc

    @app.get(
        "/internal/guardian/approvals",
        response_model=list[ApprovalView],
        dependencies=[Depends(require_service_token)],
        tags=["approvals"],
    )
    async def list_approvals(tenant_id: UUID, status_filter: str = "PENDING") -> list[ApprovalView]:
        async with get_database().session(tenant_id=tenant_id, service_role="guardian") as db:
            query = select(GuardianApprovalRequest).where(
                GuardianApprovalRequest.tenant_id == tenant_id
            )
            if status_filter:
                query = query.where(GuardianApprovalRequest.status == status_filter)
            values = (await db.scalars(query.order_by(GuardianApprovalRequest.created_at.desc()))).all()
            return [ApprovalView.model_validate(value) for value in values]

    @app.get(
        "/internal/guardian/approvals/{approval_id}",
        response_model=ApprovalView,
        dependencies=[Depends(require_service_token)],
        tags=["approvals"],
    )
    async def get_approval(approval_id: UUID, tenant_id: UUID) -> ApprovalView:
        async with get_database().session(tenant_id=tenant_id, service_role="guardian") as db:
            value = await db.scalar(
                select(GuardianApprovalRequest).where(
                    GuardianApprovalRequest.id == approval_id,
                    GuardianApprovalRequest.tenant_id == tenant_id,
                )
            )
            if value is None:
                raise HTTPException(status_code=404, detail="Approval request not found.")
            return ApprovalView.model_validate(value)

    @app.post(
        "/internal/guardian/approvals/{approval_id}/actions",
        response_model=ApprovalActionResult,
        dependencies=[Depends(require_service_token)],
        tags=["approvals"],
    )
    async def act(
        approval_id: UUID, tenant_id: UUID, body: ApprovalActionCreate
    ) -> ApprovalActionResult:
        async with get_database().session(
            tenant_id=tenant_id,
            user_id=body.actor_user_id,
            service_role="guardian",
        ) as db:
            try:
                return await guardian_service.act_on_approval(db, approval_id, tenant_id, body)
            except GuardianServiceError as exc:
                status_code = 404 if exc.code == "APPROVAL_NOT_FOUND" else 409
                raise HTTPException(status_code=status_code, detail=f"{exc.code}: {exc}") from exc

    register_error_handlers(app)
    configure_telemetry(app, "xyena-guardian")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "apps.guardian.main:app",
        host=settings.api_host,
        port=settings.guardian_port,
        reload=False,
    )
