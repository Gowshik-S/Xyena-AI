# Xyena + Guardian Backend Implementation Status

**Implementation date:** 2026-08-28  
**Scope:** core Xyena platform, Guardian, MCP calling, context, memory, user data, operations, and the
isolated synthetic bank MCP demonstration

**Excluded:** GST, Delivery and other external-domain application runtimes and real financial integrations

**Test execution:** intentionally not run, following the implementation instruction

## Delivered checkpoints

### Phase 1 — platform foundation

Implemented and pushed in commit `48f2440`:

- Python 3.12 project and environment contract;
- FastAPI public API with OpenAPI 3.1, correlation IDs, problem responses, CORS, health endpoints,
  OIDC validation, development bypass disabled by default, and tenant-scoped database sessions;
- sessions, conversations, messages, queued agent runs, run status/events, audit chain, outbox,
  idempotency records, and PostgreSQL durable jobs;
- Alembic migration `0001_core_foundation` with IAM, conversation, agent, audit, and operations
  schemas plus row-level tenant security.

### Phase 2 — MCP registry and execution plane

Implemented and pushed in commit `d7fcefb`:

- MCP v2 Streamable HTTP hosted service at `/mcp`, protected by workload authentication;
- service-authenticated registry, discovery, call, and resume controls;
- remote MCP client with secret references, custom authenticated HTTP transport, timeout, and retry;
- versioned server/tool discovery, canonical tool names, immutable schema hashes, policy status, risk
  classes, agent grants, JSON Schema validation, result limits, attempts, normalized results, and
  idempotency;
- canonical broker as the only supported capability execution path;
- two harmless first-party core tools: `xyena.platform.describe` and
  `xyena.tools.explain_risk`;
- migration `0002_mcp_gateway` and initial active policies.

At the Phase 2 checkpoint, no external demo API had been converted into a tool and no demo MCP server
had been built. The later synthetic bank checkpoint is documented below.

### Phase 3 — Guardian enforcement plane

Implemented and pushed in commit `a6c4e55`:

- independently deployable Guardian FastAPI service and separate database role boundary;
- deterministic default-deny policy evaluation for `READ`, `SENSITIVE_READ`, `MUTATE`, and
  `PRIVILEGED` risks;
- role, purpose, consent, agent-grant, idempotency, and approval checks;
- durable decisions, approval requests, human approve/reject actions, and public approval API proxy;
- Ed25519 JWT authorization bound to tenant, call ID, decision ID, exact canonical request hash,
  constraints, audience, and short expiry;
- token hash only at rest, atomic single-use consumption immediately before execution, and
  fail-closed behavior when Guardian or signing material is unavailable;
- approved-call resume path and `mcp.resume` job;
- migration `0003_guardian` with the active platform-default policy bundle.

### Phase 4 — agents, context, memory, and user data

Implemented and pushed in commit `d4b9b28`:

- OpenAI Agents SDK / Responses API runtime adapter using manager-style orchestration;
- Xyena Supervisor plus active, domain-neutral Intake, Business, Fraud/Risk, Guardian Explanation,
  and Monitoring specialists as bounded agent tools;
- inactive catalog placeholders for Invoice, Delivery, Payment, Credit, Decision, and Funding agents;
  their demo/domain behavior and tools are deliberately absent;
- every model capability call routed through the MCP broker and Guardian;
- PostgreSQL-backed Agents SDK session protocol (`get_items`, `add_items`, `pop_item`, and
  `clear_session`) with tenant/session/conversation scope;
- bounded context assembly, trusted scope envelope, untrusted-data labeling, token estimation, and
  immutable context snapshots;
- per-user and per-organization governed memory, source metadata, sensitivity, forgetting, optional
  OpenAI embeddings, pgvector storage, and lexical retrieval fallback;
- per-user data-vault object metadata, grants, access events, classifications, hashes, and soft
  deletion;
- migration `0004_context_memory_data`, pgvector, RLS, and seeded agent catalog.

### Phase 5 — production operations

Implemented in the final checkpoint:

- S3-compatible presigned uploads/downloads, tenant/user-generated object keys, required SHA-256
  metadata, server-side encryption headers, completion verification, and audited deletion;
- structured logs, correlation propagation, OpenTelemetry FastAPI/HTTPX/SQLAlchemy tracing, and
  optional OTLP export;
