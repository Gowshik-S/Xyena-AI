# XYENA Demo GST and Delivery Platforms

> **Detailed implementation specifications:** The production-like, live database-backed application specifications are maintained separately under [ext-demo](./ext-demo/README.md). This document remains a combined overview.

## 1. Purpose

XYENA needs small external applications that behave like authoritative GST/e-Invoice and delivery systems during the demonstration. Their purpose is to expose realistic data through MCP so the Invoice, Business, Delivery, Fraud/Risk, Guardian, and Evidence Trust components can be demonstrated end to end.

These applications are intentionally basic. They are not intended to recreate the government GST portal, a complete ERP, or a commercial logistics platform.

The demo must prove that:

- an agent can retrieve evidence through an allowlisted MCP tool;
- each result has a known source and correlation trail;
- raw responses pass through XYENA's Evidence Trust Gateway;
- prompt-injected or malformed fields remain untrusted data;
- cross-system inconsistencies are visible to agents and Guardian;
- each external system can be deployed and operated independently on its own subdomain.

---

## 2. Scope

### Demo GST/e-Invoice platform

Provides mock:

- taxpayer and GST registration records;
- e-Invoice/IRN records;
- invoice line items and tax totals;
- invoice status and cancellation data;
- GST filing/turnover summaries;
- invoice lookup, verification, and duplicate-search tools.

### Demo Delivery platform

Provides mock:

- purchase-order and invoice-linked deliveries;
- delivery items and quantities;
- shipment status timeline;
- proof-of-delivery metadata;
- buyer acceptance/rejection;
- fulfilment-value calculation and verification tools.

### Optional companion demo platforms

The same pattern can later support:

- Bank MCP and mock Account Aggregator/bank app;
- business registry/KYB app;
- buyer/ERP app;
- funder marketplace app;
- ledger/payment app.

The Bank MCP contract and configuration are specified separately in [BANK_MCP.md](./BANK_MCP.md) and [BANK_MCP_CONFIG.md](./BANK_MCP_CONFIG.md).

---

## 3. Design Principles

1. **MCP first** — the minimum useful application is a database, a small admin/read UI, and an MCP server.
2. **Separate authority domains** — GST and delivery data are stored and served independently so contradictions can be tested.
3. **No direct agent database access** — agents use MCP tools through the central MCP Gateway.
4. **Raw data is untrusted** — even an authenticated demo application can return malicious strings or malformed data.
5. **Server-generated provenance** — request identity, source identity, timestamps, and response hashes are created by trusted runtime code, not accepted from user JSON.
6. **Deterministic outputs** — MCP tools return versioned schemas rather than free-form text.
7. **Seedable scenarios** — the same case can be reset and replayed during a demonstration.
8. **Independent deployment** — every application has its own subdomain, runtime, database/schema, credentials, logs, and health status.
9. **Demo-only data** — no real GSTINs, bank accounts, personal data, or production credentials.
10. **Clear non-production labelling** — every UI and response identifies the system as simulated.

---

## 4. Proposed Subdomains

Use one configurable base domain. The examples below assume `demo.xyena.ai`.

| Application | Subdomain | UI | API | MCP endpoint |
|---|---|---|---|---|
| XYENA main application | `app.demo.xyena.ai` | `/` | `/api/*` | central client only |
| Demo GST/e-Invoice | `gst.demo.xyena.ai` | `/` | `/api/v1/*` | `/mcp` |
| Demo Delivery | `delivery.demo.xyena.ai` | `/` | `/api/v1/*` | `/mcp` |
| Demo Bank/AA | `bank.demo.xyena.ai` | `/` | `/api/v1/*` | `/mcp` |
| Demo Funder | `funder.demo.xyena.ai` | `/` | `/api/v1/*` | `/mcp` |
| Demo Ledger | `ledger.demo.xyena.ai` | `/` | `/api/v1/*` | `/mcp` |

For local development:

```text
app.xyena.localhost
gst.xyena.localhost
delivery.xyena.localhost
bank.xyena.localhost
funder.xyena.localhost
ledger.xyena.localhost
```

