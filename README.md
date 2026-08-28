# Xyena Enterprise AI

This repository contains the core Xyena multi-agent backend and its independent Guardian
authorization plane. The backend is Python 3.12, FastAPI, PostgreSQL/pgvector, OpenAPI 3.1, the
OpenAI Agents SDK, and MCP v2 Streamable HTTP.

## Implemented backend

- `apps/api` — public authenticated sessions, conversations, runs, approvals, memory, and data API;
- `apps/worker` — durable Xyena agent runs, approval resume, embeddings, outbox, and recovery;
- `apps/mcp_server` — hosted MCP, remote discovery/registry, schema validation, and tool broker;
- `apps/guardian` — independent policy, approvals, and exact-request single-use authorization;
- `migrations/versions` — IAM through data-vault schemas with PostgreSQL tenant RLS;
- `deploy` and `compose.yaml` — production-oriented container and Kubernetes packaging.

See [implementation status](./docs/backend-architecture/IMPLEMENTATION_STATUS.md) for delivered
phases, configuration gates, and explicit exclusions.

No GST, banking, lending, dealer, payment, funding, or other demo backend was built or tested.

## Local core stack

Copy `.env.example` to `.env`, set all required secrets (including PostgreSQL/MinIO variables used
by Compose), generate Guardian keys with `python scripts/generate_guardian_keys.py`, then use:

```powershell
docker compose up --build
```

The public API is exposed on `http://localhost:8080`. MCP is bound to localhost on port `8081` and
requires the service bearer token. Guardian is private to the backend network.

## Architecture

- [Xyena + Guardian core backend architecture](./docs/backend-architecture/README.md)
- [OpenAPI 3.1 and MCP contract plan](./docs/backend-architecture/OPENAPI_AND_MCP_CONTRACTS.md)
- [External demo MCP integration reference (read-only)](./docs/backend-architecture/EXTERNAL_DEMO_MCP_REFERENCE.md)
- [Enterprise architecture](./docs/ENTERPRISE_ARCHITECTURE.md)
- [Shareable enterprise architecture diagram](./docs/xyena-enterprise-architecture.svg)
- [Shareable enterprise architecture PNG](./docs/xyena-enterprise-architecture.png)
- [Validated Mermaid architecture source](./docs/xyena-enterprise-architecture.mmd)
- [Compiled Mermaid SVG](./docs/xyena-enterprise-mermaid.svg)
- [Compiled Mermaid PNG](./docs/xyena-enterprise-mermaid.png)
- [Original XYENA architecture](./docs/ARCHITECTURE.md)
- [Financial domain MCP and adapter architecture](./docs/FINANCIAL_DOMAIN_ADAPTERS.md)
- [Bank MCP server specification](./docs/BANK_MCP.md)
- [Bank MCP configuration guide](./docs/BANK_MCP_CONFIG.md)
- [Demo GST and Delivery platform specification](./docs/DEMO_GST_DELIVERY_PLATFORM.md)
- [External live demo application suite](./docs/ext-demo/README.md)
- [Per-agent documentation](./docs/agents/README.md)

## Web mockup

The professional React landing page is located in `apps/web`.

The live architecture control room is available at `/architecture-live`. It simulates one documented financing case across identity, evidence trust, isolated context and memory, specialist agents, MCP tools, exposure control, Guardian authorization, protected execution, and monitoring.

```powershell
cd "apps/web"
npm install
npm run dev
```

Create a production build with:

```powershell
npm run build
```

The landing page uses a maroon, dark navy, white, and neutral palette, SVG-only visuals, Lenis smooth scrolling, and intersection-based text reveal motion.

## Core system areas

- `apps/api` - application API and orchestration entry point.
- `apps/mcp_server` - MCP server and secured tool exposure.
- `apps/guardian` - independent deterministic authorization service.
- `packages/agents` - Xyena supervisor and active domain-neutral specialists.
- `packages/context` - tenant, user, MSME, case, session, and evidence context assembly.
- `packages/evidence` - untrusted-content isolation, schema projection, signed evidence receipts, and completeness/consistency policy.
- `packages/memory` - isolated user memory, MSME organizational memory, case memory, and retrieval policies.
- `packages/tools` - typed internal tools and MCP client adapters.
- `packages/contracts` - shared schemas for context, memory, agent findings, tool calls, and decisions.
- `tests` - reserved for unit, integration, isolation, security, and scenario tests.
- `docs` - copied source brief, problem statement, architecture, and shareable diagram.

## Context isolation key

Every context item, memory item, agent run, and tool call will be scoped by:

```text
tenant_id
  +-- msme_id
       +-- user_id
       +-- case_id
       +-- session_id
```

Guardian remains the authorization boundary for financially consequential tool calls. MCP standardizes tool discovery and invocation; it does not replace XYENA identity, mandate, provenance, policy, or risk checks.
