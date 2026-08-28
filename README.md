# Xyena Enterprise AI

This is the new working directory for the enterprise XYENA implementation.

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

## Planned system areas

- `apps/api` - application API and orchestration entry point.
- `apps/mcp-server` - MCP tool servers and secured tool exposure.
- `packages/agents` - specialized XYENA agents and Guardian.
- `packages/context` - tenant, user, MSME, case, session, and evidence context assembly.
- `packages/evidence` - untrusted-content isolation, schema projection, signed evidence receipts, and completeness/consistency policy.
- `packages/memory` - isolated user memory, MSME organizational memory, case memory, and retrieval policies.
- `packages/tools` - typed internal tools and MCP client adapters.
- `packages/contracts` - shared schemas for context, memory, agent findings, tool calls, and decisions.
- `tests` - unit, integration, isolation, security, and scenario tests.
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
