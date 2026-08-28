# Ledger and Payment Operations External Demo Application

## 1. Application identity

```text
Application ID   xyena-demo-ledger
Subdomain        ledger.demo.xyena.ai
UI               https://ledger.demo.xyena.ai/
REST API         https://ledger.demo.xyena.ai/api/v1
MCP              https://ledger.demo.xyena.ai/mcp
MCP audience     xyena-demo-ledger-mcp
```

The Ledger/Payment app is the authoritative demo source for double-entry postings, disbursement instructions, settlement status, reversals and reconciliation. It must preserve accounting integrity and exact-action authorization.

## 2. Users and roles

| Role | Capabilities |
|---|---|
| Ledger Viewer | inspect accounts, journal entries and balances |
| Payment Operator | investigate payment and settlement state |
| Ledger Reviewer | approve adjustment/reversal workflows |
| Reconciliation Operator | resolve bank/ledger mismatches |
| Demo Admin | reference/scenario/reset administration |
| MCP Read Client | read balances, entries and status |
| Execution Gateway | submit Guardian-authorized posting/payment commands |

## 3. UI requirements

### Dashboard

- journal and payment counts by state;
- unsettled, failed, unknown and unreconciled amounts;
- account balances and exposure-related control accounts;
- recent reversals/adjustments and integrity alerts;
- live updates.

### Chart of accounts

- account code/name/type/currency/status;
- debit/credit and available/control balances;
- immutable entry drilldown.

### Journal view

- journal header, business date, purpose, case/action references and status;
- balanced debit/credit lines;
- posting/reversal links;
- Guardian authorization and canonical action hash references;
- audit timeline.

### Payment operations

- payment instruction and exact beneficiary/amount tokens;
- Bank MCP execution reference;
- submitted/accepted/settled/failed/unknown timeline;
- reconciliation result and exceptions;
- reviewer-controlled reversal/adjustment workflow.

## 4. State machines

### Journal

```text
DRAFT → VALIDATED → POSTED
                 └→ REJECTED
POSTED → REVERSAL_REQUESTED → REVERSED
```

Posted journals are immutable. Correction is a new linked reversal/adjustment journal.

### Payment

```text
PREPARED → AUTHORIZED → SUBMITTED → ACCEPTED → SETTLED
        └→ EXPIRED/BLOCKED        ├→ FAILED
                                   └→ UNKNOWN → SETTLED/FAILED
```

### Reconciliation

```text
PENDING → MATCHED
        → MISMATCHED → INVESTIGATING → RESOLVED/ESCALATED
```

## 5. Data model

### `ledger_accounts`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | primary key |
| `tenant_id` | string | required |
| `account_code` | string | tenant unique |
| `name` | string | required |
| `account_type` | enum | `ASSET`, `LIABILITY`, `EQUITY`, `INCOME`, `EXPENSE`, `CONTROL` |
| `currency` | string | required |
| `status` | enum | `ACTIVE`, `FROZEN`, `CLOSED` |
| `debit_balance` | decimal(18,2) | derived/maintained transactionally |
| `credit_balance` | decimal(18,2) | derived/maintained transactionally |
| `version` | integer | locked update |

### `journal_entries`

Contains journal ID/number, tenant, business date, description, purpose, case/proposed action/Guardian decision IDs, canonical action hash, idempotency key, status, posted/reversed timestamps, reversal link, total debit/credit and version.

### `journal_lines`

Contains journal, line number, ledger account, debit amount, credit amount, currency, MSME/funder/receivable dimensions and reference tokens. Exactly one of debit/credit is positive; journal totals must balance by currency.

### `payment_instructions`

Contains execution ID, journal, source/beneficiary tokens, amount/currency/rail, purpose, Guardian authorization metadata, canonical hash, idempotency key, status, bank reference, submitted/settled times, failure/unknown codes and version.

### `settlement_receipts`

Contains payment, Bank MCP reference, status, amount/currency, source response hash/signature, received time and raw-object reference if required.

### `reconciliation_records`

Contains ledger/payment/bank references, expected vs observed amounts/statuses, match result, discrepancy code, assigned operator, resolution and version.

