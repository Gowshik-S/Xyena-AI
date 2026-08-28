# OpenAPI 3.1 and MCP Contract Plan

This document defines how Xyena's Python/FastAPI APIs, shared Pydantic models, agent tools, and MCP servers remain compatible without confusing REST with MCP.

## 1. Version decision

- Xyena targets the **OpenAPI 3.1 feature set**.
- FastAPI-generated documents use `openapi: 3.1.0` for broad tooling compatibility.
- CI validates behavior against the current OpenAPI 3.1.x specification clarifications. OpenAPI patch releases clarify the same 3.1 feature set and are not Xyena API versions.
- Each API has its own semantic `info.version`, starting at `1.0.0`.
- Schemas use JSON Schema 2020-12 semantics supported by OpenAPI 3.1 and Pydantic v2.
- A move to OpenAPI 3.2 is a separate architecture decision after the required generators, validators, gateway, and client tooling support it.

## 2. Contract ownership

```text
Pydantic domain/DTO model
    ├── FastAPI request/response model
    ├── OpenAPI component schema
    ├── MCP tool input/output schema
    ├── event/webhook schema
    └── persisted schema/version hash
```

One Python type may be reused only when its exposure is actually identical. Do not return database ORM models or reuse an internal record with secret/admin fields as a public DTO. Use explicit projections such as `UserPrivateView`, `UserAdminView`, and `UserAgentSafeView`.

## 3. OpenAPI artifact layout

```text
openapi/
  source/                         optional hand-authored overlays
  generated/
    xyena-public-v1.json
    guardian-internal-v1.json
    mcp-control-internal-v1.json
    webhooks-v1.json
  bundled/
    xyena-public-v1.yaml
    guardian-internal-v1.yaml
    mcp-control-internal-v1.yaml
    webhooks-v1.yaml
  snapshots/                      reviewed release baselines
```

Generated artifacts are deterministic. CI fails when generated output differs from committed output, a schema is invalid, an `operationId` is duplicated, or a breaking change lacks an approved API-version decision.

## 4. Naming and URL rules

| Item | Rule | Example |
|---|---|---|
| Public base path | `/api/v{major}` | `/api/v1` |
| Resource path | plural nouns, kebab-case | `/data-connections` |
| Path parameter | snake_case in braces | `{conversation_id}` |
| `operationId` | stable domain action; unique across document | `conversations_create` |
| Schema name | PascalCase | `ConversationCreateRequest` |
| JSON property | snake_case | `correlation_id` |
| MCP tool | domain.resource.verb | `xyena.memory.search` |
| Event type | domain.entity.past-tense | `conversation.message.created` |
| Error code | stable uppercase identifier | `SCOPE_MISMATCH` |

Changing a Python handler name must not change its `operationId`. Renaming an `operationId`, response property, enum value, or MCP tool is treated as a contract change.

## 5. Standard HTTP contracts

### 5.1 Headers

| Header | Direction | Use |
|---|---|---|
| `Authorization` | request | OIDC bearer token or service token |
| `X-Correlation-ID` | both | caller-supplied or server-generated traceable ID |
| `Idempotency-Key` | request | required on retryable externally visible mutations |
| `ETag` | response | current resource version/hash |
| `If-Match` | request | required on optimistic-concurrency updates |
| `Retry-After` | response | rate limit or dependency recovery guidance |
| `Last-Event-ID` | request | resume SSE stream |

Tenant, organization, user, agent, and case identity are resolved from authenticated claims and server state. Public clients must not be trusted merely because they supplied scope headers.

### 5.2 Error shape

Use `application/problem+json`:

```json
{
  "type": "https://docs.xyena.ai/problems/scope-mismatch",
  "title": "Scope mismatch",
  "status": 403,
  "detail": "The requested resource is not available in the authenticated scope.",
  "instance": "/api/v1/conversations/019...",
  "code": "SCOPE_MISMATCH",
  "correlation_id": "019...",
  "errors": []
}
```

Do not include stack traces, raw provider errors, tool credentials, sensitive arguments, or cross-tenant existence information.

### 5.3 Pagination

Use opaque cursor pagination for messages, events, audit, tool calls, and memories:

```json
{
  "items": [],
  "next_cursor": "opaque-or-null",
  "has_more": false
}
```

Cursor contents are signed/encrypted or server-side. They bind filters and tenant scope.

### 5.4 Money, dates, and identifiers

- IDs are UUID strings; no sequential database ID is public.
- Timestamps are RFC 3339 UTC strings.
- Money is an object with decimal string and ISO currency; never JSON floating point.
- Hashes include algorithm metadata when ambiguity is possible.
- Unknown JSON fields are rejected on commands and reviewed tool inputs unless a contract explicitly permits extensions.

## 6. Security schemes

The public API OpenAPI document declares OIDC/OAuth security. Internal documents separately declare service OAuth audiences and optional mTLS. These descriptions support client generation and documentation but do not enforce access by themselves.

Operation security is deny-by-default:

- public user operation: user bearer token + server-side scope resolution;
- reviewer operation: bearer token + reviewer role + resource policy;
- internal service operation: service token with exact audience/scope, optionally mTLS;
- `/mcp`: MCP service authentication and tool scopes, never a browser session token;
- health liveness: no sensitive dependency details;
- readiness and metrics: network/service authorization policy.

## 7. OpenAPI to MCP relationship

REST and MCP can call the same application service but they are different protocol surfaces:

