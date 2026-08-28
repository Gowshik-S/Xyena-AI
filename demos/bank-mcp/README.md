# XYENA Bank and Account Aggregator

This independent FastAPI/PostgreSQL-compatible demo supplies a complete synthetic bank, payment
operations and Account Aggregator boundary to Xyena. It never connects to a real bank, AA,
beneficiary or payment rail.

## Ready surfaces

| Surface | Purpose |
|---|---|
| `/` | Bank operations summary |
| `/accounts` | Tokenized accounts and balances |
| `/transactions` | Consented transaction evidence |
| `/beneficiaries` | Masked beneficiary verification |
| `/account-aggregator` | Consent and FI-request register |
| `/payment-operations` | Settlements, references and holds |
| `/prepared-actions` | Canonical exact-action proposals |
| `/mcp-connection` | 19-tool reviewed MCP catalog |
| `/docs` | OpenAPI 3.1 contract |
| `/mcp` | Bearer-protected MCP v2 endpoint |

The light operations interface uses paper white, navy, ledger green and restrained amber. It has
no purple, neon, gradient or generic AI styling. Browser APIs are read-only; payment execution is
not exposed as a browser control.

## Security and state model

```text
Xyena agent → MCP broker → Guardian decision + single-use consume
                              ↓
                  HMAC-signed remote runtime envelope
                              ↓
Bank rechecks action hash, expiry, beneficiary, balance and limits
                              ↓
account + transaction + execution + audit + outbox commit together
```

AA consent is separate from payment authority. Consents are account-, purpose-, information-type-
and time-scoped and revocable. FI fetches are idempotent and return evidence receipts. Side-effect
tools uniquely persist the Guardian call ID and reject action-hash or parameter drift. Unknown
results must be reconciled and are never blindly retried.

Transfers produce random-looking 10-character synthetic references. Holds adjust available rather
than current balance. Reversals require reviewer approval plus Guardian and create a compensating
credit transaction. PostgreSQL is supported with `asyncpg`; SQLite remains the local default.

## MCP catalog

```text
bank.aa.create_consent              bank.aa.get_consent
bank.aa.revoke_consent              bank.aa.fetch_information
bank.accounts.list                  bank.accounts.get
bank.accounts.get_balance           bank.transactions.list
bank.beneficiaries.verify           bank.limits.get
bank.transfers.prepare              bank.transfers.execute
bank.transfers.get_status           bank.beneficiaries.prepare_change
bank.beneficiaries.execute_change   bank.reversals.prepare
bank.reversals.execute              bank.holds.place
bank.holds.release
```

Privileged execution tools use `approval_mode=ALWAYS`, are restricted to `xyena-supervisor`, and
can run only after Guardian admits the exact central-broker call.

## Stable synthetic fixture

```text
tenant_id       00000000-0000-4000-8000-000000000101
organization_id 00000000-0000-4000-8000-000000000301
user_id         00000000-0000-4000-8000-000000000201
account         acct_demo_operating
beneficiary     ben_demo_verified
aa consent      aac_demo_active
currency/rail   INR / DEMO_BANK_RAIL
```

## Run and register

From this directory, copy `.env.example` to `.env`, use long random secrets, install with
`python -m pip install -e .`, then run `bank-mcp-demo`. Register the exact catalog with
`bank-mcp-register`. Registration fails on missing or unexpected tools and marks execution tools
as always-approval privileged actions.

## Implemented boundary

Implemented: persistent synthetic accounts, transactions, beneficiaries, AA consents, FI requests,
transfer prepare/execute/status, beneficiary changes, holds, reviewer-approved reversals, exact
hashes, replay/idempotency controls, audit/outbox records, OpenAPI, MCP and multi-page UI.

Not included: real credentials, money, regulated AA connectivity, core-banking integration, GST,
lending, brokerage, wallet, portfolio or DeFi behavior.
