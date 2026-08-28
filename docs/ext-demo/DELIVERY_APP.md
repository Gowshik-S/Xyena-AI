# Delivery and Fulfilment External Demo Application

## 1. Application identity

```text
Application ID   xyena-demo-delivery
Subdomain        delivery.demo.xyena.ai
UI               https://delivery.demo.xyena.ai/
REST API         https://delivery.demo.xyena.ai/api/v1
MCP              https://delivery.demo.xyena.ai/mcp
MCP audience     xyena-demo-delivery-mcp
Database         isolated PostgreSQL database/schema
```

This is a functioning delivery application: operators create shipments, dispatch items, post events, upload proof metadata, record buyer acceptance and correct records through controlled workflows. Current state is exposed through MCP.

## 2. Users and roles

| Role | Capabilities |
|---|---|
| Delivery Viewer | search deliveries and view timelines/POD metadata |
| Seller Operator | create delivery and dispatch seller-owned shipment |
| Carrier Operator | update transit events and delivery attempt |
| Buyer Receiver | accept, partially accept or reject delivered items |
| Delivery Reviewer | verify POD, resolve exceptions, approve correction |
| Demo Admin | scenario/reset/reference management |
| MCP Read Client | invoke delivery evidence tools |

## 3. UI requirements

### Dashboard

- counts by status and ageing;
- deliveries due/late/exceptioned today;
- accepted/rejected/partial values;
- recent events, POD verification failures and invoice mismatches;
- live event-driven refresh.

### Delivery list/detail

- filter by delivery, invoice, PO, seller, buyer, carrier, tracking number, date and status;
- shipment header, addresses and declared value;
- item quantities: ordered, dispatched, delivered, accepted and rejected;
- chronological status timeline;
- POD metadata and integrity status;
- buyer acceptance panel;
- exception and correction workflow;
- version/audit display.

### Operational screens

- create delivery from PO/invoice reference;
- dispatch items;
- post pickup/transit/out-for-delivery events;
- record delivery attempt and POD;
- buyer item-level acceptance/rejection;
- reviewer POD verification and discrepancy resolution.

## 4. State machines

### Delivery

```text
CREATED → READY_TO_DISPATCH → DISPATCHED → IN_TRANSIT → OUT_FOR_DELIVERY
   └──────────────→ CANCELLED                               │
                                                            ├→ DELIVERED_PENDING_ACCEPTANCE
                                                            ├→ PARTIAL_PENDING_ACCEPTANCE
                                                            └→ DELIVERY_FAILED → IN_TRANSIT/CANCELLED

DELIVERED_PENDING_ACCEPTANCE → DELIVERED/REJECTED
PARTIAL_PENDING_ACCEPTANCE   → PARTIALLY_ACCEPTED/REJECTED
```

Rules:

- quantities cannot become negative or exceed prior-stage quantities;
- accepted + rejected cannot exceed delivered;
- dispatch requires linked seller/buyer/PO and at least one item;
- delivery completion requires a configured proof type;
- cancellation after dispatch requires reviewer permission and reason;
- corrections append a new correction/version; they never remove prior events.

### POD

```text
CAPTURED → PENDING_VERIFICATION → VERIFIED
                               └→ REJECTED → REPLACED
```

### Buyer acceptance

```text
PENDING → ACCEPTED
        → PARTIALLY_ACCEPTED
        → REJECTED
```

## 5. Data model

### `deliveries`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | primary key |
| `tenant_id` | string | required |
| `delivery_number` | string | tenant-unique |
| `purchase_order_id` | string | ERP reference |
| `invoice_id` | string/null | GST reference |
| `invoice_number` | string/null | reconciliation display |
| `seller_business_id` | string | registry reference |
| `seller_gstin` | string | normalized |
| `buyer_id` | string | ERP/registry reference |
| `buyer_gstin` | string | normalized |
| `carrier_id` | string/null | carrier reference |
| `tracking_number` | string/null | synthetic 10-character tracking ID; tenant-unique where set |
| `status` | enum | state machine |
| `ship_from` | JSON | schema validated |
| `ship_to` | JSON | schema validated |
| `dispatch_date` | timestamp/null | state dependent |
| `expected_delivery_date` | date/null | optional |
| `delivered_at` | timestamp/null | state dependent |
| `currency` | string | default `INR` |
| `declared_value` | decimal(18,2) | server checked |
| `verified_delivered_value` | decimal(18,2) | calculated from accepted items |
| `exception_code` | string/null | controlled code |
| `version` | integer | optimistic concurrency |
| `created_at/by` | timestamp/string | audit metadata |
| `updated_at/by` | timestamp/string | audit metadata |

### `delivery_items`

Contains delivery ID, PO line ID, invoice line ID, SKU, description, unit, ordered/dispatched/delivered/accepted/rejected quantities, supported unit value, rejection reason and line version.

### `delivery_events`

Append-only events with event type/time, actor, coarse location, notes, source channel/hash, prior/new status, version and correlation ID. Event time cannot violate configured sequence without an exception flag and reviewer action.

### `proofs_of_delivery`

Contains proof type, restricted object key, content hash, MIME type, captured time, recipient token/name/role, verification status/method, verifier, replacement link and security flags. MCP returns metadata/hashes, not raw binaries by default.

### `buyer_acceptances`

Contains delivery/version, buyer identity, status, accepted value, item-level acceptance snapshot, actor, reason, time and source hash.

### `delivery_corrections`

Contains target aggregate/version, correction type, proposed changes, reason, requester, reviewer, decision and applied version.

Shared audit, outbox and inbox tables are mandatory.

### Synthetic tracking ID

