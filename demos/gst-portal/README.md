# XYENA synthetic GST portal

This folder contains the isolated GST and e-Invoice demonstration application for Xyena and
Guardian. It is a stateful, professional multi-page portal backed by its own PostgreSQL database
when deployed with Compose. All businesses, taxpayers, invoices, returns and classifications are
synthetic. The service does **not** contact GSTN, Udyam, Aadhaar, PAN, a government identity system,
or a real taxpayer account.

## Ready application surfaces

The browser experience is deliberately split into operational pages rather than a single dashboard:

| Page | Purpose |
|---|---|
| `/login` | Common login experience for isolated Micro, Small, Medium and reviewer accounts |
| `/dashboard` | Invoice position, registered turnover, tax totals and classification summary |
| `/invoices` | Enterprise-scoped invoice register with status and buyer search |
| `/invoices/new` | Source invoice and line-item entry with server-side tax calculation |
| `/invoice?id=...` | Versioned invoice record, tax breakdown, timeline and permitted transitions |
| `/taxpayers` | Synthetic taxpayer registration identity and provenance |
| `/returns` | Versioned period turnover and tax summaries |
| `/classification` | Declared, calculated and effective MSME classification with threshold provenance |
| `/audit` | Enterprise-scoped immutable operational event ledger |
| `/mcp-connection` | Human-readable Guardian/MCP boundary and approved tool catalog |
| `/docs` | OpenAPI 3.1 browser API description |
| `/mcp` | Bearer-protected MCP v2 Streamable HTTP endpoint |

The UI uses a light porcelain-and-ink tax-office visual system with restrained revenue blue,
filing green, saffron and vermilion status accents. It contains no neon, purple, gradients or
generic AI styling. The persistent tax-docket rail keeps the active enterprise, GSTIN,
classification, financial year and provenance visible.

## Domain and security rules

- One login mechanism serves all users, while every session resolves a server-side enterprise
  membership. Reviewer enterprise switching is membership-checked.
- Browser mutations require an opaque HTTP-only session cookie and a rotating CSRF token. Browser
  credentials are not valid at the MCP endpoint.
- Operators create and submit invoices. Reviewers register, reject or cancel them. Optimistic
  concurrency uses `If-Match` record versions.
- The server calculates financial year, taxable value, CGST, SGST, IGST and invoice total. Submitted
  records receive a canonical source-document hash; registered records receive a synthetic IRN.
- Classification is stored at enterprise level using annual investment and turnover. Declared,
  calculated and effective values remain separate and classification snapshots are append-only.
- Audit and outbox records are written in the same transaction as each domain change.
- All MCP operations are read-only and require both a service bearer credential and a valid
  HMAC-signed Xyena runtime `_meta` scope.

Current composite classification policy:

| Class | Investment | Annual turnover |
|---|---:|---:|
| Micro | ≤ ₹2.5 crore | ≤ ₹10 crore |
| Small | ≤ ₹25 crore | ≤ ₹100 crore |
| Medium | ≤ ₹125 crore | ≤ ₹500 crore |

Both limits must be satisfied. No single invoice or transaction changes the classification.

## Synthetic accounts

Set one demonstration password with `GST_PORTAL_DEMO_PASSWORD`; the seeded accounts are:

| Account | Enterprise | Role |
|---|---|---|
| `micro.operator@gst.demo.xyena.test` | Kaveri Precision | GST Operator / Micro |
| `small.operator@gst.demo.xyena.test` | Western Loomworks | GST Operator / Small |
| `medium.operator@gst.demo.xyena.test` | Northline Systems | GST Operator / Medium |
| `gst.reviewer@gst.demo.xyena.test` | All three enterprise memberships | GST Reviewer |

These are local synthetic credentials only. Do not reuse this authentication approach or password
in a production or government-connected service.

MCP runtime scopes use the enterprise ID as `organization_id`:

| Enterprise | Tenant ID | Organization / enterprise ID |
|---|---|---|
| Kaveri Precision | `00000000-0000-4000-8000-000000001101` | `00000000-0000-4000-8000-000000001201` |
| Western Loomworks | `00000000-0000-4000-8000-000000001102` | `00000000-0000-4000-8000-000000001202` |
| Northline Systems | `00000000-0000-4000-8000-000000001103` | `00000000-0000-4000-8000-000000001203` |

## MCP catalog

The registration utility installs exactly these canonical tools with `SENSITIVE_READ`,
`approval_mode=POLICY`, `allowed_agents=[xyena-supervisor]` and Guardian enforcement:

| Canonical name | Purpose |
|---|---|
| `gst.enterprises.get_classification` | Current classification snapshot and provenance |
| `gst.taxpayers.get` | Enterprise-scoped synthetic taxpayer identity |
| `gst.registrations.verify` | Registration evidence wrapper |
| `gst.invoices.get` | One invoice and its authoritative lifecycle state |
| `gst.invoices.verify` | Verify a registered invoice against supplied claims |
| `gst.invoices.search` | Narrow enterprise invoice search |
| `gst.invoices.check_duplicate` | Duplicate candidate evidence |
| `gst.returns.get_summary` | Versioned return-period summary |

Every result carries source system, schema version, record version, retrieval time, freshness,
security labels and a source hash. The MCP surface cannot create, submit, register, reject, cancel
or edit a record.

## Local setup

Use Python 3.12. From this folder:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
gst-portal-demo
```

The local default uses SQLite for a small developer walkthrough. Open `http://localhost:8091/login`.
The shared demo deployment uses the isolated PostgreSQL service in `compose.yaml`:

```powershell
docker compose up --build -d gst-portal
```

The Compose stack joins the existing `xyena-core_backend` network. Xyena core must create that
network first. The GST database remains on a separate internal network and is not shared with core.

## Register with Xyena and Guardian

The root MCP service needs `GST_PORTAL_MCP_TOKEN` set to the same separate high-entropy credential
as this application. The GST `.env` also needs the Xyena control URL, service token and distinct MCP
admin review token. After both stacks are running:

```powershell
docker compose --profile registration run --rm register
```

The utility registers one tenant-local `gst` server for each seeded tenant, discovers the remote
catalog, requires an exact eight-tool match, marks the server reviewed, and activates immutable tool
versions under Guardian policy. Unexpected catalog drift stops activation.

## Implemented and intentionally absent

Implemented and ready:

- isolated synthetic PostgreSQL data model and deterministic fixtures;
- opaque multi-enterprise browser sessions, roles, CSRF and enterprise switching;
- invoice creation and governed draft → submitted → registered/rejected/cancelled lifecycle;
- server-calculated tax values, synthetic IRN, hashes, versions, audit and outbox;
- taxpayer, return and append-only MSME classification evidence;
- professional responsive multi-page light frontend;
- OpenAPI 3.1 REST contract and live event stream;
- read-only MCP v2 service with signed Xyena scope;
- reviewed registry/Guardian policy activation utility and container packaging.

Intentionally absent:

- real GST filing, GSTN/Udyam/Aadhaar/PAN integration or production credentials;
- payment, banking, lending or delivery execution;
- mutable MCP tools;
- GST portal test suite execution as part of this delivery.
