# Business Registry External Demo Application

## 1. Application identity

```text
Application ID   xyena-demo-registry
Subdomain        registry.demo.xyena.ai
UI               https://registry.demo.xyena.ai/
REST API         https://registry.demo.xyena.ai/api/v1
MCP              https://registry.demo.xyena.ai/mcp
MCP audience     xyena-demo-registry-mcp
```

The Registry application is the authoritative demo source for business identity, legal status, ownership, registered addresses, directors/authorized persons and buyer-seller relationships.

## 2. Users and roles

| Role | Capabilities |
|---|---|
| Registry Viewer | search and view business records |
| Registry Operator | create pending record and propose updates |
| Registry Reviewer | activate, suspend, dissolve or approve corrections |
| Demo Admin | reference/scenario/reset administration |
| MCP Read Client | invoke identity and relationship tools |

## 3. UI requirements

- dashboard by business type/status/state and recent changes;
- business search by registry ID, name, GSTIN reference and status;
- business detail with legal identity, addresses, registrations and history;
- ownership/director/authorized-person relationships;
- buyer/seller/counterparty relationships;
- controlled status and correction workflows;
- version, source hash, audit and cross-system mismatch panels;
- SSE-driven live refresh.

## 4. State machines

### Business

```text
PENDING_REVIEW → ACTIVE → SUSPENDED → ACTIVE
                       └────────────→ DISSOLVED
PENDING_REVIEW → REJECTED
```

### Proposed change

```text
DRAFT → SUBMITTED → APPROVED/APPLIED
                  → REJECTED
```

Active identity fields are changed only through an approved versioned change. Historical versions remain queryable.

## 5. Data model

### `businesses`

| Field | Type | Constraints |
|---|---|---|
| `id` | UUID/string | primary key/shared `business_id` |
| `tenant_id` | string | required |
| `registry_number` | string | unique |
| `business_type` | enum | `PROPRIETORSHIP`, `PARTNERSHIP`, `LLP`, `COMPANY`, `OTHER` |
| `legal_name` | string | required, bounded |
| `trade_name` | string/null | bounded |
| `incorporation_date` | date | required |
| `status` | enum | business state machine |
| `registered_state_code` | string | required |
| `registered_address` | JSON | schema validated |
| `industry_code` | string/null | demo classification |
| `msme_classification` | enum/null | `MICRO`, `SMALL`, `MEDIUM` |
| `primary_gstin` | string/null | GST app reference |
| `pan_token` | string/null | synthetic/tokenized |
| `source_hash` | string | canonical record hash |
| `version` | integer | optimistic concurrency |
| `created_at/by` | timestamp/string | audit metadata |
| `updated_at/by` | timestamp/string | audit metadata |

### `business_names`

Stores legal/trade/previous names with effective dates and record versions.

### `business_addresses`

Stores registered/operating addresses, validity period, verification status and source hash.

### `business_people`

Stores synthetic person tokens, role, appointment/cessation dates, authorization status and verification metadata. No real PII.

### `ownership_links`

Stores owner type/ID, ownership percentage, effective dates, source hash and version. Percentages are validated for configured business types.

### `business_relationships`

Stores source business, target business, relationship type (`BUYER`, `SELLER`, `GROUP`, `GUARANTOR`, `SERVICE_PROVIDER`), status, effective dates and evidence hash.

### `change_requests`

Stores target record/version, requested patch, reason, requester, reviewer, decision and applied version.

Shared audit/outbox/inbox tables are mandatory.

## 6. REST API

```text
GET    /api/v1/dashboard
GET    /api/v1/businesses
POST   /api/v1/businesses
GET    /api/v1/businesses/:businessId
PATCH  /api/v1/businesses/:businessId/draft
POST   /api/v1/businesses/:businessId/submit
POST   /api/v1/businesses/:businessId/status
POST   /api/v1/businesses/:businessId/change-requests
POST   /api/v1/change-requests/:id/approve
POST   /api/v1/change-requests/:id/reject
GET    /api/v1/businesses/:businessId/ownership
GET    /api/v1/businesses/:businessId/relationships
GET    /api/v1/businesses/:businessId/history
GET    /api/v1/events/stream
POST   /mcp
```

## 7. MCP tools

| Tool | Output |
|---|---|
| `registry.businesses.get` | current business identity/status/version |
| `registry.businesses.verify` | deterministic comparison with claimed identity |
| `registry.businesses.search` | bounded candidate list |
| `registry.ownership.get` | current ownership/director graph |
| `registry.relationships.get` | approved buyer/seller/group relationships |
| `registry.authorized_persons.get` | tokenized authorized roles and status |

All tools are read-only and cite server record versions and hashes.

## 8. Events

Publishes:

```text
business.created
business.activated
business.updated
business.suspended
business.dissolved
business.ownership_changed
business.relationship_changed
```

Consumes GST registration-status events only to display/flag inconsistency. GST events do not directly rewrite legal identity.

## 9. Live updates

- Approved identity/status/ownership changes commit with audit/outbox.
- Search/detail/relationship pages refetch on SSE events.
- MCP reads expose the new version immediately.
- XYENA invalidates affected business evidence receipts/caches and can reevaluate open cases.
- Other apps mark identity drift rather than overwriting their historical transaction records.

## 10. Seed scenarios

- active MSME with consistent GST/bank identity;
- suspended/dissolved business;
- changed legal name;
- hidden related-party ownership;
- buyer-seller relationship absent or revoked;
- prompt injection in trade name/address;
- conflicting GSTIN and ownership evidence;
- stale business version.

## 11. Acceptance criteria

- registry workflows persist and preserve historical versions;
- ownership and relationship graphs are queryable through UI/API/MCP;
- approval/status changes propagate live;
- external mismatches are flagged without cross-app data corruption;
- cross-tenant and unauthorized mutations are denied;
- app deploys independently at `registry.demo.xyena.ai`.