Each application can serve its UI, REST API, and MCP endpoint from the same subdomain. The central XYENA MCP Gateway is the only normal caller of the external `/mcp` endpoints.

### Network flow

```text
Agent Worker
    ↓
XYENA Tool Policy
    ↓
Central MCP Gateway
    ├── https://gst.demo.xyena.ai/mcp
    ├── https://delivery.demo.xyena.ai/mcp
    ├── https://bank.demo.xyena.ai/mcp
    ├── https://funder.demo.xyena.ai/mcp
    └── https://ledger.demo.xyena.ai/mcp
            ↓
Evidence Trust Gateway or Execution Gateway
            ↓
Agent result + signed evidence receipt
```

---

## 5. Shared Technical Shape

Each demo application should contain only:

```text
Basic read/admin UI
REST API for its own UI
MCP server and tool handlers
Application service layer
Relational database
Seed/reset command or protected demo endpoint
Service authentication
Health/readiness endpoints
Structured audit log
```

Suggested project layout:

```text
demo-apps/
├── gst-platform/
│   ├── src/
│   │   ├── api/
│   │   ├── mcp/
│   │   ├── domain/
│   │   ├── db/
│   │   └── ui/
│   ├── migrations/
│   ├── seeds/
│   └── tests/
├── delivery-platform/
│   ├── src/
│   │   ├── api/
│   │   ├── mcp/
│   │   ├── domain/
│   │   ├── db/
│   │   └── ui/
│   ├── migrations/
│   ├── seeds/
│   └── tests/
└── shared/
    ├── auth/
    ├── mcp-contracts/
    ├── demo-identifiers/
    └── observability/
```

The actual repository location can change when implementation begins. The logical separation should remain.

---

## 6. Shared Identifiers

Cross-application reconciliation depends on stable identifiers.

| Identifier | Example | Owner |
|---|---|---|
| `demo_tenant_id` | `tenant_demo_01` | XYENA identity service |
| `msme_id` | `msme_demo_01` | XYENA/business registry |
| `case_id` | `case_demo_1023` | XYENA case service |
| `seller_gstin` | `29ABCDE1234F1Z5` | Demo GST platform |
| `buyer_gstin` | `27BUYER1234B1Z7` | Demo GST platform |
| `invoice_id` | `inv_1023` | Demo GST platform |
| `invoice_number` | `INV-1023` | Seller invoice domain |
| `irn` | deterministic demo hash | Demo GST platform |
| `purchase_order_id` | `po_7001` | Demo buyer/ERP data |
| `delivery_id` | `del_9001` | Demo Delivery platform |
| `payment_reference` | `pay_5001` | Demo Bank platform |
| `correlation_id` | `corr_demo_8001` | XYENA runtime |

Applications may store references owned by another application, but they must not silently rewrite the authoritative record.

---

## 7. Demo GST Platform

### 7.1 Minimum UI

The GST UI needs only:

1. dashboard with taxpayer/invoice counts;
2. taxpayer search and detail page;
3. invoice search and detail page;
4. IRN/status/cancellation view;
5. return-summary view;
6. protected demo scenario/reset page.

Every page displays `DEMO DATA — NOT A GOVERNMENT SYSTEM`.

### 7.2 GST data model

#### `taxpayers`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | Internal immutable ID |
| `gstin` | string | Unique, pattern-validated demo GSTIN |
| `legal_name` | string | Untrusted external data when returned to XYENA |
| `trade_name` | string/null | Untrusted external data |
| `pan_token` | string/null | Fake/tokenized value only |
| `taxpayer_type` | enum | `REGULAR`, `COMPOSITION`, `SEZ`, `OTHER` |
| `registration_status` | enum | `ACTIVE`, `SUSPENDED`, `CANCELLED` |
| `registration_date` | date | Registration date |
| `cancellation_date` | date/null | Present when cancelled |
| `registered_state_code` | string | Demo state code |
| `registered_address` | JSON | Structured fake address |
| `risk_flags` | JSON array | Demo-only source risk flags |
| `created_at` | timestamp | Server time |
| `updated_at` | timestamp | Server time |
| `version` | integer | Optimistic/versioned record |