```text
REST operation --------------------┐
                                   v
                              Application service -> repository
                                   ^
MCP tool -> ToolBroker -> Guardian-┘
```

Rules:

1. Never turn the entire OpenAPI document into tools automatically.
2. Every MCP tool has an explicit manifest entry referencing an internal handler and, optionally, a related OpenAPI `operationId`.
3. The MCP schema is narrowed for agent use: only fields the model may choose are present.
4. Trusted scope, credentials, policy version, and authorization are injected outside the tool schema.
5. REST admin/scenario/reset endpoints are never agent tools.
6. A REST write permission does not imply an MCP tool permission, and the reverse is also true.
7. MCP read results contain record version, update/retrieval time, freshness, source identity, and security labels.
8. Protected MCP tools additionally require Guardian authorization bound to the canonical call hash.

## 8. Tool mapping manifest

The database is authoritative at runtime, while a reviewed manifest seeds/migrates it:

```yaml
tool: xyena.memory.search
server: xyena-core
handler: memory.search
related_operation_id: memories_search
risk_class: SENSITIVE_READ
side_effects: false
idempotent: true
hosted_mcp_allowed: false
input_schema: XyenaMemorySearchInput
output_schema: XyenaMemorySearchResult
required_purposes:
  - assist_current_user
required_data_classes:
  - USER_MEMORY
guardian_policy: delegated_sensitive_read_v1
```

Schema hashes, manifest version, reviewer, and activation time are persisted as `mcp.tool_versions` and `mcp.tool_policies`.

## 9. FastAPI generation rules

- Configure title, description, terms, contact, semantic version, and OpenAPI URL explicitly.
- Assign every route an explicit `operation_id`, response model, response status, tags, and error responses.
- Use Pydantic discriminated unions for versioned events and run stream items.
- Declare `additionalProperties: false` where closed command/tool schemas are intended.
- Exclude internal debugging routes and the raw MCP transport from the public OpenAPI document.
- Generate separate documents by app/security boundary rather than publishing one giant specification.
- Add reviewed `x-xyena-*` annotations only where tooling consumes them:
  - `x-xyena-capability`;
  - `x-xyena-risk-class`;
  - `x-xyena-data-classification`;
  - `x-xyena-idempotency`;
  - `x-xyena-guardian-policy`.

Vendor extensions are documentation/automation metadata, not enforcement. Runtime values come from the signed/versioned tool and policy registry.

## 10. Streaming, events, and webhooks

- Conversation/run UI updates use authenticated SSE under `/api/v1/runs/{run_id}/events`.
- SSE events have an ID, name, version, timestamp, correlation ID, resource reference, and minimal data.
- Reconnect uses `Last-Event-ID`; old events are replayed from durable event storage within retention.
- External callbacks use signed/idempotent webhooks described in the OpenAPI `webhooks` section or a separate webhook document.
- Webhook receivers validate issuer, audience, signature, timestamp, tenant, event ID, schema version, and replay window.
- Event consumers use an inbox unique key `(source_application, event_id)`.

## 11. Compatibility policy

Non-breaking within `/api/v1`:

- add optional response fields when clients are configured to tolerate them;
- add new endpoints and optional request fields;
- add new event types only when subscribers are required to ignore unknown types;
- add a new MCP tool version without activating it for existing agents.

Breaking:

- remove/rename fields or operations;
- make optional input required;
- change meaning/type/format;
- narrow accepted enum values or add response enum values to clients that exhaustively parse them;
- change `operationId`, authentication, idempotency, or side-effect semantics;
- change an MCP schema or risk class in place.

Breaking REST changes require a new API major version or an explicit migration window. MCP changes always create a new immutable `tool_version`; agent grants choose when to adopt it.

## 12. CI release gates

1. Generate OpenAPI from the Python app without starting external/demo services.
2. Bundle references and validate the OpenAPI 3.1 document.
3. Run lint rules for operation IDs, errors, security, pagination, examples, and forbidden sensitive fields.
4. Diff against the last release and block unapproved breaking changes.
5. Generate the TypeScript client for `apps/web` and compile it.
6. Generate/validate JSON Schema for MCP inputs and outputs.
7. Compare registered MCP tool schema hashes with reviewed manifests.
8. Run public/internal API contract tests plus MCP contract tests using harmless core fixtures.
9. Publish versioned artifacts with the application build.

No GST, bank, payment, funding, ledger, or other demo service is required or permitted in this core contract pipeline.

## 13. Minimal OpenAPI skeleton

```yaml
openapi: 3.1.0
info:
  title: Xyena Core API
  version: 1.0.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
servers:
  - url: https://api.xyena.ai
security:
  - oidc: []
paths:
  /api/v1/sessions:
    post:
      operationId: sessions_create
      tags: [Sessions]
      x-xyena-capability: session:create
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SessionCreateRequest'
      responses:
        '201':
          description: Session created
          headers:
            X-Correlation-ID:
              $ref: '#/components/headers/CorrelationId'
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Session'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '422':
          $ref: '#/components/responses/ValidationProblem'
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://identity.xyena.ai/.well-known/openid-configuration
  schemas: {}
  headers: {}
  responses: {}
```

The production identity URL is environment-specific and must not be hardcoded into reusable client logic.

## 14. Primary reference

- [OpenAPI Specification 3.1.2](https://spec.openapis.org/oas/v3.1.2.html)

