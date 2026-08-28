# XYENA synthetic Business Registry

This folder contains the admin-only Business Registry demonstration for Xyena and Guardian. It is
the synthetic authoritative source for business legal identity, registry status, historical names
and addresses, authorized persons, ownership and buyer/seller relationships. It is not the main
Xyena customer portal and it does not connect to MCA, Udyam, GSTN, Aadhaar, PAN or another
government system.

## Who uses it

| User | Responsibility |
|---|---|
| Registry operator | Creates pending records and proposes controlled identity corrections |
| Registry reviewer | Activates, rejects, suspends or dissolves records and decides corrections |
| Xyena Business Agent | Reads versioned identity evidence through Guardian-governed MCP |
| MSME / analyst | Uses the main Xyena portal and sees verification findings, not this admin console |

The application deliberately separates identity record administration from financing case
orchestration. Registry evidence can inform Xyena; it cannot approve a financing case.

## Ready application surfaces

| Page | Purpose |
|---|---|
| `/login` | Separate synthetic operator and reviewer sign-in |
| `/dashboard` | Registry status, review queue, flags and business-type position |
| `/businesses` | Search legal name, registry number, business ID, GSTIN, state and type |
| `/businesses/new` | Operator intake that creates a pending-review record |
| `/business?id=...` | Registry folio with identity, ownership, authority, relationships and history |
| `/change-requests` | Version-bound identity correction review queue |
| `/relationships` | Buyer, seller, group and revoked counterparty evidence |
| `/audit` | Tenant-scoped immutable operational ledger |
| `/mcp-connection` | Human-readable Xyena/Guardian authority boundary and tool catalog |
| `/docs` | OpenAPI 3.1 browser and workflow API |
| `/mcp` | Bearer-protected MCP v2 Streamable HTTP endpoint |

The professional light interface is designed as a records office, using security-paper white,
mineral blue, archival green and seal red. Its signature registry folio keeps legal status,
registry number, version and source hash together. It contains no neon, purple or generic AI
visual treatment.

## Workflows and integrity

```text
Operator creates pending identity
        ↓
Reviewer activates or rejects it
        ↓
Operator proposes a version-bound correction
        ↓
Reviewer approves or rejects the correction
        ↓
Approved data becomes a new business version
        ↓
Audit/outbox commit and MCP reads expose the current version
```

- Browser sessions are opaque, HTTP-only and CSRF protected.
- Mutations enforce operator/reviewer roles and optimistic `If-Match` versions.
- Approved legal-name and address changes append historical name/address records.
- Business status follows `PENDING_REVIEW → ACTIVE/REJECTED`,
  `ACTIVE → SUSPENDED/DISSOLVED`, and `SUSPENDED → ACTIVE/DISSOLVED`.
- Audit and outbox records commit in the same transaction as domain changes.
- All identities, person tokens, PAN tokens, GSTINs and relationships are synthetic.

## Synthetic accounts and shared fixtures

Configure the role-specific passwords in `.env`:

| Account | Role |
|---|---|
| `operator@registry.demo.xyena.test` | Registry Viewer + Operator |
| `reviewer@registry.demo.xyena.test` | Registry Viewer + Reviewer |

Tenant: `00000000-0000-4000-8000-000000001301`

The Kaveri fixture reuses business/enterprise ID
`00000000-0000-4000-8000-000000001201`, business ID `biz_gst_micro_01` and GSTIN
`29ABCDE1234F1Z5` so Registry, GST and downstream Xyena evidence can be correlated without one app
overwriting another app’s records.

## MCP catalog

The registration utility installs exactly six read-only tools as `SENSITIVE_READ`,
`approval_mode=POLICY`, limited to `xyena-supervisor`, which delegates the evidence to the Business
Agent within the governed Xyena run:

| Canonical name | Evidence |
|---|---|
| `registry.businesses.get` | Current identity, legal status, version and history |
| `registry.businesses.verify` | Deterministic comparison with claimed legal name/GSTIN/status |
| `registry.businesses.search` | Bounded tenant-scoped candidate list |
| `registry.ownership.get` | Verified owner tokens and percentages |
| `registry.relationships.get` | Buyer, seller, group and service-provider relationships |
| `registry.authorized_persons.get` | Tokenized currently authorized persons and roles |

Every result includes record version, source hash, source signature, freshness and security labels.
The MCP surface cannot create, correct, activate, suspend or dissolve a business.

## Local setup

Use Python 3.12. From this folder:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
business-registry-demo
```

The local default uses SQLite. Open `http://localhost:8093/login`. The shared deployment uses the
isolated PostgreSQL service:

```powershell
docker compose up --build -d business-registry
```

## Connect to Xyena and Guardian

Set root `REGISTRY_DEMO_MCP_TOKEN` to the same high-entropy value as this application. Configure the
Xyena service token and distinct MCP admin review token, then run:

```powershell
docker compose --profile registration run --rm register
```

Registration creates or reuses the tenant-local `registry` server, discovers the remote catalog,
requires an exact six-tool match, marks it reviewed and activates immutable tool versions under
Guardian policy. Unexpected tool or schema drift stops activation.

## Implemented and intentionally absent

Implemented and ready:

- isolated SQLite/PostgreSQL registry model and deterministic synthetic attack/normal scenarios;
- operator/reviewer browser sessions, role checks, CSRF and optimistic concurrency;
- business status and version-bound correction workflows;
- historical names/addresses, people, ownership and relationship evidence;
- audit, transactional outbox and live SSE updates;
- professional responsive multi-page light administration frontend;
- OpenAPI 3.1 REST API and six read-only signed-scope MCP tools;
- reviewed Xyena/Guardian registration utility and container packaging.

Intentionally absent:

- a second MSME/customer financing portal;
- real MCA, Udyam, GSTN, Aadhaar, PAN or personal identity integration;
- payment, lending, financing approval or fund movement;
- mutable MCP tools or autonomous registry decisions;
- production IAM, certification or regulatory claims.
