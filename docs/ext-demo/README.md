# XYENA External Demo Application Suite

## Purpose

The external demo suite is a collection of independently deployed, database-backed applications that behave like real operational systems during the XYENA demonstration.

They are not static mockups. When an authorized user or workflow creates, edits, cancels, approves, dispatches, pays, or reconciles a record:

1. the application writes the change to its database;
2. an immutable audit entry and outbox event are created in the same transaction;
3. connected browser screens receive the change through SSE or WebSocket updates;
4. MCP reads immediately return the current committed version;
5. subscribed external applications receive an idempotent event/webhook;
6. XYENA records new evidence receipts and reevaluates affected findings or Guardian posture.

The applications use synthetic demo identities and transactions, but their workflows, state transitions, validations, authorization, audit, concurrency, integration, and failure handling should operate like a real application.

## Applications

| Application | Subdomain | Specification | Primary MCP server |
|---|---|---|---|
| Business Registry | `registry.demo.xyena.ai` | [BUSINESS_REGISTRY_APP.md](./BUSINESS_REGISTRY_APP.md) | Registry/Supply MCP |
| GST and e-Invoice | `gst.demo.xyena.ai` | [GST_EINVOICE_APP.md](./GST_EINVOICE_APP.md) | GST/Supply MCP |
| Buyer and ERP | `erp.demo.xyena.ai` | [BUYER_ERP_APP.md](./BUYER_ERP_APP.md) | ERP/Supply MCP |
| Delivery and Fulfilment | `delivery.demo.xyena.ai` | [DELIVERY_APP.md](./DELIVERY_APP.md) | Delivery/Supply MCP |
| Bank and Account Aggregator | `bank.demo.xyena.ai` | [BANK_AA_APP.md](./BANK_AA_APP.md) · [implementation](../../demos/bank-mcp/README.md) | Bank MCP |
| Funder Marketplace | `funder.demo.xyena.ai` | [FUNDER_MARKETPLACE_APP.md](./FUNDER_MARKETPLACE_APP.md) | Funder/Supply MCP |
| Ledger and Payment Operations | `ledger.demo.xyena.ai` | [LEDGER_PAYMENT_APP.md](./LEDGER_PAYMENT_APP.md) · [implementation](../../demos/ledger-payment/README.md) | Bank/Ledger MCP |

Shared runtime, data, event, identity, deployment, and MCP requirements are defined in [SHARED_PLATFORM_REQUIREMENTS.md](./SHARED_PLATFORM_REQUIREMENTS.md).

## System topology

```text
                                  ┌─────────────────────────┐
                                  │ app.demo.xyena.ai       │
                                  │ XYENA agents + Guardian │
                                  └────────────┬────────────┘
                                               │ Central MCP Gateway
          ┌────────────────────────────────────┼─────────────────────────────────────┐
          │                 │                  │                 │                   │
registry.demo          gst.demo           erp.demo        delivery.demo         bank.demo
          │                 │                  │                 │                   │
          └─────────────────┴──────────────────┴─────────────────┴───────────────────┘
                                               │
                                funder.demo ───┴─── ledger.demo
```

Every subdomain owns its own:

- UI and application API;
- MCP endpoint;
- relational data store or isolated database/schema;
- service audience and credentials;
- state machine and business rules;
- audit and outbox tables;
- live-update stream;
- deployment and health checks.

## End-to-end demo lifecycle

```text
1. Registry app creates/updates MSME and buyer profiles
2. ERP app creates purchase order and confirms seller relationship
3. GST app registers invoice and IRN
4. Delivery app dispatches and records fulfilment/POD
5. Bank/AA app exposes consented account and payment evidence
6. XYENA agents verify evidence and calculate eligible financing
7. Funder app returns offers and reserves the selected offer
8. Guardian authorizes the exact disbursement
9. Ledger/Payment app executes and posts balanced entries
10. Bank app and Ledger app reconcile settlement
11. Every UI and MCP read reflects the new committed state
```

## Shared identifiers

These identifiers must remain stable across applications:

```text
tenant_id
msme_id
business_id
seller_gstin
buyer_id
buyer_gstin
purchase_order_id
invoice_id
invoice_number
irn
delivery_id
account_token
beneficiary_token
financing_case_id
offer_id
proposed_action_id
guardian_decision_id
execution_id
ledger_transaction_id
correlation_id
```

Applications store foreign-system identifiers as references. They do not overwrite records owned by another application.

## Completion standard

An application is complete only when it has:

- persistent database migrations;
- create, read, update and domain-specific state-transition workflows;
- optimistic concurrency/version handling;
- role-based screens and APIs;
- current-state MCP tools;
- audit and outbox events written transactionally;
- live UI refresh after committed updates;
- idempotent inbound event handling;
- health, readiness, metrics and structured logging;
- seeded normal and attack scenarios;
- unit, contract, integration and end-to-end tests;
- containerized deployment on its assigned subdomain.

## Non-production boundary

These are functional demonstration applications, not licensed financial, government, tax, banking, brokerage, custody, or payment systems. All data and credentials must remain synthetic. The UIs must visibly identify themselves as XYENA demonstration systems.