#### `invoices`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | `invoice_id` |
| `invoice_number` | string | Unique per seller and financial year |
| `invoice_type` | enum | `B2B`, `CREDIT_NOTE`, `DEBIT_NOTE`, `EXPORT` |
| `invoice_date` | date | Issue date |
| `financial_year` | string | Example `2026-27` |
| `seller_gstin` | string | References taxpayer |
| `buyer_gstin` | string | References taxpayer/buyer record |
| `purchase_order_id` | string/null | Cross-app reconciliation key |
| `currency` | string | Default `INR` |
| `place_of_supply` | string | Demo state code |
| `taxable_value` | decimal(18,2) | Sum of taxable lines |
| `cgst_amount` | decimal(18,2) | Central tax |
| `sgst_amount` | decimal(18,2) | State tax |
| `igst_amount` | decimal(18,2) | Integrated tax |
| `cess_amount` | decimal(18,2) | Optional |
| `round_off_amount` | decimal(18,2) | Optional |
| `total_invoice_value` | decimal(18,2) | Deterministically calculated |
| `status` | enum | `DRAFT`, `REGISTERED`, `CANCELLED` |
| `irn` | string/null | Present after registration |
| `ack_number` | string/null | Demo acknowledgement |
| `ack_date` | timestamp/null | Registration timestamp |
| `cancelled_at` | timestamp/null | Cancellation timestamp |
| `cancellation_reason` | string/null | Untrusted external string |
| `source_document_hash` | string | Hash of seeded source artifact |
| `created_at` | timestamp | Server time |
| `updated_at` | timestamp | Server time |

#### `invoice_line_items`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | Immutable line ID |
| `invoice_id` | UUID/string | Parent invoice |
| `line_number` | integer | Unique within invoice |
| `description` | string | Untrusted string |
| `hsn_sac` | string | Demo code |
| `quantity` | decimal(18,3) | Positive |
| `unit` | string | Example `NOS`, `KG`, `SERVICE` |
| `unit_price` | decimal(18,2) | Non-negative |
| `discount_amount` | decimal(18,2) | Default zero |
| `taxable_value` | decimal(18,2) | Deterministically calculated |
| `gst_rate` | decimal(5,2) | Demo rate |
| `cgst_amount` | decimal(18,2) | Calculated |
| `sgst_amount` | decimal(18,2) | Calculated |
| `igst_amount` | decimal(18,2) | Calculated |
| `total_line_value` | decimal(18,2) | Calculated |

#### `gst_return_summaries`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | Immutable ID |
| `gstin` | string | Taxpayer |
| `return_period` | string | Example `082026` |
| `return_type` | enum | `GSTR1`, `GSTR3B` |
| `filing_status` | enum | `FILED`, `PENDING`, `LATE`, `NOT_FILED` |
| `filed_at` | timestamp/null | Filing time |
| `taxable_turnover` | decimal(18,2) | Period summary |
| `tax_liability` | decimal(18,2) | Period summary |
| `invoice_count` | integer | Period invoice count |
| `source_hash` | string | Immutable response/source hash |

#### `gst_audit_events`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | Event ID |
| `request_id` | string | MCP/API request ID |
| `caller_id` | string | Authenticated workload identity |
| `tool_name` | string/null | MCP tool |
| `purpose` | string | Caller-declared, policy-checked purpose |
| `argument_hash` | string | Canonical input hash |
| `result_hash` | string/null | Canonical output hash |
| `status` | enum | `SUCCESS`, `DENIED`, `FAILED` |
| `created_at` | timestamp | Server time |

### 7.3 GST MCP tools

| Tool | Inputs | Output | Policy |
|---|---|---|---|
| `gst.taxpayers.get` | `gstin` | normalized taxpayer record | sensitive read |
| `gst.registrations.verify` | `gstin`, `as_of` | registration status and match result | read |
| `gst.invoices.get` | `invoice_id` or seller + number | invoice and lines | sensitive read |
| `gst.invoices.verify` | invoice claims | field comparison and source record | read |
| `gst.invoices.search` | bounded filters | matching invoice summaries | sensitive read |
| `gst.invoices.check_duplicate` | seller, number, date, value, hash | duplicate candidates | read |
| `gst.returns.get_summary` | GSTIN and period | filing/turnover summary | sensitive read |
| `gst.demo.get_scenario` | scenario ID | scenario metadata | demo admin only |

