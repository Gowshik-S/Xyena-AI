# External Demo API and MCP Reference for Xyena Core

**Status:** read-only integration reference  
**Implementation scope:** none of the applications or tools listed here are to be built or tested as part of the Xyena + Guardian core backend

## 1. Why this reference exists

The external demo specifications were inspected to make the Xyena MCP registry, tool policy, OpenAPI contracts, event envelopes, and Guardian boundary capable of supporting future domain servers. They are future consumers of the core architecture, not dependencies required to implement the core.

The reusable requirements found in the demo specifications are:

- each external application owns its REST API, MCP endpoint, database/schema, service audience, credentials, state machine, audit, outbox, and live stream;
- its committed relational state is the source for both REST and MCP;
- browser tokens are not accepted as MCP service credentials;
- service tokens have application-specific audiences and tool scopes;
- MCP results carry schema/source/record versions, freshness timestamps, signatures/hashes, and security labels;
- raw external results pass through Xyena normalization/evidence handling before entering model context;
- read, preparation, state-changing, and protected-execution tools are different capability classes;
- admin scenario/reset endpoints are never exposed as agent MCP tools;
- execution tools require the Execution Gateway and exact Guardian authorization.

## 2. Future external server registrations

| External app | REST base | MCP endpoint | Intended Xyena registration |
|---|---|---|---|
| Business Registry | `https://registry.demo.xyena.ai/api/v1` | `https://registry.demo.xyena.ai/mcp` | read-only registry evidence server |
| GST and e-Invoice | `https://gst.demo.xyena.ai/api/v1` | `https://gst.demo.xyena.ai/mcp` | read-only tax/invoice evidence server |
| Buyer ERP | `https://erp.demo.xyena.ai/api/v1` | `https://erp.demo.xyena.ai/mcp` | read-only operational evidence server |
| Delivery | `https://delivery.demo.xyena.ai/api/v1` | `https://delivery.demo.xyena.ai/mcp` | read-only fulfillment evidence server |
| Bank/AA | `https://bank.demo.xyena.ai/api/v1` | `https://bank.demo.xyena.ai/mcp` | mixed read/prepare/protected server |
| Funder Marketplace | `https://funder.demo.xyena.ai/api/v1` | `https://funder.demo.xyena.ai/mcp` | mixed read/prepare/protected server |
| Ledger/Payment | `https://ledger.demo.xyena.ai/api/v1` | `https://ledger.demo.xyena.ai/mcp` | sensitive/protected execution server |

These endpoints are architecture examples. Core configuration must use environment-specific registrations and secret references, not hardcoded URLs or credentials.

## 3. Future MCP tool catalogue and core risk classification

### 3.1 Business Registry

| Tool | Core risk class |
|---|---|
| `registry.businesses.get` | `SENSITIVE_READ` |
| `registry.businesses.verify` | `SENSITIVE_READ` |
| `registry.businesses.search` | `SENSITIVE_READ` |
| `registry.ownership.get` | `SENSITIVE_READ` |
| `registry.relationships.get` | `SENSITIVE_READ` |
| `registry.authorized_persons.get` | `SENSITIVE_READ` |

### 3.2 GST and e-Invoice

| Tool | Core risk class |
|---|---|
| `gst.taxpayers.get` | `SENSITIVE_READ` |
| `gst.registrations.verify` | `SENSITIVE_READ` |
| `gst.invoices.get` | `SENSITIVE_READ` |
| `gst.invoices.verify` | `SENSITIVE_READ` |
| `gst.invoices.search` | `SENSITIVE_READ` |
| `gst.invoices.check_duplicate` | `SENSITIVE_READ` |
| `gst.returns.get_summary` | `SENSITIVE_READ` |

### 3.3 Buyer ERP

| Tool | Core risk class |
|---|---|
| `erp.counterparties.verify` | `SENSITIVE_READ` |
| `erp.purchase_orders.get` | `SENSITIVE_READ` |
| `erp.purchase_orders.find_by_invoice` | `SENSITIVE_READ` |
| `erp.receipts.get` | `SENSITIVE_READ` |
| `erp.invoice_matches.get` | `SENSITIVE_READ` |
| `erp.invoice_acceptance.get` | `SENSITIVE_READ` |

### 3.4 Delivery

| Tool | Core risk class |
|---|---|
| `delivery.deliveries.get` | `SENSITIVE_READ` |
| `delivery.deliveries.find_by_invoice` | `SENSITIVE_READ` |
| `delivery.deliveries.find_by_po` | `SENSITIVE_READ` |
| `delivery.events.list` | `SENSITIVE_READ` |
| `delivery.proofs.get` | `SENSITIVE_READ` |
| `delivery.acceptance.get` | `SENSITIVE_READ` |
| `delivery.fulfilment.verify` | `SENSITIVE_READ` |

### 3.5 Bank and Account Aggregator

