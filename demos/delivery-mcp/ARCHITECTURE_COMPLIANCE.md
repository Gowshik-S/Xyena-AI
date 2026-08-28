# Delivery architecture compliance

## Implemented

- Tenant-scoped PostgreSQL-compatible domain records for deliveries, lines, events, proof metadata, buyer acceptance, controlled corrections, audit, inbox, outbox, and external aggregate versions.
- Server-derived actor and tenant context with separate seller, carrier, buyer, reviewer, viewer, and administrator credentials.
- Exact lifecycle transitions, server-issued tracking identifiers, bounded `Decimal` quantities and values, row locks, and `If-Match` optimistic concurrency.
- Independent proof review before buyer acceptance; no proof auto-approval.
- Transactional audit and outbox records with meaningful before/after hashes and correlation IDs.
- Signed, idempotent, version-aware cross-app inbox for purchase order, invoice, and business changes.
- Seven exact, tenant-scoped, signed MCP source tools compatible with the XYENA registry and Guardian runtime envelope.
- Authenticated operator REST API, OpenAPI 3.1 schema, committed-event SSE stream, audit endpoint, metrics endpoint, health checks, and scenario catalogue.
- Professional light operator UI with separate overview, register, and detail pages; workflow controls appear only for the connected role and valid state.
- Isolated PostgreSQL Compose service and explicit external connection to the XYENA core backend network.

## Deliberately not implemented here

- Guardian evidence-receipt creation. That is owned by Guardian after signature, freshness, policy and contradiction evaluation.
- Bank, GST, ERP, funder, or other financial-demo behavior.
- Production identity provider, key-management service, blob store, event broker, or infrastructure deployment. The interfaces are ready, but those services are environment concerns.

## Applications expected to be ready

1. The Delivery operator console at `/`, `/deliveries`, and `/detail?id=...`.
2. The Delivery OpenAPI API and interactive contract at `/docs`.
3. The Delivery Streamable HTTP MCP source at `/mcp/`.
4. The registration job that discovers and activates exactly seven reviewed `delivery.*` tools in XYENA.
5. Guardian/Xyena consumers that validate the source envelope and create platform-owned evidence receipts.