Agents should not receive GST demo admin mutation tools. Scenario creation/reset happens through a protected admin UI or deployment seed command.

### 7.4 Example GST MCP result

```json
{
  "schema_version": "gst.invoice.v1",
  "source_system": "xyena-demo-gst",
  "request_id": "gst_req_1001",
  "retrieved_at": "2026-08-28T10:30:00Z",
  "data": {
    "invoice_id": "inv_1023",
    "invoice_number": "INV-1023",
    "seller_gstin": "29ABCDE1234F1Z5",
    "buyer_gstin": "27BUYER1234B1Z7",
    "status": "REGISTERED",
    "irn": "demo_irn_hash",
    "total_invoice_value": "1000000.00",
    "currency": "INR"
  },
  "source_signature": "demo-service-signature",
  "security_labels": ["EXTERNAL_DATA", "DEMO_SOURCE"]
}
```

`source_system` and `source_signature` are produced by the demo service. XYENA's Evidence Trust Gateway independently validates the configured connector identity, projects the schema, hashes the raw and normalized results, and issues the authoritative XYENA `EvidenceReceipt`.

---

## 8. Demo Delivery Platform

### 8.1 Minimum UI

The Delivery UI needs only:

1. delivery dashboard;
2. search by delivery, invoice, or purchase-order ID;
3. delivery detail and item list;
4. status timeline;
5. proof-of-delivery and buyer-acceptance view;
6. protected scenario/reset page.

Every page displays `DEMO DATA — NOT A REAL LOGISTICS SYSTEM`.

### 8.2 Delivery data model

#### `deliveries`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | `delivery_id` |
| `delivery_number` | string | Human-readable reference |
| `purchase_order_id` | string | Shared reconciliation key |
| `invoice_id` | string | GST platform invoice reference |
| `invoice_number` | string | Human-readable cross-check |
| `seller_gstin` | string | Supplier identifier |
| `buyer_gstin` | string | Buyer identifier |
| `carrier_id` | string/null | Demo carrier |
| `tracking_number` | string/null | server-generated synthetic ID matching `^XY[A-HJ-NP-Z2-9]{8}$` |
| `dispatch_date` | timestamp/null | Dispatch time |
| `expected_delivery_date` | date/null | Expected date |
| `delivered_at` | timestamp/null | Actual completion time |
| `status` | enum | `CREATED`, `DISPATCHED`, `IN_TRANSIT`, `PARTIAL`, `DELIVERED`, `REJECTED`, `CANCELLED` |
| `ship_from` | JSON | Structured fake address |
| `ship_to` | JSON | Structured fake address |
| `currency` | string | Default `INR` |
| `declared_value` | decimal(18,2) | Claimed shipment value |
| `verified_delivered_value` | decimal(18,2) | Calculated from accepted items |
| `created_at` | timestamp | Server time |
| `updated_at` | timestamp | Server time |
| `version` | integer | Record version |

#### `delivery_items`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | Immutable line ID |
| `delivery_id` | UUID/string | Parent delivery |
| `invoice_line_id` | string/null | GST invoice-line reference |
| `sku` | string | Demo SKU/service reference |
| `description` | string | Untrusted external string |
| `unit` | string | Same normalized unit contract as invoice |
| `ordered_quantity` | decimal(18,3) | Purchase-order quantity |
| `dispatched_quantity` | decimal(18,3) | Dispatched quantity |
| `delivered_quantity` | decimal(18,3) | Physically delivered quantity |
| `accepted_quantity` | decimal(18,3) | Buyer-accepted quantity |
| `rejected_quantity` | decimal(18,3) | Buyer-rejected quantity |
| `unit_value` | decimal(18,2) | Value used for fulfilment calculation |
| `rejection_reason` | string/null | Untrusted external string |

