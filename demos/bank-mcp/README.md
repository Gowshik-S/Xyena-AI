# XYENA synthetic bank MCP demo

This folder is an isolated, database-backed demonstration bank connected to the Xyena MCP
Gateway. Every record is synthetic. The service does **not** connect to a real bank, Account
Aggregator, payment rail, credential, account, beneficiary, or source of funds.

Its financial boundary is deliberate: tools can read synthetic evidence and prepare a canonical
transfer proposal, but no tool can execute a payment, alter a beneficiary, place a hold, reverse a
transaction, or change an account balance.

## What is included

- FastAPI application and OpenAPI 3.1 description at `/docs` and `/openapi.json`;
- MCP v2 Streamable HTTP endpoint at `/mcp`;
- bearer authentication for MCP and separate token authentication for the dashboard API;
- HMAC-signed Xyena runtime scope on every tool call;
- tenant, user, consent, purpose, account, and beneficiary enforcement;
- SQLite persistence with deterministic synthetic seed data;
- an audit event for each successful scoped operation;
- an idempotent, expiring transfer-preparation record and canonical action hash;
- a registration utility that performs discovery, reviewed activation, and policy activation through
  the Xyena control API;
- a responsive light-theme operations frontend at `/` that visibly labels all data as synthetic.

The frontend source is kept separately in `frontend/`. It uses a restrained financial-operations
palette (paper white, ink, navy, green, and amber), system typography, and no neon, purple, gradient,
or generated-art styling. It has no Node.js or external browser dependency and is served by FastAPI.

## Architecture and trust path

```text
Xyena supervisor
  -> Xyena MCP broker
     -> registered tool policy + Guardian evaluation
        -> bearer-authenticated MCP v2 request
           -> HMAC-signed tenant/user/session/run/call/purpose scope
              -> synthetic bank consent and resource checks
                 -> evidence result or prepared-action hash
```

The bearer token authenticates the gateway workload. The signed MCP request `_meta` binds the
effective tenant, organization, user, session, run, call, agent, tool name, purpose, and canonical
request hash. The bank demo rejects direct MCP tool calls that do not have a valid signature.

## Tool catalog

| Canonical Xyena name | Demo MCP name | Risk | Capability |
|---|---|---|---|
| `bank.accounts.list` | `accounts.list` | `SENSITIVE_READ` | Scoped tokenized account list |
| `bank.accounts.get_balance` | `accounts.get_balance` | `SENSITIVE_READ` | Synthetic balance evidence |
| `bank.transactions.list` | `transactions.list` | `SENSITIVE_READ` | Maximum 90-day transaction window |
| `bank.beneficiaries.verify` | `beneficiaries.verify` | `SENSITIVE_READ` | Synthetic verification evidence |
| `bank.limits.get` | `limits.get` | `SENSITIVE_READ` | Limits and disabled-execution signal |
| `bank.transfers.prepare` | `transfers.prepare` | `MUTATE` | Idempotent proposal only |
| `bank.transfers.get_status` | `transfers.get_status` | `SENSITIVE_READ` | Prepared proposal status |

All seven tools use `approval_mode=POLICY`, are restricted to `xyena-supervisor`, and pass through
Guardian because no bank capability is classified as an ordinary public read.

## Synthetic scope and fixtures

The seed data is intentionally fixed so the Xyena session used for a demo can be created in the
same scope:

```text
tenant_id       00000000-0000-4000-8000-000000000101
organization_id 00000000-0000-4000-8000-000000000301
user_id         00000000-0000-4000-8000-000000000201
account         acct_demo_operating
beneficiary     ben_demo_verified
consent         consent_demo_active
currency/rail   INR / DEMO_BANK_RAIL
```

Calls for another tenant or user cannot see the seeded accounts or prepared actions.

## Local setup

Use Python 3.12. From this folder:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
bank-mcp-demo
```

Set long random values for `BANK_DEMO_MCP_TOKEN` and `BANK_DEMO_UI_TOKEN` before starting. Then open
`http://localhost:8090`. The UI token only unlocks the demonstration dashboard API; it cannot call
MCP tools.

## Connect it to Xyena

The root Xyena MCP service must receive these environment values:

```text
XYENA_MCP_ADMIN_TOKEN=<separate high-entropy review credential>
BANK_DEMO_MCP_TOKEN=<exact same MCP token configured in this demo>
```

The demo `.env` also needs the Xyena control-plane values shown in `.env.example`. For a host-based
run, use `BANK_DEMO_PUBLIC_MCP_URL=http://host.docker.internal:8090/mcp` when Xyena runs in Docker.
For the supplied Docker Compose connection, the value is `http://bank-demo:8090/mcp`.

With Xyena core and the bank demo running, activate the connection:

```powershell
bank-mcp-register
```

The utility is intentionally explicit. It:

1. registers or reuses the tenant-local `bank` server;
2. invokes MCP discovery using the service credential;
3. activates the server as `REVIEWED_INTERNAL` using the separate admin credential;
4. verifies that the discovered catalog exactly matches the seven expected tools;
5. activates each immutable tool schema version with its reviewed Guardian policy.

It will stop if a tool is missing or an unexpected tool appears. It never silently trusts schema
drift.

## Docker Compose

The supplied compose file joins the existing `xyena-core_backend` network created by the root
Compose stack:

```powershell
docker compose up --build -d bank-demo
docker compose --profile registration run --rm register
```

For isolated UI-only use, either create a network with that name first or remove the external
network stanza locally. Xyena registration requires the shared network.

## Development connection check

After the server is running, `python -m bank_demo.client` lists the remote tools and invokes
`accounts.list`. This utility locally constructs a gateway-style signed scope and therefore uses
the MCP secret. It is for development diagnostics only; production callers must always use the
Xyena MCP broker so registry policy, Guardian authorization, audit, result limits, and idempotency
controls cannot be bypassed.

## Implemented versus intentionally absent

Implemented and ready:

- synthetic bank web/API service;
- MCP connection and discovery;
- reviewed Xyena registry activation;
- Guardian-routed policies;
- signed per-user runtime context;
- consented evidence reads;
- beneficiary and limit checks;
- transfer preparation/status only;
- synthetic audit trail and dashboard.

Intentionally absent:

- real bank or Account Aggregator integration;
- payment execution or balance mutation;
- beneficiary creation/update;
- holds, releases, reversals, mandates, or credentials;
- GST, lender, dealer, wallet, portfolio, DeFi, or any other demo application.
