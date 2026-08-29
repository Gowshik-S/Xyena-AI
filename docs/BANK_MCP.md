# XYENA Bank MCP Server

## 1. Status and Purpose

The Bank MCP Server is the controlled tool interface between XYENA agents and banking infrastructure.

The architecture previously separated `Banking Data MCP` and `Payment/Ledger MCP`. This specification consolidates their public tool surface into one Bank MCP server while retaining strict internal separation between:

1. consented, read-only evidence collection;
2. financial-action preparation;
3. Guardian-authorized execution.

The production bank/payment connector remains a specification. A runnable synthetic implementation
under `demos/bank-mcp` now covers evidence, preparation, exact-action Guardian authorization,
idempotent execution, synthetic balance mutation, double-entry posting and settlement status. It
does not connect to a real bank, Account Aggregator or payment rail.

Configuration profiles and validation rules are defined in [BANK_MCP_CONFIG.md](./BANK_MCP_CONFIG.md).

---

## 2. Internal Architecture

```text
XYENA Agent
    ↓ scoped MCP tool request
MCP Gateway + Tool Policy
    ↓
Bank MCP Server
    ├── Read Policy
    ├── Consent and Purpose Validator
    ├── Guardian Authorization Verifier
    ├── Idempotency and Replay Guard
    ├── Account Aggregator Connector ──→ AA / FIPs (read only)
    ├── Core Banking Connector ────────→ accounts / balances / status
    ├── Beneficiary Connector ─────────→ ownership / account verification
    └── Payment Rail Connector ────────→ transfer / reversal / settlement
            ↓
Evidence Trust Gateway or Execution Receipt Store
            ↓
Guardian Call Monitor and Action Graph
```

### Hard boundary

The Account Aggregator connector supplies consented financial information. It cannot execute payments. RBI's Account Aggregator directions state that an AA shall not support customer transactions. Transfer, reversal, beneficiary-change, and settlement tools therefore use separate regulated bank/payment connectors.

---

## 3. Tool Catalogue

### 3.1 Account Aggregator tools

| Tool | Class | Purpose |
|---|---|---|
| `bank.aa.create_consent` | sensitive state change | Create a purpose-bound consent request |
| `bank.aa.get_consent` | sensitive read | Retrieve consent status and permitted data scope |
| `bank.aa.revoke_consent` | sensitive state change | Revoke all or part of an active consent |
| `bank.aa.fetch_information` | sensitive read | Retrieve permitted financial information through AA/FIPs |

`bank.aa.fetch_information` returns an encrypted or raw connector payload only to the Evidence Trust Gateway. Agents receive normalized fields and signed `evidence_receipt_id` values, never unvalidated upstream JSON.

### 3.2 Account and transaction evidence tools

| Tool | Class | Purpose |
|---|---|---|
| `bank.accounts.list` | sensitive read | List tokenized accounts visible under the current consent and scope |
| `bank.accounts.get` | sensitive read | Get normalized account type, currency, status, and ownership evidence |
| `bank.accounts.get_balance` | sensitive read | Obtain current and available balance evidence |
| `bank.transactions.list` | sensitive read | Obtain a bounded, purpose-approved transaction window |
| `bank.beneficiaries.verify` | sensitive read | Verify beneficiary/account ownership and status |
| `bank.limits.get` | sensitive read | Retrieve applicable transaction, rail, and account limits |
| `bank.transfers.get_status` | sensitive read | Reconcile an existing transfer using its idempotency/reference ID |

### 3.3 Financial preparation tools

| Tool | Class | Purpose |
|---|---|---|
| `bank.transfers.prepare` | financial preparation | Validate exact transfer parameters and create a canonical unsigned action |
| `bank.beneficiaries.prepare_change` | high-risk preparation | Prepare an exact beneficiary addition or change for review |
| `bank.reversals.prepare` | high-risk preparation | Determine whether a specific settled transfer can be reversed |

Preparation does not reserve funds, move money, change beneficiaries, or imply approval. It returns a canonical proposed action, domain risk signals, and any pre-execution validation result.

### 3.4 Guardian-authorized execution tools

| Tool | Class | Default policy |
|---|---|---|
| `bank.transfers.execute` | financial execution | Valid Guardian authorization mandatory |
| `bank.beneficiaries.execute_change` | high-risk state change | Guardian authorization plus human approval by default |
| `bank.reversals.execute` | high-risk financial execution | Guardian authorization plus human approval by default |
| `bank.holds.place` | financial control | Guardian authorization mandatory |
| `bank.holds.release` | financial control | Guardian authorization mandatory |

---

## 4. Example Read Call

```json
{
  "tool": "bank.transactions.list",
  "arguments": {
    "account_token": "acct_tok_7",
    "from": "2026-05-01",
    "to": "2026-08-28",
    "purpose": "Verify cash flow for financing case case_1023"
  },
  "trusted_runtime_scope": {
    "tenant_id": "tenant_01",
    "msme_id": "msme_01",
    "user_id": "user_01",
    "case_id": "case_1023",
    "consent_ref": "consent_55"
  }
}
```

The trusted runtime supplies scope and consent. Values asserted by a model are compared with server-side scope and cannot override it.

The tool result follows this path:

```text
Bank/AA raw response
    ↓
Evidence Trust Gateway
    ↓ schema projection, normalization, hashing and security classification
Signed EvidenceReceipt
    ↓
Agent receives minimum normalized data + evidence_receipt_id
Guardian receives provenance and call telemetry
```

