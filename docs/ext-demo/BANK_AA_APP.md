# Bank and Account Aggregator External Demo Application

> Implementation status: the synthetic Bank/AA service, all 19 MCP tools, Guardian-only payment
> operations and multi-page frontend are implemented in [`demos/bank-mcp`](../../demos/bank-mcp/README.md).
> It remains a non-production demonstration and has no regulated or live financial connection.

## 1. Application identity

```text
Application ID   xyena-demo-bank
Subdomain        bank.demo.xyena.ai
UI               https://bank.demo.xyena.ai/
REST API         https://bank.demo.xyena.ai/api/v1
MCP              https://bank.demo.xyena.ai/mcp
MCP audience     xyena-bank-mcp
```

This application combines a functional demo bank, a simulated consent-based Account Aggregator/FIP flow and protected payment operations behind the Bank MCP contract.

The Account Aggregator path is read-only. Transfer, reversal, hold and beneficiary mutations use a separate protected execution path. Tool and configuration contracts are defined in [../BANK_MCP.md](../BANK_MCP.md) and [../BANK_MCP_CONFIG.md](../BANK_MCP_CONFIG.md).

## 2. Users and roles

| Role | Capabilities |
|---|---|
| Bank Viewer | view tokenized customers/accounts/transactions |
| Bank Operator | manage operational account flags and investigate transfers |
| AA Customer | create/review/revoke own synthetic consents |
| Payment Operator | review prepared and submitted transfers |
| Bank Reviewer | approve beneficiary changes/reversals and resolve unknown outcomes |
| Demo Admin | seed/reset/simulate connector modes |
| MCP Read Client | invoke approved evidence tools |
| Execution Gateway | invoke exact Guardian-authorized tools |

## 3. UI requirements

### Banking dashboard

- account balances and transaction volumes;
- transfer state counts and unresolved outcomes;
- new/changed beneficiaries and limits;
- AA consent/request activity;
- recent security/audit events;
- live SSE updates.

### Customer/account screens

- synthetic customer/business identity;
- account tokens, type, currency, status, balance and limits;
- transaction ledger with date/type/reference/purpose/status;
- holds and available-balance calculation;
- immutable account/transaction history.

### Beneficiary screens

- beneficiary token, masked destination, owner match and verification status;
- creation/change review, cooling period and audit history;
- no raw full account data in ordinary model-facing screens/logs.

### AA consent screens

- create purpose/data-type/date-range/frequency-bound consent;
- approve/activate, view usage history and revoke whole/partial consent;
- list FI requests and delivery status;
- clearly label AA as evidence sharing, not transaction execution.

### Transfer operations

- prepared action and Guardian decision reference;
- exact source, beneficiary, amount, currency, rail, purpose and hash;
- execution/reconciliation timeline;
- reversal workflow and unknown-outcome resolution.

## 4. State machines

### Account

```text
PENDING → ACTIVE → FROZEN → ACTIVE
                 └──────→ CLOSED
```

### Beneficiary

```text
DRAFT → PENDING_VERIFICATION → VERIFIED → COOLING_OFF → ACTIVE
                           └→ REJECTED
ACTIVE → CHANGE_PENDING → VERIFIED/COOLING_OFF/ACTIVE
```

### AA consent

```text
DRAFT → PENDING_CUSTOMER → ACTIVE → EXPIRED
                         └──────→ REVOKED
ACTIVE → PARTIALLY_REVOKED → EXPIRED/REVOKED
```

### Financial-information request

```text
CREATED → CONSENT_VALIDATED → FETCHING → DELIVERED
                    └→ DENIED          └→ FAILED
```

### Transfer

```text
PREPARED → GUARDIAN_AUTHORIZED → SUBMITTED → ACCEPTED → SETTLED
        └→ EXPIRED/BLOCKED                 ├→ FAILED
                                            └→ UNKNOWN → SETTLED/FAILED
```

Blind retry from `UNKNOWN` is forbidden. Status reconciliation uses the original idempotency key.

### Reversal

```text
REQUESTED → ELIGIBILITY_CONFIRMED → REVIEW_APPROVED → SUBMITTED → SETTLED/FAILED/UNKNOWN
```

## 5. Data model

### `bank_customers`

Contains tenant, customer/business IDs, verified legal-name token/hash, business-registry references, status and version.

### `bank_accounts`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | internal ID |
| `account_token` | string | externally used stable token, unique |
| `tenant_id` | string | required |
| `customer_id` | string | required |
| `masked_account_number` | string | display only |
| `account_number_hash` | string | lookup/integrity only |
| `account_type` | enum | `CURRENT`, `SAVINGS`, `ESCROW`, `LOAN` |
| `currency` | string | default `INR` |
| `status` | enum | state machine |
| `ledger_balance` | decimal(18,2) | transactional |
| `available_balance` | decimal(18,2) | balance minus active holds |
| `per_transaction_limit` | decimal(18,2) | required |
| `daily_limit` | decimal(18,2) | required |
| `version` | integer | optimistic/locked update |
| `created_at/by` | timestamp/string | audit |
| `updated_at/by` | timestamp/string | audit |

### `bank_transactions`

Contains account, type (`CREDIT`, `DEBIT`, `HOLD`, `RELEASE`, `REVERSAL`), amount, currency, value/book dates, reference, purpose code/text, counterparty token, resulting balance, status, execution/ledger reference, idempotency key and immutable hash.