| Tool | Core risk class |
|---|---|
| `bank.aa.create_consent` | `MUTATE` + user verification |
| `bank.aa.get_consent` | `SENSITIVE_READ` |
| `bank.aa.revoke_consent` | `MUTATE` + user verification |
| `bank.aa.fetch_information` | `SENSITIVE_READ` + consent |
| `bank.accounts.list` | `SENSITIVE_READ` |
| `bank.accounts.get` | `SENSITIVE_READ` |
| `bank.accounts.get_balance` | `SENSITIVE_READ` |
| `bank.transactions.list` | `SENSITIVE_READ` |
| `bank.beneficiaries.verify` | `SENSITIVE_READ` |
| `bank.limits.get` | `SENSITIVE_READ` |
| `bank.transfers.prepare` | `MUTATE` / preparation |
| `bank.transfers.execute` | `PRIVILEGED` / exact Guardian authorization |
| `bank.transfers.get_status` | `SENSITIVE_READ` |
| `bank.beneficiaries.prepare_change` | `MUTATE` / preparation |
| `bank.beneficiaries.execute_change` | `PRIVILEGED` / Guardian + reviewer default |
| `bank.reversals.prepare` | `MUTATE` / high-risk preparation |
| `bank.reversals.execute` | `PRIVILEGED` / Guardian + reviewer default |
| `bank.holds.place` | `PRIVILEGED` |
| `bank.holds.release` | `PRIVILEGED` |

### 3.6 Funder Marketplace

| Tool | Core risk class |
|---|---|
| `funder.programs.search` | `SENSITIVE_READ` |
| `funder.offers.request` | `MUTATE` / preparation |
| `funder.offers.get` | `SENSITIVE_READ` |
| `funder.offers.reserve` | `MUTATE` / financial preparation |
| `funder.reservations.release` | `MUTATE` |
| `funder.commitments.prepare` | `MUTATE` / preparation |
| `funder.commitments.confirm` | `PRIVILEGED` / exact Guardian authorization |
| `funder.exposure.get` | `SENSITIVE_READ` |

### 3.7 Ledger and Payment

| Tool | Core risk class |
|---|---|
| `ledger.accounts.get_balance` | `SENSITIVE_READ` |
| `ledger.journals.get` | `SENSITIVE_READ` |
| `ledger.payments.get_status` | `SENSITIVE_READ` |
| `ledger.reconciliation.get` | `SENSITIVE_READ` |
| `ledger.disbursements.prepare` | `MUTATE` / preparation |
| `ledger.disbursements.execute` | `PRIVILEGED` / exact Guardian authorization |
| `ledger.reversals.prepare` | `MUTATE` / high-risk preparation |
| `ledger.reversals.execute` | `PRIVILEGED` / Guardian + reviewer |

These classifications are proposed defaults for the core registry. Activating a server/tool still requires schema review, data classification, consent/purpose rules, server trust review, and policy versioning.

## 4. Data-model implications for Xyena core

The external applications retain their own domain tables. Xyena core stores references and provenance instead of copying their full operational databases.

Core integration records need:

```text
external application/server identity
service audience + allowed tool scopes
external resource type + opaque/tokenized resource ID
tenant/organization/user/case scope
source record version + schema version
updated/retrieved/fresh-until timestamps
request/response/content hashes
source signature verification result
security labels and data classification
safe normalized projection or restricted object reference
correlation ID + tool call ID + evidence/provenance reference
```

Domain entities observed in the demo documents include businesses/ownership, invoices/returns, purchase orders/receipts/matches, deliveries/proofs/acceptance, accounts/transactions/beneficiaries/consents/transfers, programs/offers/reservations/commitments, and ledgers/payments/reconciliations. Those models belong to their domain services. Xyena should not merge all of them into its core schema.

## 5. Shared future MCP response projection

```json
{
  "schema_version": "domain.resource.v1",
  "source_system": "registered-server-label",
  "request_id": "req_...",
  "record_version": 4,
  "updated_at": "2026-08-28T10:28:00Z",
  "retrieved_at": "2026-08-28T10:30:00Z",
  "fresh_until": "2026-08-28T10:35:00Z",
  "data": {},
  "source_signature": "signature-or-reference",
  "security_labels": ["EXTERNAL_DATA"]
}
```

The MCP Gateway validates this external envelope, stores hashes and restricted raw results, and emits a smaller `SafeToolResult` to the model. The external service cannot issue a Xyena Guardian authorization or declare itself trusted merely by returning a field.

## 6. OpenAPI onboarding requirements for future demo servers

Before future registration, each server should provide:

- an OpenAPI 3.1 REST description for operational/admin APIs;
- a separate MCP tool discovery/schema snapshot;
- stable API `operationId` values and MCP tool names;
- explicit authentication audiences/scopes;
- current-state, version, freshness, concurrency, error, idempotency, and event semantics;
- reviewed REST-to-domain-service and MCP-to-domain-service mappings;
- confirmation that admin scenario/reset REST routes are absent from MCP;
- a tool-by-tool data/risk/side-effect/approval classification;
- contract fixtures containing synthetic data only.

## 7. Do-not-build boundary

For the current core implementation:

- do not scaffold these external apps;
- do not connect to their example URLs;
- do not seed their domain data;
- do not invoke or test their tools;
- do not run their API or end-to-end tests;
- do not claim any of them is ready.

Use harmless Xyena core tools to validate the MCP Gateway and Guardian. The catalogue above exists so the core abstractions do not have to be redesigned when domain servers are onboarded later.

## 8. Local source documents reviewed

- `docs/ext-demo/SHARED_PLATFORM_REQUIREMENTS.md`
- `docs/ext-demo/README.md`
- `docs/ext-demo/BUSINESS_REGISTRY_APP.md`
- `docs/ext-demo/GST_EINVOICE_APP.md`
- `docs/ext-demo/BUYER_ERP_APP.md`
- `docs/ext-demo/DELIVERY_APP.md`
- `docs/ext-demo/BANK_AA_APP.md`
- `docs/ext-demo/FUNDER_MARKETPLACE_APP.md`
- `docs/ext-demo/LEDGER_PAYMENT_APP.md`

