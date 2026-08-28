# GST and e-Invoice External Demo Application

## 1. Application identity

```text
Application ID   xyena-demo-gst
Subdomain        gst.demo.xyena.ai
UI               https://gst.demo.xyena.ai/
REST API         https://gst.demo.xyena.ai/api/v1
MCP              https://gst.demo.xyena.ai/mcp
MCP audience     xyena-demo-gst-mcp
Database         isolated PostgreSQL database/schema
```

This is a functional GST/e-Invoice simulation with persistent data, real workflows and live UI updates. It does not file real tax returns or connect to a government system.

Shared platform rules are inherited from [SHARED_PLATFORM_REQUIREMENTS.md](./SHARED_PLATFORM_REQUIREMENTS.md).

## 2. Authentication, enterprise accounts and roles

### Single-login model

The application has one login page and one authentication mechanism for every demonstration user.
"Single login" means a common authentication experience; it does **not** mean that unrelated
enterprises share one username, session or data scope.

After authentication, the server resolves the user's active enterprise membership and injects the
trusted scope:

```text
user_id
  └── tenant_id
      └── enterprise_id
          ├── gstin
          ├── role set
          ├── MSME classification snapshot
          └── permitted invoice operations
```

Every invoice, return, classification record, audit event and browser subscription is scoped by
`tenant_id` and `enterprise_id`. A user who belongs to more than one test enterprise must explicitly
select an active enterprise after login. Switching the active enterprise rotates the server-side
scope; it must not rely on a client-supplied enterprise ID alone.

### Test credentials

Fixed test credentials are permitted because this application is an isolated demonstration system.
Seed at least one account for each supported enterprise category and a separate reviewer account:

| Test account | Enterprise fixture | Default role | Expected classification |
|---|---|---|---|
| Micro operator | Demo micro enterprise | GST Operator | `MICRO` |
| Small operator | Demo small enterprise | GST Operator | `SMALL` |
| Medium operator | Demo medium enterprise | GST Operator | `MEDIUM` |
| GST reviewer | Demo review authority | GST Reviewer | not applicable |

Credentials are loaded from deployment secrets or a versioned local test fixture, never committed as
production credentials. The login screen must clearly state that no Aadhaar, PAN, GSTN, Udyam or
government identity system is being contacted. Browser credentials are never accepted by the MCP
endpoint; the central Xyena MCP Gateway uses a separate service credential and signed runtime scope.

### Roles

| Role | Capabilities |
|---|---|
| GST Viewer | search taxpayers, invoices and return summaries |
| GST Operator | create draft invoice, edit draft, submit for registration |
| GST Reviewer | register, reject or cancel an invoice with a reason |
| Demo Admin | load scenarios, manage reference records, reset demo |
| MCP Read Client | invoke allowlisted taxpayer/invoice/return tools |

Registration and cancellation transitions require distinct reviewer permission; an ordinary agent has read-only MCP access.

For a simple local walkthrough, one test user may be granted both operator and reviewer roles, but
the permissions and audit actors remain distinct. Production-like and security demonstrations use
separate operator and reviewer accounts.

## 3. Enterprise classification model

MSME classification belongs to the enterprise, not to a user, login session, invoice or individual
transaction. Invoice and return data contribute to annual-turnover evidence, but an invoice amount
must never directly overwrite the enterprise's official classification.

### Classification thresholds

For demonstration calculations effective from 1 April 2025, use the current composite thresholds
published by the Government of India Udyam Registration portal:

| Classification | Investment in plant/machinery/equipment not exceeding | Annual turnover not exceeding |
|---|---:|---:|
| `MICRO` | ₹2.5 crore | ₹10 crore |
| `SMALL` | ₹25 crore | ₹100 crore |
| `MEDIUM` | ₹125 crore | ₹500 crore |

An enterprise fits a category only when both values are within that category's ceilings. If either
value crosses a ceiling, the calculation evaluates the next category. A value above the medium
ceiling produces `OUTSIDE_MSME_LIMITS`; it must not be silently forced into `MEDIUM`.

