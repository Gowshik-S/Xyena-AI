# Bank MCP Server — Configuration Guide

## 1. Purpose

This document defines the configuration model for the XYENA Bank MCP Server described in [BANK_MCP.md](./BANK_MCP.md).

The server exposes:

- consented Account Aggregator evidence tools;
- account, transaction, beneficiary, balance, and limit tools;
- transfer and reversal preparation tools;
- Guardian-authorized financial execution tools.

The configuration must keep read-only evidence connectors separate from state-changing banking and payment connectors.

---

## 2. Suggested Files

```text
apps/mcp-server/
├── config/
│   ├── bank-mcp.config.yaml
│   ├── bank-mcp.tools.yaml
│   ├── bank-mcp.policies.yaml
│   ├── bank-mcp.schemas.yaml
│   └── environments/
│       ├── development.yaml
│       ├── test.yaml
│       └── production.yaml
├── src/
│   ├── servers/bank/
│   ├── connectors/account-aggregator/
│   ├── connectors/core-banking/
│   ├── connectors/beneficiary/
│   └── connectors/payment-rail/
└── secrets/
    └── README.md
```

Secrets must not be committed to these files. Configuration references secret-manager keys or environment-variable names.

---

## 3. Complete Configuration Example

```yaml
version: "1.0"

server:
  id: "xyena-bank-mcp"
  name: "XYENA Bank MCP Server"
  environment: "development"
  transport: "stdio"                 # development: stdio; deployment: approved remote transport
  host: "127.0.0.1"
  port: 7410
  request_timeout_ms: 15000
  graceful_shutdown_ms: 10000
  max_request_bytes: 1048576

identity:
  workload_identity_provider: "local-dev"
  trusted_gateway_audiences:
    - "xyena-mcp-gateway"
  required_scope_fields:
    - "tenant_id"
    - "msme_id"
    - "user_id"
    - "case_id"
    - "correlation_id"
  reject_model_supplied_scope_override: true

secrets:
  provider: "environment"             # production: managed secret store
  references:
    aa_client_id: "BANK_MCP_AA_CLIENT_ID"
    aa_client_secret: "BANK_MCP_AA_CLIENT_SECRET"
    bank_client_id: "BANK_MCP_BANK_CLIENT_ID"
    bank_client_secret: "BANK_MCP_BANK_CLIENT_SECRET"
    payment_signing_key: "BANK_MCP_PAYMENT_SIGNING_KEY"
    evidence_receipt_signing_key: "BANK_MCP_EVIDENCE_SIGNING_KEY"
    guardian_verification_key: "BANK_MCP_GUARDIAN_PUBLIC_KEY"

connectors:
  account_aggregator:
    enabled: true
    mode: "mock"                       # mock | sandbox | production
    base_url: "https://aa-sandbox.example.invalid"
    read_only: true
    support_transactions: false
    mutual_tls: true
    verify_upstream_signatures: true
    consent_required: true
    consent_artifact_max_age_seconds: 300
    allowed_information_types:
      - "DEPOSIT"
      - "TERM_DEPOSIT"
      - "RECURRING_DEPOSIT"
      - "MUTUAL_FUNDS"
      - "EQUITIES"
      - "GST"
    max_fetch_range_days: 365
    max_fetch_frequency_per_consent_per_day: 4
    secret_refs:
      client_id: "aa_client_id"
      client_secret: "aa_client_secret"

  core_banking:
    enabled: true
    mode: "mock"
    base_url: "https://bank-sandbox.example.invalid"
    mutual_tls: true
    endpoint_allowlist:
      - "/v1/accounts"
      - "/v1/balances"
      - "/v1/transactions"
      - "/v1/transfers/status"
    secret_refs:
      client_id: "bank_client_id"
      client_secret: "bank_client_secret"

  beneficiary_verification:
    enabled: true
    mode: "mock"
    base_url: "https://beneficiary-sandbox.example.invalid"
    require_account_ownership_match: true
    cache_ttl_seconds: 900
    reject_name_only_verification: true

  payment_rail:
    enabled: true
    mode: "mock"
    base_url: "https://payment-sandbox.example.invalid"
    execution_enabled: true
    guardian_authorization_required: true
    allowed_rails:
      - "MOCK_BANK_RAIL"
    allowed_currencies:
      - "INR"
    secret_refs:
      signing_key: "payment_signing_key"

evidence_trust:
  enabled: true
  raw_payload_access: "gateway-only"
  retain_raw_payload_days: 30
  encrypt_raw_payloads: true
  issue_signed_receipts: true
  receipt_signing_key_ref: "evidence_receipt_signing_key"
  strict_output_projection: true
  reject_unknown_fields: true
  reject_invalid_encoding: true
  strip_control_characters: true
  detect_instruction_like_strings: true
  quarantine_on_injection_signal: true
  maximum_string_length: 500
  include_security_flags_in_receipt: true
  trust_external_source_field: false

consent:
  required_for_aa_tools: true
  purpose_required: true
  purpose_max_length: 300
  enforce_data_type_scope: true
  enforce_date_range_scope: true
  enforce_usage_count: true
  allow_partial_revocation: true
  log_every_consent_use: true
  expired_consent_behavior: "deny"
  revoked_consent_behavior: "deny"

guardian:
  verification_key_ref: "guardian_verification_key"
  accepted_issuer: "xyena-guardian"
  accepted_audience: "xyena-bank-mcp"
  require_for_tool_classes:
    - "financial_execution"
    - "high_risk_state_change"
    - "financial_control"
  authorization_max_age_seconds: 120
  require_single_use_nonce: true
  require_canonical_action_hash: true
  require_current_mandate: true
  require_current_policy_version: true
  reject_parameter_drift: true
  fail_closed: true

idempotency:
  required_for:
    - "bank.transfers.prepare"
    - "bank.transfers.execute"
    - "bank.reversals.prepare"
    - "bank.reversals.execute"
    - "bank.beneficiaries.prepare_change"
    - "bank.beneficiaries.execute_change"
  key_ttl_hours: 72
  reject_same_key_different_hash: true
  unknown_execution_requires_reconciliation: true

limits:
  currency: "INR"
  defaults:
    per_transfer: "500000.00"
    per_day: "1000000.00"
    per_beneficiary_per_day: "500000.00"
    transfer_count_per_hour: 5
  allow_tenant_policy_override: true
  override_must_be_more_restrictive: true
  enforce_bank_reported_limits: true
  enforce_mandate_limits: true
  enforce_exposure_limits: true
  atomic_reservation_required: true

beneficiaries:
  require_verification_before_transfer: true
  verification_max_age_seconds: 900
  new_beneficiary_cooling_period_seconds: 86400
  change_requires_human_approval: true
  detect_account_change: true
  detect_name_mismatch: true
  detect_unusual_destination: true

reversals:
  enabled: true
  prepare_only_by_default: true
  human_approval_required: true
  require_original_execution_receipt: true
  require_bank_reversibility_confirmation: true

tool_policy:
  default: "deny"
  allowlists_by_agent:
    business-agent:
      - "bank.accounts.get"
      - "bank.beneficiaries.verify"
    payment-agent:
      - "bank.accounts.get_balance"
      - "bank.transactions.list"
      - "bank.transfers.get_status"
    credit-agent:
      - "bank.accounts.get_balance"
      - "bank.transactions.list"
      - "bank.limits.get"
    funding-agent:
      - "bank.beneficiaries.verify"
      - "bank.transfers.prepare"
    execution-gateway:
      - "bank.transfers.execute"
      - "bank.beneficiaries.execute_change"
      - "bank.reversals.execute"
      - "bank.holds.place"
      - "bank.holds.release"
  deny_direct_execution_for_domain_agents: true

telemetry:
  emit_tool_request_events: true
  emit_tool_result_events: true
  emit_consent_events: true
  emit_evidence_receipt_events: true
  emit_execution_events: true
  emit_security_flags: true
  destination: "event-outbox"
  include_raw_payloads: false
  redact_account_numbers: true
  redact_credentials: true
  correlation_required: true

audit:
  append_only: true
  sign_records: true
  required_before_financial_execution: true
  include:
    - "trusted_scope"
    - "agent_id"
    - "tool_name"
    - "purpose"
    - "argument_hash"
    - "result_hash"
    - "evidence_receipt_ids"
    - "guardian_decision_id"
    - "execution_receipt_id"
    - "timestamps"

resilience:
  retries:
    read_calls: 2
    execution_calls: 0
  circuit_breaker:
    enabled: true
    failure_threshold: 5
    reset_timeout_seconds: 60
  execution_retry_requires_status_lookup: true
  fail_closed_on_audit_failure: true
  fail_closed_on_guardian_failure: true
```