### `adjustment_requests`

Contains target journal/payment, proposed adjustment, reason, requester, reviewer, Guardian/action reference when financial, decision and applied journal ID.

Shared audit/outbox/inbox tables are mandatory.

## 6. Posting invariants

- total debit equals total credit for each currency;
- posted journal lines are immutable;
- one idempotency key maps to one canonical journal/action hash;
- the same Guardian authorization/nonce cannot post twice;
- account status and currency are valid at posting time;
- exposure/control-account reservations occur atomically where configured;
- reversal never deletes original entries;
- unknown bank outcome does not create a second payment.

## 7. REST API

```text
GET    /api/v1/dashboard
GET    /api/v1/accounts
GET    /api/v1/accounts/:accountId
GET    /api/v1/journals
GET    /api/v1/journals/:journalId
GET    /api/v1/payments
GET    /api/v1/payments/:paymentId
POST   /api/v1/payments/:paymentId/reconcile
GET    /api/v1/reconciliations
GET    /api/v1/reconciliations/:id
POST   /api/v1/reconciliations/:id/resolve
POST   /api/v1/adjustments
POST   /api/v1/adjustments/:id/approve
POST   /api/v1/adjustments/:id/reject
GET    /api/v1/events/stream
POST   /mcp
```

Journal/payment execution is not exposed as an ordinary browser command.

## 8. MCP tools

| Tool | Class | Behavior |
|---|---|---|
| `ledger.accounts.get_balance` | sensitive read | current account/control balance |
| `ledger.journals.get` | sensitive read | posted journal and lines |
| `ledger.payments.get_status` | sensitive read | current execution/settlement status |
| `ledger.reconciliation.get` | sensitive read | current match/discrepancy |
| `ledger.disbursements.prepare` | financial preparation | canonical balanced journal/payment proposal |
| `ledger.disbursements.execute` | financial execution | exact Guardian authorization required |
| `ledger.reversals.prepare` | high-risk preparation | eligibility and canonical reversal proposal |
| `ledger.reversals.execute` | high-risk execution | Guardian + reviewer approval required |

Execution revalidates action hash, accounts, amount, currency, beneficiary, mandate, authorization expiry/nonce and idempotency before posting.

## 9. Events

Publishes:

```text
ledger.journal_validated
ledger.journal_posted
ledger.journal_reversed
payment.prepared
payment.submitted
payment.accepted
payment.settled
payment.failed
payment.unknown
reconciliation.matched
reconciliation.mismatched
reconciliation.resolved
```

Consumes Bank transfer status/receipt, Funder commitment and Guardian authorization/decision events through authenticated idempotent handlers.

## 10. Live updates

- Posting commits journal, lines, balances, audit and outbox atomically.
- Ledger/payment dashboards refetch on SSE events.
- MCP balance/status calls return the new committed state immediately.
- Bank settlement events update the existing payment; they never create a duplicate instruction.
- Reconciliation changes propagate to Bank/Funder/XYENA through signed events.

## 11. Validation and security

- only Execution Gateway can invoke financial execution tools;
- service validates Guardian signer/audience/action hash/single-use nonce;
- raw bank responses are stored restricted and referenced by hash;
- adjustment/reversal requires reason, reviewer and new authorization where applicable;
- database constraints and transaction isolation enforce balance invariants;
- failure to persist audit/outbox causes the financial transaction to roll back/fail closed.

## 12. Seed scenarios

- normal balanced disbursement and settlement;
- unbalanced journal rejected;
- duplicate idempotency key;
- authorization replay;
- parameter drift after authorization;
- bank accepted then settled;
- unknown bank outcome then reconciliation;
- failed payment with hold release;
- reviewer-approved full/partial reversal;
- ledger/bank amount mismatch.

## 13. Acceptance criteria

- posted journals always balance and remain immutable;
- balances update transactionally and appear live in UI/MCP;
- duplicate execution cannot double-post or double-pay;
- unknown outcomes reconcile before retry;
- reversal creates linked compensating entries;
- every posting traces to case, proposed action, Guardian decision and execution receipt;
- app deploys independently at `ledger.demo.xyena.ai`.