Source: [Official Udyam MSME classification](https://udyamregistration.gov.in/Important.aspx).

Thresholds are versioned configuration with `effective_from` and `effective_to` dates. They must not
be hard-coded into UI components or inferred by a language model.

### Declared, calculated and effective values

Maintain the following independent values:

| Value | Meaning |
|---|---|
| `declared_classification` | category supplied by the test Udyam/enterprise fixture |
| `calculated_classification` | deterministic result from the selected threshold version and verified inputs |
| `effective_classification` | category currently used by the demo after provenance and mismatch policy |

Classification inputs include:

- financial year and calculation/as-of date;
- annual turnover from registered, non-cancelled invoice/return evidence or a verified seed snapshot;
- investment in plant, machinery or equipment from the enterprise/Udyam test fixture;
- source type, source reference, source hash and verification status;
- threshold-policy version used by the calculation.

Registered invoice events update turnover analytics and may trigger a provisional recalculation. They
do not represent an official Udyam reclassification. When declared and calculated values disagree,
set `CLASSIFICATION_REVIEW_REQUIRED`, retain both values and require an authorized review before
changing `effective_classification`.

The UI and MCP output must label classification provenance as one of:

- `UDYAM_TEST_FIXTURE` — a simulated verified Udyam snapshot;
- `DEMO_DERIVED` — calculated from demonstration evidence;
- `REVIEW_REQUIRED` — inputs conflict or are incomplete.

## 4. UI requirements

### Dashboard

- active enterprise name, GSTIN and MSME classification badge with provenance;
- classification input year, turnover, investment and mismatch/review status;
- active/suspended/cancelled taxpayer counts;
- draft/registered/cancelled invoice counts;
- current-period taxable turnover and tax totals;
- recent registrations, cancellations and schema/security flags;
- live updates from `taxpayer.*`, `invoice.*` and `return.*` events.

### Taxpayer list and detail

- search by GSTIN, legal name, trade name, state and status;
- status, registration history, addresses and business metadata;
- linked invoice and return-summary tabs;
- version, last updated time and audit timeline;
- authorized status update workflow with reason.

### Enterprise account and classification

- one login page for all test users;
- enterprise selector only when the authenticated user has multiple memberships;
- legal/trade name, enterprise identifier, GSTIN and active role set;
- declared, calculated and effective MSME classifications shown separately;
- annual turnover, plant/equipment investment, financial year, source and as-of date;
- threshold version and a visible `DEMO_DERIVED` or `UDYAM_TEST_FIXTURE` provenance badge;
- review workflow for classification mismatches; and
- no UI claim that a transaction-derived value is an official government classification.

### Invoice list and detail

- filters for seller, buyer, invoice number/date, financial year, status and IRN;
- line-item editor while `DRAFT`;
- calculated taxable value, taxes and invoice total;
- purchase-order reference;
- registration and cancellation workflow;
- immutable IRN/acknowledgement section after registration;
- audit, source hash and event timeline;
- clear injection/security-flag display for seeded attack records.

### Return summaries

- period selector;
- GSTR1/GSTR3B-style demo summaries;
- invoice count, turnover, liability and filing status;
- drilldown to included registered invoices.

### Scenario administration

- load a named scenario;
- reset to a versioned seed set;
- simulate latency, source-signature failure, invalid schema or upstream outage;
- not exposed as agent MCP tools.

## 5. State machines

### Taxpayer registration

```text
PENDING → ACTIVE → SUSPENDED → ACTIVE
               └────────────→ CANCELLED
```

`CANCELLED` is terminal for the demo. Historical invoices remain readable.

### Invoice

```text
DRAFT → SUBMITTED → REGISTERED → CANCELLED
          └───────→ REJECTED
```

Rules:

- only `DRAFT` invoices can change seller, buyer, number, date, lines or amounts;
- submission recalculates totals and freezes a canonical source document hash;
- registration requires active seller registration, valid buyer, unique seller/number/year and accepted totals;
- registration generates immutable `irn`, `ack_number` and `ack_date`;
- cancellation requires reviewer role, reason and policy-valid window;
- correction after registration creates a linked credit/debit note or replacement invoice; it does not mutate history.

All normal GST demo invoices are created through the authenticated UI/REST workflow and stored in the
GST application's relational database. Scenario fixtures may be imported only by Demo Admin and are
labelled as seeded records. MCP never creates, edits, registers, rejects or cancels an invoice.

### Return summary

```text
OPEN → GENERATED → FILED
                  └→ AMENDED
```

Only registered, non-cancelled invoices are included in a generated return version.

## 6. Data model

### `users`

Contains `id`, normalized login identifier, password hash or external test-subject reference, status,
last-login time and audit metadata. Passwords are never stored in plaintext.

### `enterprises`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | primary key |
| `tenant_id` | string | indexed, required |
| `business_id` | string | registry-app reference, unique in tenant |
| `legal_name` | string | required |
| `trade_name` | string/null | optional |
| `primary_gstin` | string | normalized, unique in tenant |
| `udyam_reference_token` | string/null | synthetic/tokenized; never a real credential |
| `declared_classification` | enum | `MICRO`, `SMALL`, `MEDIUM`, `OUTSIDE_MSME_LIMITS`, `UNKNOWN` |
| `calculated_classification` | enum | deterministic current calculation |
| `effective_classification` | enum | policy-selected current category |
| `classification_provenance` | enum | `UDYAM_TEST_FIXTURE`, `DEMO_DERIVED`, `REVIEW_REQUIRED` |
| `classification_as_of` | date | required when classified |
| `status` | enum | `ACTIVE`, `SUSPENDED`, `CLOSED` |
| `version` | integer | optimistic concurrency |
| `created_at/by` | timestamp/string | audit metadata |
| `updated_at/by` | timestamp/string | audit metadata |

### `enterprise_memberships`

Maps `user_id` to `tenant_id`, `enterprise_id`, role set, status, valid-from/until and audit metadata.
The server derives the active enterprise scope from this table after login.

### `msme_classification_snapshots`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | primary key |
| `tenant_id` | string | required |
| `enterprise_id` | string | required, indexed |
| `financial_year` | string | required |
| `investment_amount` | decimal(18,2) | non-negative INR amount |
| `annual_turnover` | decimal(18,2) | non-negative INR amount |
| `declared_classification` | enum | supplied fixture value |
| `calculated_classification` | enum | deterministic result |
| `effective_classification` | enum | reviewed/policy result |
| `source_type` | enum | `UDYAM_TEST_FIXTURE`, `GST_RETURN_DERIVED`, `DEMO_SEED` |
| `source_reference` | string | token or aggregate reference |
| `source_hash` | string | canonical input hash |
| `threshold_policy_version` | string | immutable calculation version |
| `verification_status` | enum | `VERIFIED`, `PROVISIONAL`, `REVIEW_REQUIRED`, `REJECTED` |
| `effective_from/to` | date/date null | temporal history |
| `created_at/by` | timestamp/string | audit metadata |

Snapshots are append-only. Recalculation creates a new snapshot and does not rewrite the inputs or
result used by an earlier invoice-financing case.

### `taxpayers`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | primary key |
| `tenant_id` | string | indexed, required |
| `gstin` | string | unique, normalized uppercase, pattern checked |
| `business_id` | string | registry-app reference |
| `enterprise_id` | string | owning enterprise, required |
| `legal_name` | string | length bounded, external/untrusted when read by XYENA |
| `trade_name` | string/null | length bounded |
| `taxpayer_type` | enum | `REGULAR`, `COMPOSITION`, `SEZ`, `OTHER` |
| `registration_status` | enum | state machine |
| `registration_date` | date | required |
| `suspension_date` | date/null | status dependent |
| `cancellation_date` | date/null | status dependent |
| `state_code` | string | two-character demo code |
| `registered_address` | JSON | schema validated |
| `email_token` | string/null | fake/tokenized |
| `phone_token` | string/null | fake/tokenized |
| `risk_flags` | JSON array | source flags, not Guardian verdict |
| `version` | integer | optimistic concurrency |
| `created_at/by` | timestamp/string | audit metadata |
| `updated_at/by` | timestamp/string | audit metadata |

### `taxpayer_status_history`

Stores previous/new status, reason, effective date, actor, aggregate version and correlation ID.

### `invoices`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | primary key |
| `tenant_id` | string | required |
| `enterprise_id` | string | seller enterprise scope, required |
| `invoice_number` | string | unique with seller + financial year |
| `invoice_type` | enum | `B2B`, `CREDIT_NOTE`, `DEBIT_NOTE`, `EXPORT` |
| `invoice_date` | date | required |
| `financial_year` | string | derived/validated |
| `seller_gstin` | string | active taxpayer required at registration |
| `buyer_gstin` | string | valid demo GSTIN when applicable |
| `buyer_id` | string/null | ERP/registry reference |
| `purchase_order_id` | string/null | ERP reference |
| `currency` | string | default `INR` |
| `place_of_supply` | string | validated demo state code |
| `taxable_value` | decimal(18,2) | calculated from lines |
| `cgst_amount` | decimal(18,2) | calculated |
| `sgst_amount` | decimal(18,2) | calculated |
| `igst_amount` | decimal(18,2) | calculated |
| `cess_amount` | decimal(18,2) | calculated/default zero |
| `round_off_amount` | decimal(18,2) | bounded |
| `total_invoice_value` | decimal(18,2) | calculated |
| `status` | enum | invoice state machine |
| `irn` | string/null | immutable, unique after registration |
| `ack_number` | string/null | immutable |
| `ack_date` | timestamp/null | immutable |
| `cancelled_at/by` | timestamp/string null | cancellation metadata |
| `cancellation_reason` | string/null | required when cancelled |
| `source_document_hash` | string | canonical submitted invoice hash |
| `supersedes_invoice_id` | string/null | correction chain |
| `version` | integer | optimistic concurrency |
| `created_at/by` | timestamp/string | audit metadata |
| `updated_at/by` | timestamp/string | audit metadata |

### `invoice_line_items`

Contains `invoice_id`, line number, description, HSN/SAC, quantity, unit, unit price, discount, taxable value, GST rate, CGST/SGST/IGST/cess amounts and total. Money uses decimals. Totals are server calculated.

### `invoice_status_history`

Contains every transition, actor, reason, old/new hash, version and correlation ID.

### `return_summaries`

Contains GSTIN, period, return type, version, status, filed/amended timestamps, turnover, tax totals, invoice count and source hash.

### `return_invoice_links`

Immutable mapping between a return version and included invoice/version.

The shared `audit_events`, `outbox_events` and `inbox_events` tables are mandatory.

## 7. REST API

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/auth/session
GET    /api/v1/enterprises/current
GET    /api/v1/enterprises/current/classification
POST   /api/v1/enterprises/current/classification/recalculate
POST   /api/v1/enterprises/current/classification/review

GET    /api/v1/dashboard
GET    /api/v1/taxpayers
POST   /api/v1/taxpayers
GET    /api/v1/taxpayers/:gstin
PATCH  /api/v1/taxpayers/:gstin
POST   /api/v1/taxpayers/:gstin/status
GET    /api/v1/taxpayers/:gstin/history

GET    /api/v1/invoices
POST   /api/v1/invoices
GET    /api/v1/invoices/:invoiceId
PATCH  /api/v1/invoices/:invoiceId
POST   /api/v1/invoices/:invoiceId/submit
POST   /api/v1/invoices/:invoiceId/register
POST   /api/v1/invoices/:invoiceId/reject
POST   /api/v1/invoices/:invoiceId/cancel
GET    /api/v1/invoices/:invoiceId/history

GET    /api/v1/returns/:gstin/:period
POST   /api/v1/returns/:gstin/:period/generate
POST   /api/v1/returns/:returnId/file
POST   /api/v1/returns/:returnId/amend

GET    /api/v1/events/stream
GET    /api/v1/audit
POST   /mcp
```

Mutation requests require `If-Match`/version and `Idempotency-Key` where externally retried.

Classification recalculation is deterministic. Review and changes to `effective_classification`
require an authorized reviewer and an audit reason. Login establishes the enterprise scope; invoice
mutation routes reject seller identities outside that scope.

## 8. MCP tools

| Tool | Required inputs | Current-state output |
|---|---|---|
| `gst.enterprises.get_classification` | enterprise/GSTIN, financial year or as-of | declared/calculated/effective category, inputs, provenance and policy version |
| `gst.taxpayers.get` | GSTIN | taxpayer, status, version, updated time |
| `gst.registrations.verify` | GSTIN, optional as-of | exact status and status-history reference |
| `gst.invoices.get` | invoice ID or seller + number + year | invoice, lines, IRN, status, hashes |
| `gst.invoices.verify` | claimed invoice fields | deterministic field-by-field comparison |
| `gst.invoices.search` | bounded filters | paginated summaries |
| `gst.invoices.check_duplicate` | seller, number, date, amount/hash | exact and fuzzy candidates with reason codes |
| `gst.returns.get_summary` | GSTIN, period, type | return version and totals |

MCP is read-only for agents. The result includes source request ID, schema version, record version, updated/retrieved times and service signature. Raw strings remain external data.

The central MCP Gateway authenticates with its test service credential and sends the signed Xyena
runtime scope. The GST MCP server verifies tenant, enterprise/user, session, case, call, agent, tool,
purpose and request hash before reading data. Browser cookies, test passwords and client-supplied
tenant IDs are not MCP authorization.

`gst.invoices.get` and `gst.invoices.search` read the latest committed database state. By default,
financing verification uses `REGISTERED` and non-cancelled invoices. Historical/cancelled results may
be returned for explicit verification, but their status makes them ineligible evidence rather than
silently filtering them out.

## 9. Published events

```text
taxpayer.created
taxpayer.status_changed
taxpayer.updated
enterprise.classification_recalculated
enterprise.classification_review_required
enterprise.classification_changed
invoice.created
invoice.submitted
invoice.registered
invoice.rejected
invoice.cancelled
return.generated
return.filed
return.amended
demo.scenario_loaded
```

`invoice.registered` contains only identifiers, status, version, IRN token/hash, totals and correlation metadata. Consumers refetch details through an authorized tool/API.

## 10. Consumed events

- `business.updated` to flag taxpayer identity drift;
- `purchase_order.created/updated` to maintain reference visibility;
- no consumed event may silently mutate a registered invoice;
- conflicts create a reconciliation/security flag.
- registered/cancelled invoice and return changes may queue deterministic turnover recalculation;
- consumed events never directly set the effective MSME category.

## 11. Live update behavior

- Dashboard, taxpayer and invoice pages subscribe to the SSE stream.
- A successful register/cancel command commits before emitting the event.
- Open invoice pages refetch when their invoice version changes.
- MCP reads after commit return the new version immediately.
- XYENA connector caches invalidate on invoice/taxpayer events.
- Enterprise classification views refresh when a new snapshot is committed.
- Evidence already used in a case remains immutable; a new version creates a new receipt and can trigger case reevaluation.

## 12. Validation and security

- reject duplicate GSTIN and seller/year/invoice-number combinations;
- reject client-calculated totals that differ from server totals;
- prevent edits to registered invoice fields;
- detect unknown/oversized/control-character JSON fields;
- preserve seeded prompt injection as labelled field data without executing it;
- source signatures use server-managed keys;
- tenant and tool scope come from trusted service identity;
- no admin mutation tools are available over agent MCP credentials.
- derive tenant and enterprise scope from the authenticated membership, never from an editable form;
- deny cross-enterprise invoice, return and classification lookups even within the same deployment;
- do not classify an enterprise from one invoice or transaction amount;
- version thresholds and record every input used by classification;
- never display `DEMO_DERIVED` as official Udyam verification;
- keep browser test credentials separate from MCP service credentials.

## 13. Seed scenarios

- separate Micro, Small and Medium enterprise test accounts with deterministic classification inputs;
- classification mismatch requiring review;
- enterprise above the medium ceilings producing `OUTSIDE_MSME_LIMITS`;
- active taxpayer and valid registered invoice;
- suspended/cancelled seller;
- fake invoice not found;
- cancelled invoice;
- duplicate invoice identity/hash;
- invoice/PO amount mismatch;
- legal/trade name prompt injection;
- invoice-description prompt injection;
- stale prior invoice version;
- invalid source signature and malformed output schema modes.

## 14. Acceptance criteria

1. One login page authenticates all test users and resolves an isolated enterprise membership.
2. Micro, Small and Medium fixtures use separate enterprise scopes and cannot read one another's data.
3. Users can create, submit, register, search and cancel invoices under role/state rules.
4. Every normal invoice originates in the GST UI/REST database workflow; MCP has no mutation tools.
5. Every mutation persists and is visible after reload.
6. Connected browser screens refresh after the outbox event.
7. MCP reads return the latest committed version and current status.
8. Registered invoices cannot be silently edited.
9. Return summaries are reproducibly generated from registered invoice versions.
10. MSME classification uses versioned investment and annual-turnover inputs, not individual transactions.
11. Declared, calculated and effective classifications and provenance remain independently auditable.
12. A classification mismatch becomes `REVIEW_REQUIRED` and cannot silently change the effective category.
13. Audit history explains every authentication, invoice and classification transition.
14. Duplicate, cancellation, stale-version, cross-enterprise and injection scenarios produce deterministic outputs.
15. Browser test credentials cannot authenticate to MCP.
16. The app deploys independently at `gst.demo.xyena.ai` with health/readiness checks.