Values shown above are safe prototype defaults, not universal production limits. Production amounts, retention, consent frequency, cooling periods, rails, and connector settings must come from applicable institution and regulatory policy.

---

## 4. Tool Configuration

```yaml
tools:
  bank.aa.create_consent:
    class: "sensitive_state_change"
    allowed_callers: ["intake-agent", "consent-service"]
    consent_required: false
    purpose_required: true
    guardian_required: false
    audit_required: true

  bank.aa.fetch_information:
    class: "sensitive_read"
    allowed_callers: ["business-agent", "payment-agent", "credit-agent"]
    consent_required: true
    purpose_required: true
    output_route: "evidence-trust-gateway"
    expose_raw_result_to_agent: false
    guardian_required: false
    audit_required: true

  bank.transactions.list:
    class: "sensitive_read"
    allowed_callers: ["payment-agent", "credit-agent"]
    consent_required: true
    purpose_required: true
    maximum_range_days: 365
    output_route: "evidence-trust-gateway"
    expose_raw_result_to_agent: false

  bank.transfers.prepare:
    class: "financial_preparation"
    allowed_callers: ["funding-agent", "decision-orchestrator"]
    guardian_required: false
    moves_funds: false
    canonical_action_required: true
    idempotency_required: true

  bank.transfers.execute:
    class: "financial_execution"
    allowed_callers: ["execution-gateway"]
    guardian_required: true
    human_approval_required: false
    canonical_action_hash_required: true
    single_use_authorization_required: true
    idempotency_required: true
    atomic_reservation_required: true

  bank.beneficiaries.execute_change:
    class: "high_risk_state_change"
    allowed_callers: ["execution-gateway"]
    guardian_required: true
    human_approval_required: true
    cooling_period_required: true

  bank.reversals.execute:
    class: "high_risk_financial_execution"
    allowed_callers: ["execution-gateway"]
    guardian_required: true
    human_approval_required: true
    original_execution_receipt_required: true
```

