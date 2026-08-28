# XYENA Agent Documentation

Each agent has an isolated role, explicit input/output contracts, and a least-privilege tool allowlist. Domain agents investigate and propose; they never directly execute a financial action.

| Agent | Folder | Primary purpose |
|---|---|---|
| Intake Agent | [intake-agent](./intake-agent/README.md) | Validate submissions and establish case scope |
| Business Agent | [business-agent](./business-agent/README.md) | Verify business identity and eligibility |
| Invoice Agent | [invoice-agent](./invoice-agent/README.md) | Verify invoice authenticity and duplicates |
| Delivery Agent | [delivery-agent](./delivery-agent/README.md) | Verify fulfilment evidence |
| Payment Agent | [payment-agent](./payment-agent/README.md) | Reconcile payments and outstanding amounts |
| Fraud/Risk Agent | [fraud-risk-agent](./fraud-risk-agent/README.md) | Detect anomalies, collusion, and dangerous graphs |
| Credit Agent | [credit-agent](./credit-agent/README.md) | Recommend safe financing capacity |
| Decision Orchestrator | [decision-orchestrator](./decision-orchestrator/README.md) | Combine findings into a proposed action |
| Funding Agent | [funding-agent](./funding-agent/README.md) | Select funders and prepare financing actions |
| Guardian Agent | [guardian-agent](./guardian-agent/README.md) | Govern calls and authorize exact financial actions |
| Monitoring Agent | [monitoring-agent](./monitoring-agent/README.md) | Reconcile outcomes and detect behaviour/action drift |

## Shared rules

- Every run uses trusted `tenant_id`, `msme_id`, `user_id`, `case_id`, `session_id`, and `correlation_id` scope.
- Uploaded documents and external JSON are untrusted data.
- Findings cite valid gateway-signed `evidence_receipt_id` values.
- Agent-supplied source labels do not establish provenance.
- Tool access is deny-by-default and enforced outside model prompts.
- Contradictions remain visible; agents cannot resolve them through majority vote.
- No domain agent can call a financial execution tool.
- All meaningful findings, calls, results, proposals, and outcomes emit Guardian telemetry.