#### `delivery_events`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | Event ID |
| `delivery_id` | UUID/string | Parent delivery |
| `event_type` | enum | `CREATED`, `PICKED_UP`, `IN_TRANSIT`, `OUT_FOR_DELIVERY`, `DELIVERED`, `PARTIAL`, `REJECTED`, `CANCELLED` |
| `event_time` | timestamp | Event time |
| `location` | JSON/null | Coarse fake location only |
| `actor_type` | enum | `SELLER`, `CARRIER`, `BUYER`, `SYSTEM` |
| `actor_id` | string | Demo actor |
| `notes` | string/null | Untrusted external string |
| `source_hash` | string | Event source hash |

#### `proofs_of_delivery`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | POD ID |
| `delivery_id` | UUID/string | Parent delivery |
| `proof_type` | enum | `OTP`, `SIGNATURE`, `PHOTO`, `BUYER_CONFIRMATION`, `DOCUMENT` |
| `object_key` | string/null | Restricted evidence-object reference |
| `object_hash` | string | Immutable content hash |
| `recipient_name` | string/null | Fake/tokenized demo name |
| `recipient_role` | string/null | Example `WAREHOUSE_MANAGER` |
| `verified` | boolean | Deterministic/workflow status |
| `verified_at` | timestamp/null | Verification time |
| `verification_method` | string/null | Demo method |
| `security_flags` | JSON array | Mismatch or tamper flags |

#### `buyer_acceptances`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID/string | Acceptance ID |
| `delivery_id` | UUID/string | Parent delivery |
| `buyer_gstin` | string | Buyer identity |
| `status` | enum | `PENDING`, `ACCEPTED`, `PARTIALLY_ACCEPTED`, `REJECTED` |
| `accepted_value` | decimal(18,2) | Supported accepted value |
| `accepted_at` | timestamp/null | Decision time |
| `reason` | string/null | Untrusted external string |
| `actor_reference` | string | Tokenized demo actor |
| `source_hash` | string | Immutable source hash |

#### `delivery_audit_events`

Uses the same event fields as `gst_audit_events`, with delivery-specific tool and resource references.

### 8.3 Delivery MCP tools

| Tool | Inputs | Output | Policy |
|---|---|---|---|
| `delivery.deliveries.get` | `delivery_id` | delivery and items | sensitive read |
| `delivery.deliveries.find_by_invoice` | `invoice_id` or seller + number | matching deliveries | sensitive read |
| `delivery.events.list` | `delivery_id` | ordered timeline | read |
| `delivery.proofs.get` | `delivery_id` | POD metadata and hashes | sensitive read |
| `delivery.acceptance.get` | `delivery_id` | buyer acceptance | sensitive read |
| `delivery.fulfilment.verify` | invoice line claims | quantity/value comparison | read |
| `delivery.demo.get_scenario` | scenario ID | scenario metadata | demo admin only |

The Delivery Agent receives structured results and evidence references. It does not need direct access to uploaded POD binaries unless the workflow explicitly requests a separately sandboxed artifact.

### 8.4 Fulfilment calculation

For the basic demo:

```text
Accepted Line Value
= MIN(accepted_quantity, invoiced_quantity) × supported_unit_value

Verified Delivered Value
= SUM(Accepted Line Value)

Finance-Supported Receivable Base
= MIN(
    GST Registered Invoice Value,
    Verified Delivered Value
  )
```

Payment reconciliation is applied later by the Payment Agent.

---

## 9. Cross-Application Consistency Rules

XYENA compares normalized claims rather than allowing one demo application to overwrite another.

| Rule | GST source | Delivery source | Expected control |
|---|---|---|---|
| Seller identity | `seller_gstin` | `seller_gstin` | exact match |
| Buyer identity | `buyer_gstin` | `buyer_gstin` | exact match |
| Invoice link | `invoice_id`, number | `invoice_id`, number | exact match |
| Purchase order | `purchase_order_id` | `purchase_order_id` | exact match when required |
| Quantity | invoice lines | accepted delivery items | delivered cannot support more than invoiced |
| Value | invoice line/total | accepted delivery value | finance base uses supported minimum |
| Dates | invoice date | dispatch/delivery dates | policy-valid ordering and range |
| Status | registered/cancelled | delivered/accepted | cancelled invoice cannot be financed |