- job lease recovery and transactional outbox delivery to an optional authenticated event webhook;
- one non-root Docker image, Docker Compose for PostgreSQL/pgvector, MinIO, migrations, API, worker,
  MCP, and Guardian;
- Kubernetes base manifests with non-root/read-only containers, probes, resources, private MCP and
  Guardian services, a migration Job, secret template, and ingress network policies;
- Guardian key-generation utility and OpenAPI export for public API, Guardian internal API, and MCP
  control API.

### Post-core checkpoint — reviewed remote MCP and synthetic bank demo

Implemented and pushed after the original five core phases:

- separate MCP review credential, reviewed server/tool activation endpoints, immutable schema-version
  activation, exact egress-host allowlists and HMAC-signed per-user runtime scope;
- isolated `demos/bank-mcp` Python service with OpenAPI 3.1 and MCP v2 Streamable HTTP;
- seven synthetic bank tools for account, balance, transaction, beneficiary and limit evidence plus
  idempotent transfer preparation/status;
- active synthetic consent, tenant/user resource enforcement, audit events, expiring canonical action
  hashes and aggregate preparation limits;
- explicit `execution_available=false` boundary with no real payment or balance mutation capability;
- reviewed registration utility, direct development connection checker and independent Docker Compose;
- responsive light-theme bank operations frontend with dedicated account, transaction, beneficiary,
  prepared-action and MCP-connection pages.

Primary commits: `7a33fc6`, `ac5490c`, `6347582`, and `032c2ed`.

## Apps that should be ready after configuration

| App | Ready capability | Required configuration before use |
|---|---|---|
| `apps/api` | Authenticated sessions, conversations, runs, approvals, memory, and user data APIs | PostgreSQL migration, OIDC issuer/audience, service token, object storage for upload/download |
| `apps/worker` | Agent runs, approval resume, embeddings, durable jobs, outbox, lease recovery | OpenAI API key/model, service token, reachable MCP/Guardian, optional event webhook |
| `apps/mcp_server` | Hosted core MCP, remote registry/discovery, canonical broker and approved resume | Service token, PostgreSQL, Guardian URL, approved server records and secret references |
| `apps/guardian` | Policy decisions, approvals, signed exact-request authorizations | Service token, PostgreSQL, Ed25519 signing and verification keys |
| `apps/web` | Pre-existing web experience only | It must be connected only to `apps/api`; its demo simulation was not built or tested here |
| `demos/bank-mcp` | Synthetic bank evidence, preparation-only tools and operations UI | Separate demo tokens, Xyena service/admin credentials and reviewed MCP registration |

## Mandatory deployment gates

Before calling the deployment production-ready:

1. Provide a PostgreSQL 16 database with `pgvector` and run `alembic upgrade head` using a migration
   identity; application identities should receive only their required schema grants.
2. Configure real OIDC values, disable development auth, rotate a strong workload service token,
   and place credentials in a secret manager.
3. Generate Guardian Ed25519 keys, store the private key only in Guardian, and distribute only the
   public verification key where verification is required. The shared environment template is for
   local orchestration; production should use per-workload secrets.
4. Configure the OpenAI API key and a model supported by the target OpenAI-compatible endpoint.
5. Configure encrypted S3-compatible storage and bucket retention/lifecycle rules.
6. Review and activate every external MCP server, tool schema version, egress host, risk class,
   policy, and agent grant. Discovered tools start pending review.
7. Export/review the OpenAPI documents and run the repository's test, migration, contract, RLS,
   security, and failure-recovery suites in an authorized CI environment. They were not run during
   this build.
8. Replace deployment image placeholders with immutable digests and adapt ingress/network policies
   to the target cluster.

## Deliberately not implemented

- runnable GST/e-Invoice, Delivery, Business Registry, Buyer/ERP, Funder, Ledger or dealer demos;
- real bank, Account Aggregator, payment-rail, lending, portfolio or DeFi integrations;
- payment execution, balance mutation, beneficiary mutation, holds, reversals or real credentials in
  the synthetic bank demo;
- agent/domain implementations for Invoice, Delivery, Payment, Credit, Decision and Funding beyond
  their documented contracts and inactive catalog entries;
- automatic activation of OpenAPI operations or newly discovered MCP tools;
- a claim that tests passed—the instruction for this build explicitly prohibited running tests.
