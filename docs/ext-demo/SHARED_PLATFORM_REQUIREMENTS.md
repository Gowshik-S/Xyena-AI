# Shared External Demo Platform Requirements

## 1. Functional quality

Every external demo application must be a working, stateful application rather than a static mock UI.

The source of truth is the application's relational database. UI pages, REST APIs, MCP tools, events, and audit views read from the same committed domain state.

## 2. Reference implementation profile

The requirements are technology-neutral. A practical reference profile is:

```text
Frontend             React application
Backend              TypeScript service
Database             PostgreSQL
Cache/rate limiting  Redis when required
Events               transactional PostgreSQL outbox + event relay
Live UI              Server-Sent Events; WebSocket only for bidirectional use cases
MCP                   one MCP endpoint per application
Deployment            one container/service per application
Ingress               TLS reverse proxy with one subdomain per application
Observability         OpenTelemetry-compatible logs, metrics and traces
```

SQLite can be used for a local spike, but the shared demo environment should use PostgreSQL so concurrency, transactions, row locking, migrations, JSON fields, and outbox delivery behave consistently.

## 3. Application layers

```text
Browser UI
   ↓ REST/SSE
Application API
   ↓
Domain service and state machine
   ↓
Repository / transaction boundary
   ├── domain tables
   ├── audit_events
   ├── outbox_events
   └── inbox_events

Central MCP Gateway
   ↓ authenticated MCP request
MCP tool handler
   ↓ same domain service/repository
Current committed domain state
```

MCP handlers must not maintain a separate copy of application data.

## 4. Live-update contract

### Write path

```text
User/API command
    ↓ authenticate + authorize
Validate current version and transition
    ↓
Database transaction
    ├── update domain aggregate
    ├── append immutable audit event
    └── insert outbox event
    ↓ commit
Outbox relay publishes event
    ├── SSE/WebSocket subscribers refresh
    ├── external webhooks/event consumers update
    └── XYENA invalidates stale evidence/cache
```

### UI behavior

- List and detail pages subscribe to resource or tenant event streams.
- Events contain resource ID, version, event type, timestamp and correlation ID—not the entire sensitive record.
- On an event, the UI refetches the current resource through the API.
- The UI shows last-updated time and current version.
- Stale edit forms receive `409 VERSION_CONFLICT` and offer reload/reapply behavior.
- Optimistic UI may be used only for reversible non-financial edits; authoritative status is shown after server commit.

### MCP behavior

- MCP tools always read the latest committed version unless an explicit `as_of` snapshot is requested.
- Results include `record_version`, `updated_at`, `retrieved_at`, and `fresh_until` where appropriate.
- Cached connector results are invalidated by domain events.
- Stale results cannot silently satisfy a Guardian freshness policy.

## 5. Shared base record

Every mutable aggregate includes:

| Field | Type | Requirement |
|---|---|---|
| `id` | UUID/string | immutable |
| `tenant_id` | string | mandatory scope |
| `status` | enum | state-machine controlled |
| `version` | integer | increments on every mutation |
| `created_at` | timestamp | server generated |
| `created_by` | string | authenticated actor |
| `updated_at` | timestamp | server generated |
| `updated_by` | string | authenticated actor |
| `deleted_at` | timestamp/null | soft delete only where policy permits |

Hard deletion of records referenced by evidence, financial actions, audit, or another application is forbidden. Use cancellation, deactivation, archival, or a new correcting version.

## 6. Audit model

Each app contains `audit_events`:

| Field | Type |
|---|---|
| `id` | UUID/string |
| `tenant_id` | string |
| `application_id` | string |
| `aggregate_type` | string |
| `aggregate_id` | string |
| `aggregate_version` | integer |
| `event_type` | string |
| `actor_type` | `USER`, `SERVICE`, `AGENT`, `SYSTEM` |
| `actor_id` | string |
| `reason` | string/null |
| `before_hash` | string/null |
| `after_hash` | string |
| `metadata` | JSON |
| `correlation_id` | string |
| `occurred_at` | timestamp |

Audit rows are append-only. Sensitive values are referenced by token/hash rather than duplicated in logs.

## 7. Outbox and inbox models

### `outbox_events`

| Field | Type |
|---|---|
| `id` | UUID/string |
| `tenant_id` | string |
| `aggregate_type` | string |
| `aggregate_id` | string |
| `aggregate_version` | integer |
| `event_type` | string |
| `schema_version` | string |
| `payload` | JSON |
| `correlation_id` | string |
| `created_at` | timestamp |
| `published_at` | timestamp/null |
| `attempt_count` | integer |
| `last_error` | string/null |

### `inbox_events`

| Field | Type |
|---|---|
| `source_application` | string |
| `event_id` | string |
| `event_type` | string |
| `received_at` | timestamp |
| `processed_at` | timestamp/null |
| `status` | `RECEIVED`, `PROCESSED`, `REJECTED`, `FAILED` |
| `payload_hash` | string |
| `last_error` | string/null |

The unique key `(source_application, event_id)` prevents duplicate processing.

## 8. Shared event envelope