Contradictions produce explicit findings. They must not be silently repaired by either demo application or the orchestrator.

---

## 10. MCP Request and Response Envelope

### Request

```json
{
  "tool_call_id": "tc_demo_101",
  "tool": "delivery.fulfilment.verify",
  "trusted_scope": {
    "tenant_id": "tenant_demo_01",
    "msme_id": "msme_demo_01",
    "user_id": "user_demo_01",
    "case_id": "case_demo_1023"
  },
  "purpose": "Verify fulfilment for invoice INV-1023",
  "arguments": {
    "invoice_id": "inv_1023"
  },
  "correlation_id": "corr_demo_8001"
}
```

`trusted_scope` is injected or signed by the central gateway. The demo application rejects mismatches between trusted runtime scope and model-supplied arguments.

### Response

```json
{
  "schema_version": "delivery.fulfilment.v1",
  "source_system": "xyena-demo-delivery",
  "request_id": "delivery_req_201",
  "retrieved_at": "2026-08-28T10:35:00Z",
  "data": {
    "delivery_id": "del_9001",
    "invoice_id": "inv_1023",
    "status": "DELIVERED",
    "accepted_value": "1000000.00",
    "currency": "INR"
  },
  "source_signature": "demo-service-signature",
  "security_labels": ["EXTERNAL_DATA", "DEMO_SOURCE"]
}
```

---

## 11. Authentication and Authorization

### Human demo UI

- one seeded demo administrator per application;
- optional shared demo identity provider;
- secure cookie, short session, CSRF protection;
- admin scenario/reset controls unavailable to ordinary read users.

### MCP service authentication

Use short-lived service tokens with:

- issuer;
- audience bound to the exact demo application;
- caller/workload identity;
- permitted MCP tool scopes;
- tenant/demo scope where applicable;
- issue and expiry timestamps;
- unique token ID.

Example audiences:

```text
xyena-demo-gst-mcp
xyena-demo-delivery-mcp
xyena-demo-bank-mcp
```

Production-like deployment should use TLS and workload identity or mutually authenticated service connections. Static API keys may be used only for an isolated local prototype and must never be included in model prompts.

---

## 12. Evidence Trust Integration

The external demo application is not the final trust authority.

```text
Demo MCP response
    ↓
Connector identity and transport validation
    ↓
Strict response schema projection
    ↓
Type, enum, pattern, range and length validation
    ↓
Instruction-like string and hidden-content classification
    ↓
Raw-response hash + normalized-claims hash
    ↓
XYENA-signed EvidenceReceipt
```

The receipt binds:

- tool call and connector identity;
- tenant, MSME and case scope;
- raw and normalized hashes;
- schema and connector version;
- retrieval time and freshness;
- security flags;
- gateway signature.

Neither the demo application nor an agent can manufacture a trusted XYENA receipt by returning an `evidence_receipt_id` field.

---

## 13. Seed Scenarios

| Scenario | GST data | Delivery data | Expected result |
|---|---|---|---|
| `S01_NORMAL` | active seller, registered ₹10L invoice | full accepted ₹10L delivery | verification succeeds |
| `S02_FAKE_INVOICE` | invoice not found | delivery claims invoice exists | `BLOCK` or `VERIFY` |
| `S03_CANCELLED_INVOICE` | invoice cancelled | delivery complete | invoice ineligible |
| `S04_PARTIAL_DELIVERY` | registered ₹10L invoice | only ₹4L accepted | constrain receivable base to ₹4L before payments/cap |
| `S05_VALUE_MISMATCH` | ₹10L invoice | delivery claims ₹13L | contradiction and risk signal |
| `S06_BUYER_MISMATCH` | Buyer A | delivery to Buyer B | block/verify counterparty |
| `S07_DUPLICATE_INVOICE` | two matching invoice identities/hashes | one delivery | fraud/duplicate finding |
| `S08_DOCUMENT_INJECTION` | invoice description contains instructions | otherwise normal | text quarantined; instructions inert |
| `S09_JSON_FIELD_INJECTION` | legal/trade name contains role-changing instructions | normal | schema-safe data plus security flag |
| `S10_FAKE_POD` | valid invoice | POD hash/status mismatch | verify/escalate |
| `S11_EVENT_SEQUENCE` | valid invoice | delivered event occurs before dispatch | action/evidence anomaly |
| `S12_STALE_EVIDENCE` | old valid record | old accepted delivery | freshness policy requires re-fetch |

