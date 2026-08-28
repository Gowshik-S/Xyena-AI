# XYENA synthetic Buyer ERP

This folder contains the isolated Buyer ERP demonstration for Xyena and Guardian. It models the
commercial evidence chain from purchase order through goods/service receipt, GST invoice matching
and buyer acceptance. It is a synthetic procure-to-pay evidence system: it is not a payment system,
bank, accounting product or government GST portal.

## Ready application surfaces

The professional light interface is split into focused operational pages:

| Page | Purpose |
|---|---|
| `/` | Tenant overview, commercial document chain and exception queue |
| `/purchase-orders` | Versioned purchase-order register and fulfilment state |
| `/receipts` | Goods/service receipt evidence and accepted/rejected values |
| `/invoice-matching` | Three-way PO/receipt/GST invoice matching and discrepancies |
| `/counterparties` | Buyer/supplier identity, terms and relationship controls |
| `/activity` | Immutable audit trail and outbox position |
| `/mcp-connection` | Reviewed MCP catalog, scope and authority boundary |
| `/docs` | OpenAPI 3.1 API description |
| `/mcp` | Bearer-protected MCP v2 Streamable HTTP endpoint |

The visual system uses cool paper, charcoal and deep ledger green, with restrained brass and rust
status accents. It contains no gradients, neon, purple or generic AI styling. Its signature element
is the document chain: purchase order → receipt → GST invoice → buyer acceptance.

## Domain ownership and workflow

Buyer ERP owns counterparties, purchase orders, receipt posting, deterministic three-way matching
and buyer acceptance. GST remains authoritative for invoice registration, IRN and cancellation.

```text
ERP operator creates and approves PO
        ↓
Warehouse posts accepted/rejected receipt
        ↓
Signed GST event arrives with authoritative invoice snapshot
        ↓
ERP deduplicates event and rejects stale versions
        ↓
PO + receipt + GST invoice are matched
        ↓
Human AP reviewer accepts, partially accepts or disputes
```

Later GST cancellation or a newer registered version never deletes ERP history. Any previously
accepted match becomes `REVIEW_REQUIRED`. The signed event inbox, domain record, audit record and
transactional outbox are tenant scoped. An optional `ERP_DEMO_GST_BASE_URL` may retrieve an invoice
snapshot from a compatible service API when the signed event contains only an aggregate reference;
otherwise the producer must include `data.invoice_snapshot`.

## Authentication and authority separation

- `ERP_DEMO_UI_TOKEN` unlocks read-only browser data for this isolated demo tab.
- `ERP_DEMO_ADMIN_TOKEN` protects operator mutations in the OpenAPI surface.
- `If-Match` carries the expected integer version for state transitions.
- `ERP_DEMO_GST_EVENT_SECRET` verifies signed GST event bytes before parsing their authority.
- `ERP_DEMO_MCP_TOKEN` authenticates only the MCP workload endpoint.
- Every MCP call also requires HMAC-signed Xyena runtime `_meta` scope.

These credentials are deliberately separate. A browser token is not an MCP or admin credential.
The frontend currently presents the review console; operational mutations remain available through
the documented API so role-specific form workflows can be added without weakening the boundary.

## MCP catalog

Registration installs exactly six read-only tools as `SENSITIVE_READ`, with
`approval_mode=POLICY`, `allowed_agents=[xyena-supervisor]` and Guardian enforcement:

| Canonical name | Evidence returned |
|---|---|
| `erp.counterparties.verify` | Approved identity, GSTIN, terms and risk flags |
| `erp.purchase_orders.get` | Tenant-scoped PO header, lines, state and version |
| `erp.purchase_orders.find_by_invoice` | PO associated with an authoritative invoice |
| `erp.receipts.get` | Receipt posting and accepted/rejected evidence |
| `erp.invoice_matches.get` | Three-way values, supported amount and discrepancies |
| `erp.invoice_acceptance.get` | Human acceptance status and matched version |

Each result includes a signed evidence receipt. MCP cannot create or approve a PO, post a receipt,
accept an invoice, alter a counterparty or move money.

## Data model

The SQLAlchemy/PostgreSQL model contains `counterparties`, `purchase_orders`,
`purchase_order_lines`, `goods_service_receipts`, `receipt_lines`, `supplier_invoices`,
`invoice_matches`, `invoice_acceptances`, `audit_events`, `outbox_events` and `inbox_events`.
Business aggregates use record versions and tenant keys; monetary values use fixed precision.
Compose places PostgreSQL on an internal ERP-only network.

## Local setup

Use Python 3.12. From this folder:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
buyer-erp-demo
```

The local default uses SQLite. Open `http://localhost:8092/`; the page asks for the configured
`ERP_DEMO_UI_TOKEN`. For isolated PostgreSQL deployment:

```powershell
docker compose up --build -d buyer-erp
```

The Compose stack joins the existing `xyena-core_backend` network. Start Xyena core first so that
network exists. Never commit `.env` or reuse demonstration credentials.

## Register with Xyena and Guardian

Set root `BUYER_ERP_MCP_TOKEN` to the same high-entropy value as `ERP_DEMO_MCP_TOKEN`. Configure the
Xyena service and MCP admin review tokens in the ERP `.env`, then run:

```powershell
docker compose --profile registration run --rm register
```

Registration discovers the remote catalog, requires an exact six-tool match, creates immutable
tool versions, marks the server `REVIEWED_INTERNAL` and activates it. Unexpected catalog drift
stops activation.

## Implemented and intentionally absent

Implemented and ready:

- PostgreSQL/SQLite domain model with deterministic synthetic fixtures;
- purchase-order state transitions and optimistic concurrency;
- goods/service receipt creation, accepted/rejected valuation and posting;
- deterministic invoice matching, partial match, dispute and acceptance workflows;
- signed, deduplicated and version-aware GST event consumption;
- immutable audit, inbox and transactional outbox records;
- OpenAPI 3.1 REST API and multi-page professional light frontend;
- read-only MCP v2 server, evidence receipts and reviewed Xyena registration;
- container and isolated PostgreSQL packaging.

Intentionally absent:

- real buyer, supplier, GSTN, accounting-vendor, bank or government integration;
- payment, disbursement, lending, beneficiary or fund movement;
- mutable MCP tools or autonomous agent approval;
- production IAM, legal/regulatory certification and ERP test-suite execution in this delivery.

