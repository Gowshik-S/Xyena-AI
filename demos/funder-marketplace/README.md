# XYENA synthetic Funder Marketplace

This folder contains the independent funding marketplace demonstration for Xyena and Guardian. It
stores synthetic funders, versioned programs and deterministic rules, applications, term-sheet
offers, capacity reservations and Guardian-protected commitments. It is not a lender, bank,
payment system or licensed financial marketplace and it never moves money.

## Ready application surfaces

| Page | Purpose |
|---|---|
| `/` | Capital position, underwriting queue and live term-sheet rail |
| `/funders` | Institution directory, settlement rails and policy metadata |
| `/programs` | Program capacity, limits, status and deterministic rule ledger |
| `/applications` | Receivable applications, evidence references and eligibility state |
| `/offers` | Offer inventory and aligned term-sheet comparison |
| `/reservations` | Idempotent amount locks, expiry and release/commit references |
| `/commitments` | Guardian, execution and settlement status |
| `/exposure` | Total, reserved, committed and available program capacity |
| `/activity` | Immutable audit and outbox activity |
| `/mcp-connection` | Reviewed MCP catalog and authority boundary |
| `/docs` | OpenAPI 3.1 API description |
| `/mcp` | Bearer-protected MCP v2 Streamable HTTP endpoint |

The white institutional interface uses graphite, ledger green, restrained brass and rust. Its
signature component is the term-sheet rail, which aligns funder, amount, advance rate, annual rate,
fees, tenor and expiry. There is no purple, neon, gradient or generic AI styling.

## Workflow and authority

```text
Xyena submits case, receivable and evidence receipt references
        ↓
Marketplace evaluates deterministic active program rules
        ↓
Funder reviewer approves or declines the application
        ↓
One or more versioned offers are issued
        ↓
Xyena reserves capacity with an idempotency key and expiry
        ↓
Marketplace prepares exact amount + destination action hash
        ↓
Guardian authorizes the exact action
        ↓
Execution Gateway confirms commitment
        ↓
Bank/Ledger events update disbursement and settlement state
```

A program suspension blocks new reservations and offers but preserves history. Reservation and
commitment changes use database row locking and fixed-precision decimals. The marketplace stores
signed evidence receipt references, not unrestricted source documents.

## Authentication boundaries

- `FUNDER_DEMO_UI_TOKEN` permits read-only browser and dashboard API access.
- `FUNDER_DEMO_OPERATOR_TOKEN` protects reviews, offer issuance, reservations and program state.
- `FUNDER_DEMO_EXECUTION_TOKEN` is required for REST commitment confirmation.
- `FUNDER_DEMO_MCP_TOKEN` authenticates MCP workloads and signs Xyena runtime scope.
- `FUNDER_DEMO_EVENT_SECRET` verifies Bank/Ledger event bytes before processing.
- `If-Match` supplies the expected aggregate version for controlled transitions.

No browser credential is accepted as an MCP, operator or execution credential.

## MCP catalog

| Canonical tool | Policy | Capability |
|---|---|---|
| `funder.programs.search` | Sensitive read | Current deterministic eligibility search |
| `funder.offers.request` | Mutation | Create eligibility-checked application |
| `funder.offers.get` | Sensitive read | Current offer terms, status, expiry and hash |
| `funder.offers.reserve` | Privileged | Idempotent time-bound capacity reservation |
| `funder.reservations.release` | Mutation | Release unused capacity |
| `funder.commitments.prepare` | Privileged | Prepare canonical exact-action proposal |
| `funder.commitments.confirm` | Privileged | Confirm exact Guardian-authorized commitment |
| `funder.exposure.get` | Sensitive read | Marketplace and program exposure view |

All tools require signed tenant/session/run/call scope and are restricted to
`xyena-supervisor`. Confirmation records a marketplace commitment; it does not invoke a bank.

## Data model

The PostgreSQL/SQLAlchemy model includes `funder_institutions`, `funding_programs`,
`program_rules`, `funding_applications`, `funding_offers`, `offer_reservations`,
`funding_commitments`, `audit_events`, `outbox_events` and `inbox_events`. Mutable aggregates carry
tenant scope and versions. Externally visible events use signed, idempotent inbox processing.

## Local setup

Use Python 3.12. From this folder:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
funder-marketplace-demo
```

The local default uses SQLite. Open `http://localhost:8093/` and enter the configured viewer token.
For isolated PostgreSQL deployment:

```powershell
docker compose up --build -d funder-marketplace
```

The database is confined to an internal network. The app also joins `xyena-core_backend`, which
must already exist.

## Register with Xyena and Guardian

Set root `FUNDER_MARKETPLACE_MCP_TOKEN` to the same value as `FUNDER_DEMO_MCP_TOKEN`, configure the
Xyena service/reviewer credentials, then run:

```powershell
docker compose --profile registration run --rm register
```

Registration requires an exact eight-tool discovery match, assigns policy and risk classes, marks
the server reviewed and activates immutable tool versions. Catalog drift stops activation.

## Implemented and intentionally absent

Implemented:

- synthetic PostgreSQL/SQLite data model and deterministic marketplace fixtures;
- deterministic eligibility, reviewer decisions and program lifecycle transitions;
- versioned offers with explicit rate, fee, tenor, conditions, expiry and hash;
- transactional capacity reservations with idempotency and expiry bounds;
- canonical commitment preparation and exact Guardian action-hash confirmation;
- signed Bank/Ledger event inbox for disbursement, failure and settlement reconciliation;
- append-only audit, outbox, OpenAPI 3.1 API and SSE event stream;
- eight Guardian-governed MCP tools;
- professional responsive ten-page white frontend;
- container, PostgreSQL and Xyena registration packaging.

Intentionally absent:

- real funder onboarding, underwriting, bank account or customer data;
- actual credit approval, lending, disbursement, payment or settlement execution;
- production IAM, licensing, regulatory certification or legal enforceability;
- mutable rules controlled by an AI model;
- test-suite execution as part of this delivery.

