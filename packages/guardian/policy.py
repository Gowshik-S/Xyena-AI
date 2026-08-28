from dataclasses import dataclass, field

from packages.contracts.guardian import GuardianEvaluationRequest, GuardianOutcome
from packages.contracts.tools import ToolRiskClass


@dataclass(frozen=True)
class PolicyResult:
    outcome: GuardianOutcome
    reason_codes: list[str] = field(default_factory=list)
    constraints: dict[str, object] = field(default_factory=dict)


class GuardianPolicyEngine:
    """Deterministic, fail-closed baseline policy; model output never changes these rules."""

    def evaluate(self, evaluation: GuardianEvaluationRequest) -> PolicyResult:
        request = evaluation.request
        policy = evaluation.policy
        scope = request.scope

        if request.request_hash == "" or request.scope.tenant_id.int == 0:
            return PolicyResult(GuardianOutcome.BLOCK, ["INVALID_SCOPE"])
        if policy.allowed_agents and request.agent_name not in policy.allowed_agents:
            return PolicyResult(GuardianOutcome.BLOCK, ["AGENT_NOT_GRANTED"])
        if set(policy.required_roles) - set(scope.roles):
            return PolicyResult(GuardianOutcome.BLOCK, ["ROLE_REQUIRED"])
        if policy.required_purposes and request.purpose not in policy.required_purposes:
            return PolicyResult(GuardianOutcome.BLOCK, ["PURPOSE_NOT_ALLOWED"])
        consent_ids = {str(value) for value in scope.consent_ids}
        if set(policy.required_consents) - consent_ids:
            return PolicyResult(GuardianOutcome.BLOCK, ["CONSENT_REQUIRED"])
        if policy.side_effects and not request.idempotency_key:
            return PolicyResult(GuardianOutcome.BLOCK, ["IDEMPOTENCY_REQUIRED"])
        if policy.approval_mode == "ALWAYS" or policy.risk_class == ToolRiskClass.PRIVILEGED:
            return PolicyResult(
                GuardianOutcome.ESCALATE,
                ["HUMAN_APPROVAL_REQUIRED"],
                {"exact_request_hash": request.request_hash, "single_use": True},
            )
        if policy.risk_class in (ToolRiskClass.SENSITIVE_READ, ToolRiskClass.MUTATE):
            return PolicyResult(
                GuardianOutcome.ALLOW,
                ["PROTECTED_POLICY_SATISFIED"],
                {"exact_request_hash": request.request_hash, "single_use": True},
            )
        if policy.risk_class == ToolRiskClass.READ and policy.approval_mode == "NEVER":
            return PolicyResult(GuardianOutcome.ALLOW, ["SAFE_READ"])
        return PolicyResult(GuardianOutcome.BLOCK, ["NO_ALLOW_RULE"])
