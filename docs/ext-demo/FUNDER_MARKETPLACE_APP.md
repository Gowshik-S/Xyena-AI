# Funder Marketplace External Demo Application

## 1. Application identity

```text
Application ID   xyena-demo-funder
Subdomain        funder.demo.xyena.ai
UI               https://funder.demo.xyena.ai/
REST API         https://funder.demo.xyena.ai/api/v1
MCP              https://funder.demo.xyena.ai/mcp
MCP audience     xyena-demo-funder-mcp
```

The Funder Marketplace stores funding programs, eligibility rules, quotes/offers, reservations and funding commitments. It behaves as an external marketplace; XYENA retains aggregate exposure and Guardian governance.

## 2. Users and roles

| Role | Capabilities |
|---|---|
| Marketplace Viewer | view public/eligible programs and offers |
| Funder Operator | manage own programs and review applications |
| Funder Reviewer | approve/decline offers and commitments |
| Marketplace Admin | manage institutions/reference data/scenarios |
| MCP Read Client | discover eligible programs/offers |
| MCP Prepare Client | create/reserve offer under policy |
| Execution Gateway | confirm Guardian-authorized commitment/disbursement reference |

## 3. UI requirements

- dashboard for active programs, submitted applications, offers, reservations and commitments;
- funder institution/profile pages;
- program/rule editor with effective versions;
- application review with evidence receipt references, not raw unrestricted evidence;
- quote/offer comparison and expiry;
- reservation and commitment timeline;
- utilization and exposure view per funder/MSME;
- live event-driven updates.

## 4. State machines

### Funding program

```text
DRAFT → ACTIVE → SUSPENDED → ACTIVE
               └──────────→ CLOSED
```

### Application

```text
RECEIVED → ELIGIBILITY_CHECKED → UNDER_REVIEW → APPROVED/DECLINED
```

### Offer

```text
DRAFT → ISSUED → RESERVED → COMMITTED → DISBURSED → SETTLED
               ├→ EXPIRED
               └→ WITHDRAWN
```

Reservation and commitment use idempotency, expiry and amount locking.

## 5. Data model

### `funder_institutions`

Contains institution ID, legal/display name, type, status, supported currencies/rails, settlement account token, policy metadata and version.

### `funding_programs`

Contains funder, program code/name, product type, currency, min/max amount, advance-rate maximum, tenor range, pricing model, eligible regions/industries, required evidence types, risk/credit limits, effective dates, status and policy version.

### `program_rules`

Versioned deterministic rule JSON/DSL with rule ID, inputs, operator/value, reason code and effective dates. Model-generated text cannot modify active rules.

### `funding_applications`

Contains case/MSME/receivable IDs, requested amount, currency, tenor, evidence receipt references, exposure snapshot reference, status, submitted time and version.

### `funding_offers`

Contains application/funder/program, approved amount, advance rate, rate/fees, tenor, repayment terms, conditions, expiry, status, offer hash and version.

### `offer_reservations`

Contains offer, reserved amount, case/MSME, expiry, idempotency key, status and release/commit references.

### `funding_commitments`

Contains reservation, committed amount, Guardian/action reference, disbursement destination token, status, execution/ledger references and settlement status.

Shared audit/outbox/inbox tables are mandatory.

## 6. REST API

```text
GET    /api/v1/dashboard
GET    /api/v1/funders
POST   /api/v1/funders
GET    /api/v1/programs
POST   /api/v1/programs
PATCH  /api/v1/programs/:id
POST   /api/v1/programs/:id/activate
POST   /api/v1/programs/:id/suspend
GET    /api/v1/applications
GET    /api/v1/applications/:id
POST   /api/v1/applications/:id/review
POST   /api/v1/applications/:id/offers
POST   /api/v1/offers/:id/withdraw
GET    /api/v1/reservations/:id
GET    /api/v1/commitments/:id
GET    /api/v1/events/stream
POST   /mcp
```

## 7. MCP tools

| Tool | Class | Output/action |
|---|---|---|
| `funder.programs.search` | read | eligible active programs and versions |
| `funder.offers.request` | preparation | creates application/offer request, no asset movement |
| `funder.offers.get` | read | current offer terms/status |
| `funder.offers.reserve` | financial preparation | idempotent time-bound reservation |
| `funder.reservations.release` | state change | release unused reservation under policy |
| `funder.commitments.prepare` | preparation | canonical commitment proposal |
| `funder.commitments.confirm` | protected execution | requires Guardian authorization/execution identity |
| `funder.exposure.get` | read | marketplace/funder exposure view |

## 8. Events and live updates

Publishes program, application, offer, reservation, commitment, disbursement and settlement events. Consumes Guardian decisions, Bank/Ledger execution receipts and exposure updates.

- Offer changes/expiry update open UIs through SSE.
- Reservations update available program capacity transactionally.
- MCP reads return current offer/reservation versions.
- A program suspension invalidates new offers but preserves historical commitments.
- Ledger settlement events update commitment status idempotently.

## 9. Validation and security

- funder operators can manage only their institution;
- active rules are deterministic and versioned;
- offer amount cannot exceed program, receivable or supplied eligibility bounds;
- reserve/commit operations use idempotency and row/aggregate locking;
- commitment cannot execute without exact Guardian/action reference;
- evidence is referenced through receipt IDs; raw sensitive documents are not copied into the marketplace.

## 10. Seed scenarios

- multiple eligible offers with different terms;
- no eligible program;
- offer expiry before reservation;
- concurrent reservation capacity race;
- program suspended after offer;
- amount modified after Guardian decision;
- funder exposure limit reached;
- execution failed/unknown then reconciled.

## 11. Acceptance criteria

- users can manage programs and issue/reserve offers through valid workflows;
- current capacities and statuses update live;
- concurrency cannot over-reserve capacity;
- MCP results reflect current terms and versions;
- commitments remain protected by Guardian authorization;
- app deploys independently at `funder.demo.xyena.ai`.