```json
{
  "event_id": "evt_1001",
  "event_type": "invoice.registered",
  "schema_version": "1.0",
  "source_application": "xyena-demo-gst",
  "tenant_id": "tenant_demo_01",
  "aggregate": {
    "type": "invoice",
    "id": "inv_1023",
    "version": 4
  },
  "data": {
    "invoice_id": "inv_1023",
    "status": "REGISTERED"
  },
  "correlation_id": "corr_demo_8001",
  "occurred_at": "2026-08-28T10:30:00Z",
  "signature": "service-event-signature"
}
```

Consumers validate the issuer, audience/route, schema, signature, tenant, event ID and version before applying an event.

## 9. Shared MCP envelope

### Request

```json
{
  "tool_call_id": "tc_1001",
  "tool": "gst.invoices.get",
  "trusted_scope": {
    "tenant_id": "tenant_demo_01",
    "msme_id": "msme_demo_01",
    "case_id": "case_demo_1023"
  },
  "purpose": "Verify invoice INV-1023",
  "arguments": {"invoice_id": "inv_1023"},
  "correlation_id": "corr_demo_8001"
}
```

### Response

```json
{
  "schema_version": "gst.invoice.v1",
  "source_system": "xyena-demo-gst",
  "request_id": "req_2001",
  "record_version": 4,
  "updated_at": "2026-08-28T10:28:00Z",
  "retrieved_at": "2026-08-28T10:30:00Z",
  "data": {},
  "source_signature": "service-response-signature",
  "security_labels": ["EXTERNAL_DATA", "DEMO_SOURCE"]
}
```

Raw responses go to XYENA's Evidence Trust Gateway. External applications cannot issue an authoritative XYENA evidence receipt.

## 10. Identity and roles

### Shared roles

| Role | Capability |
|---|---|
| `DEMO_VIEWER` | read application data |
| `DEMO_OPERATOR` | normal operational transitions |
| `DEMO_REVIEWER` | approve/reject controlled transitions |
| `DEMO_ADMIN` | manage scenarios and reference data |
| `MCP_READ_CLIENT` | invoke approved read tools |
| `MCP_PREPARE_CLIENT` | invoke preparation tools |
| `EXECUTION_GATEWAY` | invoke Guardian-authorized execution tools |
| `EVENT_CONSUMER` | receive signed domain events |

Every service token has an application-specific audience and tool scopes. Browser sessions are not accepted as MCP service credentials.

## 11. Security requirements

- TLS on every deployed subdomain.
- Exact CORS allowlist; no wildcard credentials.
- CSRF protection for cookie-authenticated UI writes.
- Short-lived service tokens and key rotation.
- Server-side tenant/case scope injection.
- Deny-by-default tool and API policies.
- Strict input and output schemas.
- Decimal types for money; never floating point.
- Account, identity and personal values masked/tokenized before model context.
- Raw documents and external strings labelled untrusted.
- Rate limits by caller, tenant, route/tool and action type.
- Idempotency keys for externally visible state changes.
- Append-only audit and transactional event outbox.
- No real production credentials or customer data.

## 12. Standard endpoints

Every application exposes:

```text
GET  /health/live
GET  /health/ready
GET  /metrics                    protected
GET  /api/v1/events/stream       authenticated SSE
GET  /api/v1/audit               reviewer/admin
GET  /api/v1/admin/scenarios     admin
POST /api/v1/admin/scenarios/:id/load
POST /api/v1/admin/reset
POST /mcp                        service authenticated
```

Domain-specific endpoints are documented per application.

## 13. Configuration baseline

```dotenv
APP_ENV=demo
APP_ID=xyena-demo-gst
PUBLIC_BASE_URL=https://gst.demo.xyena.ai
DATABASE_URL=secret-reference
REDIS_URL=secret-reference
IDENTITY_ISSUER=https://identity.demo.xyena.ai
MCP_AUDIENCE=xyena-demo-gst-mcp
EVENT_SIGNING_KEY=secret-reference
SOURCE_SIGNING_KEY=secret-reference
ALLOWED_UI_ORIGINS=https://app.demo.xyena.ai
EVENT_RELAY_ENABLED=true
SSE_ENABLED=true
ALLOW_DEMO_ADMIN=true
RAW_PAYLOAD_LOGGING=false
LOG_LEVEL=info
```

## 14. Deployment requirements

Each app has:

- independent build artifact/container;
- independent migration job;
- isolated database or database schema and credentials;
- independent DNS, certificate, readiness and autoscaling policy;
- explicit outbound destination allowlist;
- backup/restore procedure for the shared demo environment;
- deterministic scenario seed version.

One application failure must not corrupt another application's database. Cross-application updates are eventual and idempotent; financial execution and local ledger posting use the stronger transaction/idempotency rules defined in their specific applications.

## 15. Test baseline

Every application must pass:

- domain state-machine unit tests;
- database migration and repository tests;
- API and MCP schema contract tests;
- authorization and cross-tenant denial tests;
- optimistic-concurrency tests;
- outbox publication and inbox deduplication tests;
- SSE live-refresh tests;
- idempotency and replay tests;
- prompt/JSON injection containment tests;
- subdomain health and end-to-end workflow tests.

