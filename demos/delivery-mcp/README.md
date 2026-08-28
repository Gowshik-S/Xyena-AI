# XYENA Delivery MCP

An isolated synthetic logistics source application for XYENA + Guardian. It provides a professional operator console, an OpenAPI 3.1 REST API, seven reviewed MCP read tools, signed source envelopes, and a signed cross-application event inbox.

This service is deliberately separate from the bank, GST, ERP, and funder demos. It does not call or start those applications.

## Security model

The browser never supplies a tenant or actor identity. `X-Demo-Token` resolves both values on the server and grants exactly one role:

| Role | Permitted work |
|---|---|
| `DEMO_VIEWER` | Read dashboards and deliveries |
| `SELLER_OPERATOR` | Create, prepare, dispatch, pre-dispatch cancel, request correction |
| `CARRIER_OPERATOR` | Transit events, delivery attempt, proof capture, request correction |
| `BUYER_RECEIVER` | Buyer acceptance after verified proof, request correction |
| `DELIVERY_REVIEWER` | Independent proof review, controlled correction review, post-dispatch cancellation |
| `DEMO_ADMIN` | Demo administration and most operational setup actions; it cannot replace independent proof or correction review |

All delivery mutations require `If-Match: <current-version>`. The service locks the aggregate, rejects stale versions with HTTP 409, increments the version, and writes the audit plus outbox event in the same database transaction.

The role tokens are a local synthetic-demo adapter. Production deployment must replace them with XYENA OIDC/service identity claims while retaining the same `ActorScope` and role checks.

## Lifecycle

```text
CREATED
  -> READY_TO_DISPATCH (server issues XY tracking number)
  -> DISPATCHED
  -> IN_TRANSIT
  -> OUT_FOR_DELIVERY
  -> DELIVERED_PENDING_ACCEPTANCE | PARTIAL_PENDING_ACCEPTANCE
  -> DELIVERED | PARTIALLY_ACCEPTED | REJECTED
```

Failures move to `DELIVERY_FAILED` and may resume to `IN_TRANSIT`. Terminal records are immutable except through preserved historical/audit records. A buyer acceptance is rejected unless a distinct reviewer has verified a pending proof-of-delivery record.

## MCP contract

The endpoint is `POST /mcp/` using Streamable HTTP and bearer authentication. Guardian also supplies the signed `ai.xyena/runtime` scope for every call. Registration exposes exactly:

- `delivery.deliveries.get`
- `delivery.deliveries.find_by_invoice`
- `delivery.deliveries.find_by_po`
- `delivery.events.list`
- `delivery.proofs.get`
- `delivery.acceptance.get`
- `delivery.fulfilment.verify`

Every successful tool result contains a source-system signature, source record version, `retrieved_at`, `fresh_until`, and synthetic/tenant security labels. The delivery app does **not** issue Guardian `EvidenceReceipt` identifiers. Guardian validates the source result and creates its own evidence receipt.

`fulfilment.verify` requires purchase-order ID, invoice ID, line identity, claimed quantity, and claimed unit value. It only supports a claim using lines from independently accepted delivery records.

## Cross-application events

`POST /api/v1/events/inbox` accepts the versioned OpenAPI event envelope for:

- `purchase_order.cancelled`
- `invoice.cancelled`
- `business.updated`

The raw JSON request must have an `X-Xyena-Signature` HMAC-SHA256 signature made with `DELIVERY_DEMO_EVENT_SIGNING_KEY`. The inbox deduplicates source event IDs and rejects stale aggregate versions. It preserves delivery history and raises source exceptions instead of deleting records.

## Local configuration

Copy `.env.example` to `.env` and replace every placeholder with a distinct secret. Start the service and its isolated PostgreSQL database:

```bash
docker compose up --build delivery-demo
```

Open `http://localhost:8095`. API documentation is available at `/docs` and the schema at `/openapi.json`.

The external Docker network `xyena-core_backend` must already exist when the service is connected to XYENA. Create it once with `docker network create xyena-core_backend` when running the demo independently.

To register the seven tools after XYENA is healthy:

```bash
docker compose --profile registration run --rm register
```

## Operational endpoints

- `/health/live` and `/health/ready` for orchestration
- `/metrics` for tenant record count (reviewer/admin only)
- `/api/v1/audit` for hashed before/after mutation evidence (reviewer/admin only)
- `/api/v1/events/stream` for authenticated, committed outbox notifications
- `/api/v1/admin/scenarios` for the seeded synthetic scenario catalogue (admin only)

## Seeded data

The five records demonstrate accepted fulfilment, partial acceptance, source identity mismatch, rejected/replacement proof, and prompt-injection-shaped business text. That text is always treated as untrusted data; it is never interpreted as an instruction.

## Production boundary

This demo now enforces the intended application contracts, but production rollout still requires organization-managed OIDC, KMS/HSM secrets, private object storage with malware scanning, Alembic migration operations, a durable event broker/outbox publisher, centralized observability, backup/restore drills, and deployment-specific retention policies.