Every scenario should be loadable by ID and produce stable identifiers so screenshots and demonstrations are repeatable.

---

## 14. Demo Admin Operations

Admin-only operations may include:

```text
Load scenario
Reset database to seeds
Toggle simulated connector latency
Toggle schema failure
Toggle upstream unavailable
Toggle malicious/instruction-like field
Inspect recent MCP calls
Inspect source response hash
```

These controls must be separated from normal MCP tools. Agents must not be able to load or alter scenarios.

---

## 15. REST Endpoints for the Basic UI

### GST

```text
GET  /api/v1/taxpayers/:gstin
GET  /api/v1/invoices/:invoiceId
GET  /api/v1/invoices?gstin=&number=&status=
GET  /api/v1/returns/:gstin/:period
GET  /api/v1/admin/scenarios
POST /api/v1/admin/scenarios/:scenarioId/load
POST /api/v1/admin/reset
GET  /health/live
GET  /health/ready
POST /mcp
```

### Delivery

```text
GET  /api/v1/deliveries/:deliveryId
GET  /api/v1/deliveries?invoiceId=&purchaseOrderId=&status=
GET  /api/v1/deliveries/:deliveryId/events
GET  /api/v1/deliveries/:deliveryId/proof
GET  /api/v1/admin/scenarios
POST /api/v1/admin/scenarios/:scenarioId/load
POST /api/v1/admin/reset
GET  /health/live
GET  /health/ready
POST /mcp
```

The MCP endpoint should use the selected supported MCP transport and should not expose arbitrary REST route execution.

---

## 16. Deployment

Each application is packaged independently:

```text
One application container
One migration/seed job
One application database or isolated database schema
One subdomain and TLS certificate
One workload identity/audience
One log stream and health check
```

### Suggested routing

```text
Public/controlled demo ingress
    ├── gst.demo.xyena.ai       → gst-platform service
    ├── delivery.demo.xyena.ai  → delivery-platform service
    ├── bank.demo.xyena.ai      → bank-platform service
    ├── funder.demo.xyena.ai    → funder-platform service
    └── ledger.demo.xyena.ai    → ledger-platform service
```

### Required environment variables

```dotenv
APP_ENV=demo
APP_ID=xyena-demo-gst
PUBLIC_BASE_URL=https://gst.demo.xyena.ai
DATABASE_URL=secret-reference
MCP_AUDIENCE=xyena-demo-gst-mcp
WORKLOAD_ISSUER=https://identity.demo.xyena.ai
SOURCE_SIGNING_KEY=secret-reference
ALLOWED_UI_ORIGINS=https://app.demo.xyena.ai
ALLOW_DEMO_ADMIN=true
DEMO_SEED_SET=default
LOG_LEVEL=info
RAW_PAYLOAD_LOGGING=false
```

Delivery uses the same variables with delivery-specific IDs and URLs.

### Cross-subdomain controls

- HTTPS only outside local development;
- exact CORS allowlist, never wildcard with credentials;
- cookies scoped to the smallest required host;
- separate MCP audiences per application;
- service-to-service calls do not depend on browser cookies;
- rate limiting per caller, tool, tenant and correlation ID;
- security headers on every UI;
- DNS and certificate ownership documented for every subdomain.

---

## 17. Observability

Every MCP call records:

- request/tool call ID;
- authenticated caller/workload;
- tool name and schema version;
- purpose and trusted scope;
- canonical argument hash;
- result hash and status;
- latency and connector errors;
- correlation ID;
- security flags;
- timestamp.

Do not place full invoices, addresses, credentials, raw POD images, or unrestricted upstream JSON in ordinary logs.

Recommended demo dashboards:

- calls per application/tool;
- successful, denied and failed calls;
- response latency;
- injection/quarantine signals;
- evidence receipts issued by XYENA;
- Guardian verdicts produced from the scenario.