---

## 5. Example Transfer Preparation

```json
{
  "tool": "bank.transfers.prepare",
  "arguments": {
    "source_account_token": "acct_tok_7",
    "beneficiary_token": "ben_tok_14",
    "amount": "500000.00",
    "currency": "INR",
    "rail": "APPROVED_BANK_RAIL",
    "purpose": "Finance verified receivable INV-1023",
    "case_id": "case_1023",
    "evidence_receipt_ids": ["evr_invoice_1", "evr_bank_2"],
    "client_idempotency_key": "case_1023-disbursement-1"
  }
}
```

The server returns a canonical action:

```json
{
  "proposed_action_id": "act_9001",
  "action_type": "BANK_TRANSFER",
  "canonical_action_hash": "sha256:...",
  "source_account_token": "acct_tok_7",
  "beneficiary_token": "ben_tok_14",
  "amount": "500000.00",
  "currency": "INR",
  "rail": "APPROVED_BANK_RAIL",
  "preparation_status": "READY_FOR_GUARDIAN",
  "risk_signals": [],
  "expires_at": "2026-08-28T11:00:00Z"
}
```

---

## 6. Example Guardian-Authorized Execution

```json
{
  "tool": "bank.transfers.execute",
  "arguments": {
    "proposed_action_id": "act_9001",
    "guardian_authorization": "signed_compact_token",
    "client_idempotency_key": "case_1023-disbursement-1"
  }
}
```

Before calling a bank or payment rail, the Bank MCP server and Execution Gateway verify:

- Guardian signature and trusted signer;
- action hash equality;
- tenant, MSME, user, agent, and case scope;
- exact source, beneficiary, amount, currency, rail, and purpose;
- authorization issue time, expiry, nonce, and single-use state;
- current mandate and policy version;
- beneficiary status and applicable limits;
- atomic exposure/funds reservation;
- idempotency and prior execution status.

The bank connector returns an execution receipt that is reconciled before exposure and workflow state are finalized.

---

## 7. MCP Result Contracts

### Evidence result

```json
{
  "status": "SUCCESS",
  "normalized_data": {},
  "evidence_receipt_ids": ["evr_bank_2"],
  "security_flags": [],
  "fresh_until": "2026-08-28T11:30:00Z"
}
```

### Execution result

```json
{
  "status": "ACCEPTED | SETTLED | FAILED | UNKNOWN",
  "execution_id": "exec_801",
  "bank_reference": "tokenized_reference",
  "canonical_action_hash": "sha256:...",
  "executed_at": "2026-08-28T10:45:00Z",
  "reconciliation_required": false
}
```

`UNKNOWN` is never treated as failure-safe permission to retry. The system must query `bank.transfers.get_status` using the same idempotency key before another execution attempt.

---

## 8. Error and Decision Codes

| Code | Meaning |
|---|---|
| `SCOPE_MISMATCH` | Runtime scope does not match the requested resource |
| `CONSENT_REQUIRED` | No valid consent covers the requested evidence |
| `CONSENT_SCOPE_EXCEEDED` | Requested data exceeds purpose, type, range, or frequency |
| `INVALID_UPSTREAM_SCHEMA` | Bank/AA response failed schema projection |
| `EVIDENCE_QUARANTINED` | Response contains invalid or instruction-like data |
| `GUARDIAN_AUTH_REQUIRED` | State-changing call lacks authorization |
| `ACTION_HASH_MISMATCH` | Execution parameters differ from the authorized action |
| `AUTHORIZATION_EXPIRED` | Guardian authorization is no longer valid |
| `AUTHORIZATION_REPLAYED` | Single-use authorization has already been consumed |
| `BENEFICIARY_UNVERIFIED` | Beneficiary ownership/status is not sufficiently verified |
| `LIMIT_EXCEEDED` | Amount violates account, rail, mandate, exposure, or policy limit |
| `EXECUTION_STATE_UNKNOWN` | Connector outcome requires reconciliation |

---

## 9. Security Rules

- Agents never receive bank passwords, PINs, private keys, or reusable bank credentials.
- Account numbers are tokenized or masked before entering model context.
- AA consent is evidence-access authorization, not transaction authorization.
- External JSON strings remain untrusted data even when delivered by an authenticated bank or AA connector.
- Tool descriptions and MCP annotations are not authorization controls.
- Domain agents receive read-only Bank MCP capabilities by default.
- Only the Execution Gateway can invoke financial execution tools.
- Beneficiary changes and reversals require elevated policy and human review by default.
- All calls emit tenant-scoped telemetry into the append-only audit and Guardian action graph.
- Financial execution fails closed if Guardian, audit signing, idempotency, or atomic reservation is unavailable.

---

## 10. Related Domain MCP Servers

The same pattern extends beyond banking:

| MCP server | Read/evidence connectors | Protected execution connectors |
|---|---|---|
| Bank MCP | Account Aggregator, banks, beneficiary verification | bank/payment rails, ledger |
| Wallet MCP | chain RPC/indexer, custody data, address intelligence | custody signer, MPC, hardware wallet |
| Portfolio MCP | AA/depository, broker/custodian, market data | broker/order-management system |
| DeFi MCP | chain RPC, protocol registry, contract-risk service | transaction builder and approved signer |

All servers use the shared Evidence Trust Gateway, Guardian authorization contract, call-monitoring stream, and execution-reconciliation protocol.
