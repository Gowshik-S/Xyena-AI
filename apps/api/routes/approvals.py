from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_correlation_id, get_principal, get_scoped_session
from packages.contracts.guardian import (
    ApprovalActionCreate,
    ApprovalActionResult,
    ApprovalDecisionRequest,
    ApprovalView,
)
from packages.contracts.identity import AuthenticatedPrincipal
from packages.guardian import GuardianClient, GuardianClientError
from packages.persistence.models.ops import Job

router = APIRouter(prefix="/api/v1/approvals", tags=["Approvals"])
guardian_client = GuardianClient()


@router.get("", operation_id="approvals_list", response_model=list[ApprovalView])
async def list_approvals(
    status_filter: str = "PENDING",
    principal: AuthenticatedPrincipal = Depends(get_principal),
) -> list[ApprovalView]:
    try:
        return await guardian_client.list_approvals(principal.tenant_id, status_filter)
    except GuardianClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{approval_id}", operation_id="approvals_get", response_model=ApprovalView)
async def get_approval(
    approval_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
) -> ApprovalView:
    try:
        return await guardian_client.get_approval(principal.tenant_id, approval_id)
    except GuardianClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/{approval_id}/actions",
    operation_id="approvals_act",
    response_model=ApprovalActionResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def act_on_approval(
    approval_id: UUID,
    body: ApprovalDecisionRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> ApprovalActionResult:
    if "guardian-approver" not in principal.roles:
        raise HTTPException(status_code=403, detail="The guardian-approver role is required.")
    action = ApprovalActionCreate(
        action=body.action,
        actor_user_id=principal.user_id,
        actor_roles=principal.roles,
        reason=body.reason,
        correlation_id=correlation_id,
    )
    try:
        result = await guardian_client.act_on_approval(principal.tenant_id, approval_id, action)
    except GuardianClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result.resume_required:
        db.add(
            Job(
                id=uuid4(),
                tenant_id=principal.tenant_id,
                job_type="mcp.resume",
                payload={
                    "approval_id": str(approval_id),
                    "tool_call_id": str(result.approval.tool_call_id),
                    "correlation_id": str(correlation_id),
                },
                state="AVAILABLE",
                available_at=datetime.now(UTC),
                max_attempts=5,
            )
        )
    return result
