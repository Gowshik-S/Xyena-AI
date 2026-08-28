# Buyer and ERP External Demo Application

## 1. Application identity

```text
Application ID   xyena-demo-erp
Subdomain        erp.demo.xyena.ai
UI               https://erp.demo.xyena.ai/
REST API         https://erp.demo.xyena.ai/api/v1
MCP              https://erp.demo.xyena.ai/mcp
MCP audience     xyena-demo-erp-mcp
```

The ERP app is the operational source for buyer/supplier onboarding, purchase orders, goods/service receipts and invoice acceptance. It provides independent evidence that the underlying commercial transaction exists.

## 2. Users and roles

| Role | Capabilities |
|---|---|
| ERP Viewer | view suppliers, POs, receipts and invoice matches |
| Buyer Procurement | create/approve/cancel purchase orders |
| Warehouse/Service Receiver | record goods/service receipt |
| Accounts Payable | match and accept/reject supplier invoices |
| ERP Reviewer | approve exceptions and corrections |
| Demo Admin | seed/reset/reference administration |
| MCP Read Client | read approved operational evidence |

## 3. UI requirements

- operational dashboard for open POs, received value, unmatched invoices and exceptions;
- supplier/buyer relationship pages;
- PO creation, approval and line-item tracking;
- goods/service receipt screen;
- three-way match view: PO vs invoice vs delivery/receipt;
- invoice acceptance/rejection and dispute history;
- audit timeline and live SSE updates.

## 4. State machines

### Purchase order

```text
DRAFT → SUBMITTED → APPROVED → PARTIALLY_FULFILLED → FULFILLED → CLOSED
          └───────→ REJECTED
APPROVED/PARTIAL → CANCELLED (only unfulfilled remainder)
```

### Receipt

```text
DRAFT → POSTED → CORRECTED
             └→ REVERSED
```

### Invoice match

```text
PENDING → MATCHED → ACCEPTED
        → PARTIAL_MATCH → PARTIALLY_ACCEPTED/DISPUTED
        → MISMATCHED → DISPUTED/REJECTED
```

## 5. Data model

### `counterparties`

Contains buyer/supplier business IDs, GSTINs, relationship status, approved addresses, payment terms, onboarding dates, risk flags and versions.

### `purchase_orders`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | shared PO ID |
| `tenant_id` | string | required |
| `po_number` | string | tenant/buyer unique |
| `buyer_id` | string | required |
| `supplier_business_id` | string | required |
| `buyer_gstin` | string | normalized |
| `seller_gstin` | string | normalized |
| `order_date` | date | required |
| `expected_delivery_date` | date/null | optional |
| `currency` | string | default `INR` |
| `subtotal/tax/total` | decimal(18,2) | server calculated |
| `payment_terms_days` | integer | bounded |
| `status` | enum | state machine |
| `approved_at/by` | timestamp/string null | immutable approval metadata |
| `version` | integer | optimistic concurrency |

### `purchase_order_lines`

Contains SKU/service code, description, ordered quantity, unit, unit price, tax category, received/accepted quantities, cancelled remainder and line version.

### `goods_service_receipts`

Contains receipt ID/number, PO and delivery references, receipt type, posting date, receiver token, status, accepted/rejected value, source hash and version.

### `receipt_lines`

Contains PO line, delivery line, received/accepted/rejected quantities, unit value, discrepancy and reason.

### `supplier_invoices`

Stores GST invoice references and a local matching snapshot: invoice ID/number, seller/buyer, date, claimed total, source version/hash and current match status. GST remains authoritative for registration/IRN.

### `invoice_matches`

Contains PO/invoice/receipt/delivery IDs, tolerance policy, matched quantities/values, discrepancies, status, reviewer and version.

### `invoice_acceptances`

Contains accepted amount, status, reason, actor, time and linked match version.

Shared audit/outbox/inbox tables are mandatory.

## 6. REST API

```text
GET    /api/v1/dashboard
GET    /api/v1/counterparties
POST   /api/v1/counterparties
GET    /api/v1/purchase-orders
POST   /api/v1/purchase-orders
GET    /api/v1/purchase-orders/:poId
PATCH  /api/v1/purchase-orders/:poId
POST   /api/v1/purchase-orders/:poId/submit
POST   /api/v1/purchase-orders/:poId/approve
POST   /api/v1/purchase-orders/:poId/cancel
POST   /api/v1/receipts
GET    /api/v1/receipts/:receiptId
POST   /api/v1/receipts/:receiptId/post
POST   /api/v1/receipts/:receiptId/correct
POST   /api/v1/invoice-matches
GET    /api/v1/invoice-matches/:matchId
POST   /api/v1/invoice-matches/:matchId/accept
POST   /api/v1/invoice-matches/:matchId/dispute
GET    /api/v1/events/stream
POST   /mcp
```

## 7. MCP tools

| Tool | Output |
|---|---|
| `erp.counterparties.verify` | current approved relationship and identity |
| `erp.purchase_orders.get` | PO header/lines/status/version |
| `erp.purchase_orders.find_by_invoice` | candidate POs for invoice |
| `erp.receipts.get` | posted goods/service receipt evidence |
| `erp.invoice_matches.get` | deterministic match and discrepancies |
| `erp.invoice_acceptance.get` | buyer/AP acceptance and supported amount |

Agents receive read-only current or explicit historical versions.

## 8. Events

Publishes PO, receipt, match and acceptance lifecycle events. Consumes business identity changes, GST invoice registration/cancellation and delivery acceptance events.

Consumed data is stored with source event ID/version/hash. Duplicate events are idempotently ignored. Contradictions create exceptions rather than automatic rewrites.

## 9. Live updates

- PO approval, receipt posting and invoice acceptance emit events after commit.
- UI dashboards and match screens refetch on SSE notification.
- MCP results immediately reflect the committed match/version.
- GST cancellation or delivery correction marks the current match `REVIEW_REQUIRED` and publishes an exception event.

## 10. Seed scenarios

- approved PO, full receipt and accepted invoice;
- invoice without PO;
- invoice exceeds PO value;
- partial receipt;
- supplier/buyer mismatch;
- cancelled PO with later invoice;
- duplicate invoice match;
- injected description/notes;
- stale PO or match version.

## 11. Acceptance criteria

- PO-to-receipt-to-invoice matching operates end to end;
- totals and tolerances are deterministic;
- accepted amounts update live and appear in MCP;
- external cancellations/corrections create review exceptions;
- no agent can approve/cancel a PO or accept an invoice through read MCP credentials;
- app deploys independently at `erp.demo.xyena.ai`.

