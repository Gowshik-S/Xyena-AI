# XYENA Ledger and Payment Operations

This independent synthetic service provides immutable double-entry journals, payment instruction
state, Bank settlement ingestion and reconciliation for Xyena and Guardian.

## Ready surfaces

| Page | Purpose |
|---|---|
| `/` | Balanced-book overview and invariant strip |
| `/accounts` | Chart of accounts, normal side, balance and version |
| `/journals` | Journal/case register with equal debit and credit totals |
| `/payments` | Payment lifecycle and 10-character bank references |
| `/reconciliation` | Journal ↔ payment ↔ settlement match |
| `/mcp-connection` | Eight reviewed tools and signed scope |
| `/docs` | OpenAPI 3.1 contract |
| `/mcp` | Bearer-protected MCP v2 endpoint |

The paper-white and graphite UI uses clearing blue, reconciliation green and exception amber. Its
signature component is a paired debit/credit posting tape. There are no payment or journal-posting
buttons in the browser.

## Accounting and execution invariants

- Debits equal credits before a journal can move beyond validation.
- Posting the lines, versioned balances, audit and outbox occurs in one database transaction.
- Posted journals are never edited; a reversal is a linked compensating journal.
- A Guardian call ID and idempotency key cannot post twice or drift to other parameters.
- Disbursement execution uses `approval_mode=ALWAYS`.
- Reversal execution requires both a reviewer approval ID and Guardian authorization.
- Unknown bank outcomes are reconciled before another execution attempt.
- Settlement event IDs are single-use and payload-hash bound.

## MCP catalog

```text
ledger.accounts.get_balance       ledger.journals.get
ledger.payments.get_status        ledger.reconciliation.get
ledger.disbursements.prepare      ledger.disbursements.execute
ledger.reversals.prepare          ledger.reversals.execute
```

`ledger.disbursements.execute` posts the balanced journal and returns the exact prepared Bank
execution request. The Bank executes separately through its own Guardian-protected MCP tool. Its
settlement event enters `POST /internal/v1/bank-settlements`, creates an immutable receipt and
marks reconciliation `MATCHED` only when payment, execution, amount and currency agree.

## Run and register

Copy `.env.example` to `.env`, set long random MCP/UI/settlement secrets, install with
`python -m pip install -e .`, and run `ledger-payment-demo`. The default local database is SQLite;
the supplied PostgreSQL URL uses `asyncpg`. Run `ledger-payment-register` to discover, verify and
activate the exact eight-tool catalog.

The governed cross-service coordinator and stable fixture are in [../e2e/README.md](../e2e/README.md).