---

## 18. Failure Behaviour

| Failure | Required behaviour |
|---|---|
| Demo application unavailable | bounded retry for reads; no invented result |
| Invalid service token | deny before tool execution |
| Scope/audience mismatch | deny and audit |
| Unknown MCP tool | deny |
| Invalid input schema | reject with reason code |
| Invalid output schema | Evidence Trust Gateway rejects/quarantines result |
| Source signature invalid | evidence cannot satisfy trusted completeness policy |
| Conflicting GST and delivery facts | preserve contradiction and return non-`ALLOW` Guardian decision as policy requires |
| Raw field contains prompt injection | keep as inert data, flag/quarantine, continue only if safe fields remain sufficient |
| Timeout after financial execution | applies to Bank/Ledger demos: reconcile by idempotency key before retry |

---

## 19. Testing

### Contract tests

- MCP tool input/output schemas;
- enum, decimal and date formats;
- source signature generation/validation;
- stable canonical result hashing;
- error-code contracts.

### Security tests

- unauthenticated and wrong-audience requests;
- model-supplied scope override;
- cross-tenant/case lookup attempt;
- prompt injection in every free-form field;
- oversized/unknown JSON fields;
- malformed encoding and control characters;
- admin tool invocation by an agent;
- response replay and stale evidence.

### Scenario tests

- normal invoice/full delivery;
- fake or cancelled invoice;
- partial delivery and supported-value constraint;
- buyer/seller mismatch;
- duplicate invoice;
- forged POD;
- inconsistent event ordering;
- upstream outage and invalid schema.

---

## 20. Acceptance Criteria

The first demo is complete when:

1. GST and Delivery applications run independently on different subdomains.
2. Each has a basic read/admin UI and `/mcp` endpoint.
3. The central MCP Gateway authenticates and invokes both applications.
4. Agents cannot access either database directly.
5. GST verification returns deterministic invoice/taxpayer data.
6. Delivery verification returns deterministic fulfilment and POD metadata.
7. Raw responses are normalized and produce signed XYENA evidence receipts.
8. A normal case produces consistent Business/Invoice/Delivery findings.
9. A partial-delivery case constrains the supported receivable value.
10. Document and JSON prompt-injection scenarios remain inert and are visible as security flags.
11. Contradictions are preserved for Fraud/Risk and Guardian.
12. Scenario reset makes the demonstration repeatable.
13. Logs contain hashes and correlation metadata, not credentials or unrestricted evidence.

---

## 21. Non-Goals

The basic demo does not need:

- government GST or IRP integration;
- real GST filing or statutory compliance;
- real GSTIN, PAN, buyer, or personal information;
- production-grade tax calculation across every rule;
- carrier GPS tracking;
- OCR or biometric proof verification inside the delivery app;
- real banking or payment movement;
- elaborate user-management or design-system features;
- agent reasoning inside external demo applications.

The intelligence remains in XYENA. The demo applications exist to serve controlled MCP evidence and predictable scenarios.

---

## 22. Recommended Build Order

### Milestone 1 — Shared foundation

- shared identifiers and schemas;
- service-token authentication;
- MCP request/response envelope;
- audit middleware;
- seed/reset framework;
- subdomain routing and TLS for the demo environment.

### Milestone 2 — GST platform

- taxpayer, invoice, line-item and return tables;
- basic GST UI;
- GST MCP tools;
- normal, fake, cancelled, duplicate and injection seeds.

### Milestone 3 — Delivery platform

- delivery, item, event, POD and acceptance tables;
- basic Delivery UI;
- Delivery MCP tools;
- full, partial, mismatch, forged-POD and injection seeds.

### Milestone 4 — XYENA integration

- connector registration in central MCP Gateway;
- Evidence Trust schemas and receipt issuance;
- Invoice and Delivery Agent tool allowlists;
- cross-source consistency rules;
- Guardian scenario policies and action graph.

### Milestone 5 — Demonstration hardening

- one-command seed/reset;
- dashboards and correlation tracing;
- subdomain health checks;
- scripted normal and attack demonstrations;
- backup demo dataset and offline fallback.