The demo service generates a tracking ID when a delivery becomes ready for dispatch. The identifier
looks operationally realistic while remaining visibly owned by the XYENA demonstration environment:

```text
Format   XY[A-HJ-NP-Z2-9]{8}
Length   exactly 10 characters
Example  XY7K4M9Q2P
```

Rules:

- `XY` is a fixed synthetic prefix and the remaining eight characters are generated randomly;
- use a cryptographically secure random generator, not timestamps, counters or truncated database IDs;
- omit visually ambiguous characters `I`, `O`, `0` and `1`;
- enforce a unique database constraint on `(tenant_id, tracking_number)`;
- regenerate on the unlikely event of a collision;
- generate the value server-side and never accept a browser-supplied tracking ID;
- the tracking ID is immutable after dispatch except through an approved correction that preserves
  the previous value in history; and
- UI, REST, MCP, events and audit records return the same stored value rather than generating a new
  value for each read.

The value is synthetic and must not copy or claim to use a real carrier's tracking-number format.

## 6. REST API

```text
GET    /api/v1/dashboard
GET    /api/v1/deliveries
POST   /api/v1/deliveries
GET    /api/v1/deliveries/:deliveryId
PATCH  /api/v1/deliveries/:deliveryId
POST   /api/v1/deliveries/:deliveryId/ready
POST   /api/v1/deliveries/:deliveryId/dispatch
POST   /api/v1/deliveries/:deliveryId/events
POST   /api/v1/deliveries/:deliveryId/delivery-attempt
POST   /api/v1/deliveries/:deliveryId/proofs
POST   /api/v1/deliveries/:deliveryId/acceptance
POST   /api/v1/deliveries/:deliveryId/cancel
POST   /api/v1/deliveries/:deliveryId/corrections
POST   /api/v1/corrections/:correctionId/approve
POST   /api/v1/corrections/:correctionId/reject
GET    /api/v1/deliveries/:deliveryId/history
GET    /api/v1/events/stream
POST   /mcp
```

## 7. MCP tools

| Tool | Required inputs | Output |
|---|---|---|
| `delivery.deliveries.get` | delivery ID | current delivery, items, versions and status |
| `delivery.deliveries.find_by_invoice` | invoice ID or seller + number | matching delivery summaries |
| `delivery.deliveries.find_by_po` | purchase-order ID | matching deliveries |
| `delivery.events.list` | delivery ID | ordered immutable timeline |
| `delivery.proofs.get` | delivery ID | POD metadata, hashes and verification status |
| `delivery.acceptance.get` | delivery ID | latest acceptance and item snapshot |
| `delivery.fulfilment.verify` | invoice/PO line claims | deterministic quantity/value comparison |

`delivery.fulfilment.verify` returns line-level matches, unmatched lines, over/under-delivery, accepted quantities, supported values, contradiction codes, source versions and current freshness.

## 8. Value calculation

```text
Supported Accepted Quantity
= MIN(invoiced_quantity, accepted_quantity)

Supported Line Value
= Supported Accepted Quantity × supported_unit_value

Verified Delivered Value
= SUM(Supported Line Value)
```

The Delivery app reports fulfilment evidence. It does not calculate the final financing amount.

## 9. Published events

```text
delivery.created
delivery.ready
delivery.dispatched
delivery.event_recorded
delivery.delivery_attempted
delivery.pod_captured
delivery.pod_verified
delivery.pod_rejected
delivery.accepted
delivery.partially_accepted
delivery.rejected
delivery.cancelled
delivery.corrected
```

## 10. Consumed events

- `purchase_order.created/updated/cancelled` from ERP;
- `invoice.registered/cancelled` from GST;
- `business.updated` for seller/buyer identity drift;
- cancellation or mismatch creates an exception; it does not delete delivery history.

## 11. Live update behavior

- Dispatch/status/POD/acceptance commits publish outbox events.
- Operations dashboards and open detail screens refetch on relevant SSE events.
- MCP reads immediately expose the committed version.
- XYENA invalidates delivery evidence cache on state, item, POD or acceptance changes.
- A case using an older delivery receipt receives a freshness/change signal and can be reevaluated.
- Duplicate external events are ignored using the inbox unique key.

## 12. Validation and security

- item quantities follow monotonic bounds and state rules;
- PO/invoice/seller/buyer identifiers are immutable after dispatch except approved correction;
- tracking IDs match `^XY[A-HJ-NP-Z2-9]{8}$`, are generated server-side and are tenant-unique;
- POD binaries live in restricted object storage and are hash verified;
- notes, addresses, recipient names and rejection reasons are untrusted strings;
- event timestamps and actor permissions are validated server-side;
- no agent MCP credential can create events, alter status or approve a correction;
- version conflict prevents lost updates.

## 13. Seed scenarios

- full delivery and buyer acceptance;
- partial delivery;
- over-delivery claim;
- buyer/seller/invoice mismatch;
- delivery before dispatch timestamp;
- forged/replaced POD;
- rejected items;
- cancelled invoice after dispatch;
- prompt injection in notes, description or rejection reason;
- duplicate event/webhook replay;
- stale delivery version.

## 14. Acceptance criteria

1. Authorized users can create, dispatch, track, deliver and accept a shipment.
2. Data remains after reload and every transition appears in the audit timeline.
3. Multiple open browser screens reflect committed updates without manual reload.
4. MCP reads use the same current database state.
5. Partial acceptance produces the correct supported value.
6. POD metadata and hashes are retrievable without exposing raw evidence by default.
7. Corrections require review and preserve prior versions/events.
8. Cross-app invoice/PO changes create visible exceptions.
9. The application deploys independently at `delivery.demo.xyena.ai`.