---

## 5. Environment Variables

```dotenv
BANK_MCP_ENVIRONMENT=development
BANK_MCP_TRANSPORT=stdio
BANK_MCP_HOST=127.0.0.1
BANK_MCP_PORT=7410

BANK_MCP_AA_CLIENT_ID=secret-reference-only
BANK_MCP_AA_CLIENT_SECRET=secret-reference-only
BANK_MCP_BANK_CLIENT_ID=secret-reference-only
BANK_MCP_BANK_CLIENT_SECRET=secret-reference-only
BANK_MCP_PAYMENT_SIGNING_KEY=secret-reference-only
BANK_MCP_EVIDENCE_SIGNING_KEY=secret-reference-only
BANK_MCP_GUARDIAN_PUBLIC_KEY=public-key-or-secret-reference

BANK_MCP_AA_BASE_URL=https://aa-sandbox.example.invalid
BANK_MCP_BANK_BASE_URL=https://bank-sandbox.example.invalid
BANK_MCP_PAYMENT_BASE_URL=https://payment-sandbox.example.invalid

BANK_MCP_LOG_LEVEL=info
BANK_MCP_RAW_PAYLOAD_LOGGING=false
BANK_MCP_EXECUTION_ENABLED=false
```

Do not commit real values in `.env` files. Development should start with mock connectors and `BANK_MCP_EXECUTION_ENABLED=false`.

---

## 6. Environment Profiles

### Development

```yaml
environment: "development"
connectors:
  mode: "mock"
execution:
  enabled: false
guardian:
  accept_test_signer: true
telemetry:
  destination: "console-and-local-outbox"
```

### Test

```yaml
environment: "test"
connectors:
  mode: "sandbox"
execution:
  enabled: true
  rail: "MOCK_BANK_RAIL"
guardian:
  accept_test_signer: true
  require_single_use_nonce: true
audit:
  append_only: true
```

### Production

```yaml
environment: "production"
connectors:
  mode: "production"
execution:
  enabled: true
guardian:
  accept_test_signer: false
  fail_closed: true
secrets:
  provider: "managed-secret-store"
transport_security:
  mutual_tls: true
  certificate_pinning: "policy-controlled"
audit:
  append_only: true
  sign_records: true
  required_before_financial_execution: true
```

Production startup must fail when mock connectors, test signers, plaintext secrets, raw-payload logging, or disabled audit enforcement are detected.

---

## 7. Configuration Validation Rules

The server must reject configuration when:

- the Account Aggregator connector has `support_transactions: true`;
- a domain agent is allowlisted for an execution tool;
- an execution tool does not require Guardian authorization;
- a beneficiary-change or reversal tool disables human approval without an explicit signed policy exception;
- raw connector results can be returned directly to agents;
- trusted scope can be overridden by tool arguments;
- evidence receipts are unsigned;
- execution retries are enabled without idempotency and status reconciliation;
- production uses mock connectors or test signing keys;
- financial execution is enabled while append-only audit is unavailable;
- account numbers, credentials, or raw payloads are enabled in ordinary logs.

---

## 8. Minimum Prototype Configuration

The first runnable Bank MCP prototype should enable:

```text
Mock Account Aggregator connector
Mock core-banking connector
Mock beneficiary verification
Mock payment rail
Evidence Trust Gateway
Guardian test signer/verifier
Append-only local audit
Idempotency store
Event outbox
```

Required demonstration tools:

```text
bank.aa.create_consent
bank.aa.fetch_information
bank.accounts.get_balance
bank.transactions.list
bank.beneficiaries.verify
bank.transfers.prepare
bank.transfers.execute
bank.transfers.get_status
```

Required security demonstrations:

1. invalid or revoked AA consent is denied;
2. malicious text inside bank/AA JSON is quarantined;
3. a domain agent cannot call `bank.transfers.execute`;
4. execution without Guardian authorization is denied;
5. changing the amount or beneficiary after authorization is denied;
6. replaying an authorization is denied;
7. unknown execution state triggers reconciliation rather than blind retry;
8. beneficiary change and reversal require escalation by default.

