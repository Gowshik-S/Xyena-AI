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

## 2. Users and roles

| Role | Capabilities |
|---|---|
| GST Viewer | search taxpayers, invoices and return summaries |
| GST Operator | create draft invoice, edit draft, submit for registration |
| GST Reviewer | register, reject or cancel an invoice with a reason |
| Demo Admin | load scenarios, manage reference records, reset demo |
| MCP Read Client | invoke allowlisted taxpayer/invoice/return tools |

Registration and cancellation transitions require distinct reviewer permission; an ordinary agent has read-only MCP access.

## 3. UI requirements

### Dashboard

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

## 4. State machines

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

### Return summary

```text
OPEN → GENERATED → FILED
                  └→ AMENDED
```

Only registered, non-cancelled invoices are included in a generated return version.

## 5. Data model

### `taxpayers`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | primary key |
| `tenant_id` | string | indexed, required |
| `gstin` | string | unique, normalized uppercase, pattern checked |
| `business_id` | string | registry-app reference |
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

## 6. REST API

```text
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

## 7. MCP tools

| Tool | Required inputs | Current-state output |
|---|---|---|
| `gst.taxpayers.get` | GSTIN | taxpayer, status, version, updated time |
| `gst.registrations.verify` | GSTIN, optional as-of | exact status and status-history reference |
| `gst.invoices.get` | invoice ID or seller + number + year | invoice, lines, IRN, status, hashes |
| `gst.invoices.verify` | claimed invoice fields | deterministic field-by-field comparison |
| `gst.invoices.search` | bounded filters | paginated summaries |
| `gst.invoices.check_duplicate` | seller, number, date, amount/hash | exact and fuzzy candidates with reason codes |
| `gst.returns.get_summary` | GSTIN, period, type | return version and totals |

MCP is read-only for agents. The result includes source request ID, schema version, record version, updated/retrieved times and service signature. Raw strings remain external data.

## 8. Published events

```text
taxpayer.created
taxpayer.status_changed
taxpayer.updated
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

## 9. Consumed events

- `business.updated` to flag taxpayer identity drift;
- `purchase_order.created/updated` to maintain reference visibility;
- no consumed event may silently mutate a registered invoice;
- conflicts create a reconciliation/security flag.

## 10. Live update behavior

- Dashboard, taxpayer and invoice pages subscribe to the SSE stream.
- A successful register/cancel command commits before emitting the event.
- Open invoice pages refetch when their invoice version changes.
- MCP reads after commit return the new version immediately.
- XYENA connector caches invalidate on invoice/taxpayer events.
- Evidence already used in a case remains immutable; a new version creates a new receipt and can trigger case reevaluation.

## 11. Validation and security

- reject duplicate GSTIN and seller/year/invoice-number combinations;
- reject client-calculated totals that differ from server totals;
- prevent edits to registered invoice fields;
- detect unknown/oversized/control-character JSON fields;
- preserve seeded prompt injection as labelled field data without executing it;
- source signatures use server-managed keys;
- tenant and tool scope come from trusted service identity;
- no admin mutation tools are available over agent MCP credentials.

## 12. Seed scenarios

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

## 13. Acceptance criteria

1. Users can create, submit, register, search and cancel invoices under role/state rules.
2. Every mutation persists and is visible after reload.
3. Connected browser screens refresh after the outbox event.
4. MCP reads return the new version and current status.
5. Registered invoices cannot be silently edited.
6. Return summaries are reproducibly generated from registered invoice versions.
7. Audit history explains every transition.
8. Duplicate, cancellation, stale-version and injection scenarios produce deterministic outputs.
9. The app deploys independently at `gst.demo.xyena.ai` with health/readiness checks.

