from uuid import UUID

import httpx

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


class GuardianClientError(RuntimeError):
    pass


class GuardianClient:
    def _headers(self) -> dict[str, str]:
        token = get_settings().service_token
        if token is None:
            raise GuardianClientError("Service token is not configured.")
        return {"Authorization": f"Bearer {token.get_secret_value()}"}

    async def evaluate(self, request: GuardianEvaluationRequest) -> GuardianEvaluationResponse:
        async with httpx.AsyncClient(base_url=str(get_settings().guardian_base_url), timeout=30) as client:
            response = await client.post(
                "/internal/guardian/evaluate",
                json=request.model_dump(mode="json"),
                headers=self._headers(),
            )
        if response.is_error:
            raise GuardianClientError(f"Guardian evaluation failed with status {response.status_code}.")
        return GuardianEvaluationResponse.model_validate(response.json())

    async def consume(
        self,
        *,
        token: str,
        tenant_id: UUID,
        call_id: UUID,
        request_hash: str,
        correlation_id: UUID,
    ) -> AuthorizationConsumeResult:
        body = AuthorizationConsumeRequest(
            token=token,
            call_id=call_id,
            request_hash=request_hash,
            correlation_id=correlation_id,
        )
        async with httpx.AsyncClient(base_url=str(get_settings().guardian_base_url), timeout=30) as client:
            response = await client.post(
                "/internal/guardian/authorizations/consume",
                json=body.model_dump(mode="json"),
                headers=self._headers(),
                params={"tenant_id": str(tenant_id)},
            )
        if response.is_error:
            raise GuardianClientError(f"Guardian authorization failed with status {response.status_code}.")
        return AuthorizationConsumeResult.model_validate(response.json())

    async def list_approvals(
        self, tenant_id: UUID, status_filter: str = "PENDING"
    ) -> list[ApprovalView]:
        async with httpx.AsyncClient(base_url=str(get_settings().guardian_base_url), timeout=30) as client:
            response = await client.get(
                "/internal/guardian/approvals",
                params={"tenant_id": str(tenant_id), "status_filter": status_filter},
                headers=self._headers(),
            )
        if response.is_error:
            raise GuardianClientError(f"Guardian approval query failed with status {response.status_code}.")
        return [ApprovalView.model_validate(item) for item in response.json()]

    async def get_approval(self, tenant_id: UUID, approval_id: UUID) -> ApprovalView:
        async with httpx.AsyncClient(base_url=str(get_settings().guardian_base_url), timeout=30) as client:
            response = await client.get(
                f"/internal/guardian/approvals/{approval_id}",
                params={"tenant_id": str(tenant_id)},
                headers=self._headers(),
            )
        if response.is_error:
            raise GuardianClientError(f"Guardian approval query failed with status {response.status_code}.")
        return ApprovalView.model_validate(response.json())

    async def act_on_approval(
        self, tenant_id: UUID, approval_id: UUID, action: ApprovalActionCreate
    ) -> ApprovalActionResult:
        async with httpx.AsyncClient(base_url=str(get_settings().guardian_base_url), timeout=30) as client:
            response = await client.post(
                f"/internal/guardian/approvals/{approval_id}/actions",
                params={"tenant_id": str(tenant_id)},
                json=action.model_dump(mode="json"),
                headers=self._headers(),
            )
        if response.is_error:
            raise GuardianClientError(f"Guardian approval action failed with status {response.status_code}.")
        return ApprovalActionResult.model_validate(response.json())

    async def authorize_approved(
        self,
        *,
        tenant_id: UUID,
        call_id: UUID,
        request_hash: str,
        correlation_id: UUID,
    ) -> GuardianEvaluationResponse:
        body = ApprovedAuthorizationRequest(
            call_id=call_id,
            request_hash=request_hash,
            correlation_id=correlation_id,
        )
        async with httpx.AsyncClient(base_url=str(get_settings().guardian_base_url), timeout=30) as client:
            response = await client.post(
                "/internal/guardian/authorizations/approved",
                params={"tenant_id": str(tenant_id)},
                json=body.model_dump(mode="json"),
                headers=self._headers(),
            )
        if response.is_error:
            raise GuardianClientError(
                f"Guardian approved authorization failed with status {response.status_code}."
            )
        return GuardianEvaluationResponse.model_validate(response.json())
