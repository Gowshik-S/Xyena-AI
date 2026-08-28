from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.audit import append_audit_event
from packages.contracts.guardian import (
    ApprovalActionCreate,
    ApprovalActionResult,
    ApprovalView,
    ApprovedAuthorizationRequest,
    AuthorizationConsumeRequest,
    AuthorizationConsumeResult,
    GuardianEvaluationRequest,
    GuardianEvaluationResponse,
    GuardianOutcome,
)
from packages.persistence.models.guardian import (
    GuardianApprovalAction,
    GuardianApprovalRequest,
    GuardianAuthorization,
    GuardianDecision,
)
from packages.tools.canonical import canonical_hash

from .policy import GuardianPolicyEngine
from .signing import AuthorizationSigner, AuthorizationSigningError, token_hash


class GuardianServiceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GuardianService:
    def __init__(
        self,
        policy_engine: GuardianPolicyEngine | None = None,
        signer: AuthorizationSigner | None = None,
    ) -> None:
        self.policy_engine = policy_engine or GuardianPolicyEngine()
        self.signer = signer or AuthorizationSigner()

    async def evaluate(
        self, db: AsyncSession, evaluation: GuardianEvaluationRequest
    ) -> GuardianEvaluationResponse:
        request = evaluation.request
        now = datetime.now(UTC)
        existing = await db.scalar(
            select(GuardianDecision)
            .where(
                GuardianDecision.tenant_id == request.scope.tenant_id,
                GuardianDecision.tool_call_id == request.call_id,
                GuardianDecision.request_hash == request.request_hash,
                GuardianDecision.expires_at > now,
            )
            .order_by(GuardianDecision.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            return await self._resolve_existing(db, existing, evaluation)

        result = self.policy_engine.evaluate(evaluation)
        expires_at = now + timedelta(minutes=15)
        decision = GuardianDecision(
            id=uuid4(),
            tenant_id=request.scope.tenant_id,
            organization_id=request.scope.organization_id,
            user_id=request.scope.user_id,
            run_id=request.run_id,
            tool_call_id=request.call_id,
            request_hash=request.request_hash,
            evaluation_hash=canonical_hash(evaluation.model_dump(mode="json")),
            policy_bundle_version=request.scope.policy_bundle_version,
            risk_class=evaluation.policy.risk_class.value,
            outcome=result.outcome.value,
            reason_codes=result.reason_codes,
            constraints=result.constraints,
            expires_at=expires_at,
        )
        db.add(decision)
        await db.flush()

        approval: GuardianApprovalRequest | None = None
        if result.outcome == GuardianOutcome.ESCALATE:
            approval = GuardianApprovalRequest(
                id=uuid4(),
                tenant_id=request.scope.tenant_id,
                decision_id=decision.id,
                tool_call_id=request.call_id,
                requested_for_user_id=request.scope.user_id,
                summary=f"Approve {request.canonical_name} for purpose: {request.purpose}",
                risk_class=evaluation.policy.risk_class.value,
                status="PENDING",
                required_approver_roles=["guardian-approver"],
                expires_at=expires_at,
            )
            db.add(approval)
            await db.flush()

        await append_audit_event(
            db,
            tenant_id=request.scope.tenant_id,
            actor_type="SERVICE",
            actor_id="guardian",
            event_type="guardian.decision.created",
            subject_type="GUARDIAN_DECISION",
            subject_id=decision.id,
            correlation_id=request.scope.correlation_id,
            payload={"outcome": result.outcome.value, "reason_codes": result.reason_codes},
        )
        if result.outcome == GuardianOutcome.ALLOW:
            return await self._issue_authorization(db, decision)
        return GuardianEvaluationResponse(
            decision_id=decision.id,
            outcome=result.outcome,
            reason_codes=result.reason_codes,
            constraints=result.constraints,
            policy_bundle_version=decision.policy_bundle_version,
            approval_id=approval.id if approval else None,
            expires_at=expires_at,
        )

    async def _resolve_existing(
        self,
        db: AsyncSession,
        decision: GuardianDecision,
        evaluation: GuardianEvaluationRequest,
    ) -> GuardianEvaluationResponse:
        approval = await db.scalar(
            select(GuardianApprovalRequest).where(
                GuardianApprovalRequest.decision_id == decision.id
            )
        )
        if approval is not None and approval.status == "APPROVED":
            return await self._issue_authorization(db, decision)
        if approval is not None and approval.status in ("REJECTED", "EXPIRED"):
            return GuardianEvaluationResponse(
                decision_id=decision.id,
                outcome=GuardianOutcome.BLOCK,
                reason_codes=[f"APPROVAL_{approval.status}"],
                constraints=decision.constraints,
                policy_bundle_version=decision.policy_bundle_version,
                approval_id=approval.id,
                expires_at=decision.expires_at,
            )
        if decision.outcome == GuardianOutcome.ALLOW.value:
            return await self._issue_authorization(db, decision)
        return GuardianEvaluationResponse(
            decision_id=decision.id,
            outcome=GuardianOutcome(decision.outcome),
            reason_codes=decision.reason_codes,
            constraints=decision.constraints,
            policy_bundle_version=decision.policy_bundle_version,
            approval_id=approval.id if approval else None,
            expires_at=decision.expires_at,
        )

    async def _issue_authorization(
        self, db: AsyncSession, decision: GuardianDecision
    ) -> GuardianEvaluationResponse:
        authorization_id = uuid4()
        try:
            token, token_id, expires_at = self.signer.issue(
                authorization_id=authorization_id,
                tenant_id=decision.tenant_id,
                call_id=decision.tool_call_id,
                decision_id=decision.id,
                request_hash=decision.request_hash,
                constraints=decision.constraints,
            )
        except AuthorizationSigningError as exc:
            raise GuardianServiceError("SIGNING_UNAVAILABLE", str(exc)) from exc
        authorization = GuardianAuthorization(
            id=authorization_id,
            tenant_id=decision.tenant_id,
            decision_id=decision.id,
            tool_call_id=decision.tool_call_id,
            request_hash=decision.request_hash,
            token_id=token_id,
            token_hash=token_hash(token),
            constraints=decision.constraints,
            status="ACTIVE",
            issued_at=datetime.now(UTC),
            expires_at=expires_at,
        )
        db.add(authorization)
        await db.flush()
        return GuardianEvaluationResponse(
            decision_id=decision.id,
            outcome=GuardianOutcome.ALLOW,
            reason_codes=["EXACT_AUTHORIZATION_ISSUED"],
            constraints=decision.constraints,
            policy_bundle_version=decision.policy_bundle_version,
            authorization_id=authorization.id,
            authorization_token=token,
            expires_at=expires_at,
        )

    async def act_on_approval(
        self,
        db: AsyncSession,
        approval_id: UUID,
        tenant_id: UUID,
        action: ApprovalActionCreate,
    ) -> ApprovalActionResult:
        approval = await db.scalar(
            select(GuardianApprovalRequest)
            .where(
                GuardianApprovalRequest.id == approval_id,
                GuardianApprovalRequest.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if approval is None:
            raise GuardianServiceError("APPROVAL_NOT_FOUND", "Approval request was not found.")
        now = datetime.now(UTC)
        if approval.status != "PENDING":
            raise GuardianServiceError("APPROVAL_RESOLVED", "Approval is already resolved.")
        if approval.expires_at <= now:
            approval.status = "EXPIRED"
            raise GuardianServiceError("APPROVAL_EXPIRED", "Approval request has expired.")
        if set(approval.required_approver_roles) - set(action.actor_roles):
            raise GuardianServiceError("APPROVER_ROLE_REQUIRED", "Approver role is required.")

        approval.status = "APPROVED" if action.action == "APPROVE" else "REJECTED"
        approval.resolved_at = now
        approval.version += 1
        db.add(
            GuardianApprovalAction(
                id=uuid4(),
                tenant_id=tenant_id,
                approval_request_id=approval.id,
                actor_user_id=action.actor_user_id,
                actor_roles=list(action.actor_roles),
                action=action.action,
                reason=action.reason,
                correlation_id=action.correlation_id,
            )
        )
        await append_audit_event(
            db,
            tenant_id=tenant_id,
            actor_type="USER",
            actor_id=str(action.actor_user_id),
            event_type=f"guardian.approval.{approval.status.lower()}",
            subject_type="GUARDIAN_APPROVAL",
            subject_id=approval.id,
            correlation_id=action.correlation_id,
            payload={"reason": action.reason},
        )
        return ApprovalActionResult(
            approval=ApprovalView.model_validate(approval),
            resume_required=approval.status == "APPROVED",
        )

    async def consume(
        self, db: AsyncSession, request: AuthorizationConsumeRequest
    ) -> AuthorizationConsumeResult:
        try:
            claims = self.signer.verify(request.token)
        except AuthorizationSigningError as exc:
            raise GuardianServiceError("AUTHORIZATION_INVALID", str(exc)) from exc
        if claims.get("call_id") != str(request.call_id) or claims.get("request_hash") != request.request_hash:
            raise GuardianServiceError("AUTHORIZATION_SCOPE_MISMATCH", "Authorization scope mismatch.")
        authorization = await db.scalar(
            select(GuardianAuthorization)
            .where(
                GuardianAuthorization.token_hash == token_hash(request.token),
                GuardianAuthorization.tool_call_id == request.call_id,
                GuardianAuthorization.request_hash == request.request_hash,
            )
            .with_for_update()
        )
        now = datetime.now(UTC)
        if authorization is None or authorization.status != "ACTIVE":
            raise GuardianServiceError("AUTHORIZATION_NOT_ACTIVE", "Authorization is not active.")
        if authorization.expires_at <= now:
            authorization.status = "EXPIRED"
            raise GuardianServiceError("AUTHORIZATION_EXPIRED", "Authorization has expired.")
        authorization.status = "CONSUMED"
        authorization.consumed_at = now
        authorization.consumed_correlation_id = request.correlation_id
        return AuthorizationConsumeResult(
            authorization_id=authorization.id,
            consumed=True,
            constraints=authorization.constraints,
        )

    async def authorize_approved(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        request: ApprovedAuthorizationRequest,
    ) -> GuardianEvaluationResponse:
        row = (
            await db.execute(
                select(GuardianDecision, GuardianApprovalRequest)
                .join(
                    GuardianApprovalRequest,
                    GuardianApprovalRequest.decision_id == GuardianDecision.id,
                )
                .where(
                    GuardianDecision.tenant_id == tenant_id,
                    GuardianDecision.tool_call_id == request.call_id,
                    GuardianDecision.request_hash == request.request_hash,
                    GuardianApprovalRequest.status == "APPROVED",
                )
                .order_by(GuardianDecision.created_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            raise GuardianServiceError(
                "APPROVED_DECISION_NOT_FOUND", "No approved decision matches this exact request."
            )
        decision, _approval = row
        if decision.expires_at <= datetime.now(UTC):
            raise GuardianServiceError("DECISION_EXPIRED", "The approved decision has expired.")
        return await self._issue_authorization(db, decision)