### `beneficiaries`

Contains beneficiary token, owner business/customer reference, masked account, account hash, bank/routing token, owner-match status, verification source/time, status, cooling-off end, change version and risk flags.

### `account_holds`

Contains account, amount, purpose/action ID, status, expiry, placed/released references and version. Hold placement/release is atomic with available-balance updates.

### `aa_consents`

Contains consent ID, customer, FIU, purpose, permitted information types, account tokens, date range, frequency/usage count, created/approved/expiry/revoked times, status, signed consent-artifact hash and version.

### `aa_consent_usage`

Append-only use record: consent, requester, requested types/range, decision, reason, timestamp and correlation ID.

### `financial_information_requests`

Contains request ID, consent, FIU, requested types/range, status, encrypted/result object reference, source signature/hash, delivered time and error.

### `transfer_actions`

Contains proposed action, canonical hash, source/beneficiary tokens, amount/currency/rail/purpose, Guardian decision/authorization metadata, status, idempotency key, bank reference, submitted/settled times, failure/unknown reason and version.

### `reversal_actions`

Contains original execution, requested amount/reason, eligibility, reviewer decision, Guardian authorization, idempotency and status.

Shared audit/outbox/inbox tables are mandatory. Monetary account/transfer mutations use serializable or appropriately locked transactions.

## 6. REST API

```text
GET    /api/v1/dashboard
GET    /api/v1/customers/:customerId
GET    /api/v1/accounts
GET    /api/v1/accounts/:accountToken
GET    /api/v1/accounts/:accountToken/transactions
GET    /api/v1/accounts/:accountToken/holds

GET    /api/v1/beneficiaries
POST   /api/v1/beneficiaries
POST   /api/v1/beneficiaries/:id/verify
POST   /api/v1/beneficiaries/:id/approve
POST   /api/v1/beneficiaries/:id/activate

GET    /api/v1/aa/consents
POST   /api/v1/aa/consents
POST   /api/v1/aa/consents/:id/approve
POST   /api/v1/aa/consents/:id/revoke
GET    /api/v1/aa/consents/:id/usage
POST   /api/v1/aa/fi-requests
GET    /api/v1/aa/fi-requests/:id

GET    /api/v1/transfers
GET    /api/v1/transfers/:id
POST   /api/v1/transfers/:id/reconcile
POST   /api/v1/reversals/:id/review
GET    /api/v1/events/stream
POST   /mcp
```

Normal financial execution is invoked through Bank MCP/Execution Gateway, not a browser REST command.

## 7. Bank MCP tools

The exact catalogue is in [../BANK_MCP.md](../BANK_MCP.md). The application implements:

```text
bank.aa.create_consent
bank.aa.get_consent
bank.aa.revoke_consent
bank.aa.fetch_information
bank.accounts.list
bank.accounts.get
bank.accounts.get_balance
bank.transactions.list
bank.beneficiaries.verify
bank.limits.get
bank.transfers.prepare
bank.transfers.execute
bank.transfers.get_status
bank.beneficiaries.prepare_change
bank.beneficiaries.execute_change
bank.reversals.prepare
bank.reversals.execute
bank.holds.place
bank.holds.release
```

Read tools return current committed state through Evidence Trust. Execution tools reject calls lacking a valid exact-action Guardian authorization and execution-gateway identity.

## 8. Events

Publishes account/balance/transaction/beneficiary/consent/FI-request/transfer/hold/reversal lifecycle events. Sensitive event payloads use tokens and hashes.

Consumes:

- `business.updated` for owner verification drift;
- `guardian.action_authorized` or equivalent trusted authorization handoff;
- `ledger.transaction_posted/reconciled` for execution reconciliation;
- funder reservation/disbursement references.

## 9. Live updates

- Account/beneficiary/consent/transfer screens refetch after SSE events.
- Transfer execution commits account debit/hold, transaction, audit and outbox atomically.
- MCP balance/transaction reads expose the new committed version immediately.
- AA consent revocation takes effect before another fetch is accepted.
- XYENA evidence caches invalidate on account transaction or consent-relevant changes.

## 10. Validation and security

- AA consent never authorizes a transaction;
- external strings remain untrusted;
- raw account numbers and credentials never enter agent context;
- exact Guardian action hash and single-use nonce are verified;
- parameter drift, replay and stale authorization are denied;
- beneficiary/account limits and available balance are rechecked at execution;
- financial execution fails closed if audit/idempotency/reservation is unavailable;
- unknown results reconcile before retry.

## 11. Seed scenarios

- valid consent and bank evidence;
- expired/revoked/over-scoped consent;
- prompt injection in transaction narration/account name;
- new beneficiary/cooling period;
- owner mismatch and impersonation;
- normal transfer settlement;
- amount/beneficiary changed after authorization;
- replayed authorization;
- insufficient balance/limit exceeded;
- unknown execution then successful reconciliation;
- reversal requiring reviewer approval.

## 12. Acceptance criteria

- balances, transactions, consents and transfers are persistent and live updating;
- AA evidence and payment execution remain technically separated;
- MCP read results match current database state;
- exact-action Guardian authorization is mandatory for execution;
- idempotency prevents duplicate debit;
- audit and ledger reconciliation explain every balance change;
- app deploys independently at `bank.demo.xyena.ai`.

