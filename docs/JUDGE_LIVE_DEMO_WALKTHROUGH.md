# Xyena + Guardian live judge walkthrough

This guide is the recommended four-to-six minute hands-on path for demonstrating that Xyena is connected to real deployed services rather than replaying a UI animation. All records and accounts are synthetic. The judge workflow does not move money or mutate business state unless the judge explicitly saves a draft invoice in the GST portal.

## Where to run each test

| Experience | Platform | What the judge proves |
| --- | --- | --- |
| Main live proof, MCP traces, and adversarial PDF upload | `https://app.gowshik.in/live-demo` | Deployed services, PostgreSQL registry, model inference, multiple MCP servers, Guardian authorization, exact returned evidence, and document-injection blocking |
| GST invoice creation | `https://gst.gowshik.in/login` | A human-controlled, multi-page source application that creates synthetic invoices and exposes them through GST MCP tools |

If a browser is already open on `/live-demo`, use that page for the first three tests. The malicious PDF is uploaded in the **Document security lab** on this same page; it is not uploaded to the GST portal or any third-party scanner.

## 1. Prove the deployment is live

1. Open `https://app.gowshik.in/live-demo`.
2. Click **Run live verification**.
3. Wait for the receipt to show **VERIFIED**.
4. Point out the fresh service latencies, PostgreSQL-backed active MCP server and tool counts, Guardian and MCP readiness, model provider response, unique proof ID, and `Business state changed: false` evidence.

This operation performs fresh health, registry, database, and inference calls. It is not a pre-recorded dashboard.

## 2. Let the judge operate the multi-platform MCP network

1. In **Hands-on agent trace**, keep the recommended **6-platform MCP tour** selected.
2. Press Enter or click **Run agent trace**.
3. In the execution tape, click each tool step.
4. Switch between **Request**, **Response**, and **Guardian**.
5. Show the exact tool name, safe returned source data, call ID, request/provenance hash, Guardian `ALLOW`, risk class, and authorization state.
6. Finish on the deterministic result. It must state that business state remained unchanged and audit records were created.

### How the final tool-call risk score is calculated

The trace includes one table covering every connected platform. Each tool row shows:

- registered class points: `READ 5`, `SENSITIVE_READ 15`, `MUTATE 45`, `PRIVILEGED 75`, or `UNKNOWN 90`;
- Guardian points: `ALLOW 0`, `VERIFY 8`, `ESCALATE 20`, or `BLOCK/MISSING 40`;
- execution points: `0` for success or `15` for failure;
- security points: `5` per unexpected security flag, capped at `15`; and
- the tool subtotal, capped at `100`.

The final score is `highest tool subtotal + cross-platform breadth + call volume + protected-read reduction`, clamped to `0–100`. Breadth adds two points per additional platform, capped at ten. Volume adds one point per call above three, capped at five. A five-point reduction applies only when every tool is a successful Guardian-allowed `READ` or `SENSITIVE_READ` with no unexpected flags. The highest subtotal is used instead of summing all tool rows so six safe reads do not become high risk merely because six services were consulted.

Bands are `LOW 0–24`, `GUARDED 25–49`, `HIGH 50–74`, and `CRITICAL 75–100`. The model never calculates or changes this score.

The tour calls six independent read-only capabilities:

1. `registry.businesses.verify`
2. `gst.invoices.search`
3. `erp.purchase_orders.get`
4. `delivery.deliveries.find_by_invoice`
5. `bank.accounts.list`
6. `ledger.accounts.get_balance`

The sources have separate MCP servers and source databases. Xyena supplies a signed tenant context; the central MCP Gateway resolves the registered server and tool version; Guardian evaluates the exact request; only then is the downstream source called. The model summary is advisory. The final verified/not-verified result is determined from explicit checks.

After the network tour, the judge can run the **Amount mismatch** or **Not yet registered** scenario to see a real negative result. These cases demonstrate that the UI does not always print `VERIFIED`.

## 3. Upload a malicious PDF

1. Stay on `https://app.gowshik.in/live-demo` and scroll to **Document security lab**.
2. Click **Load attack sample**, or download and re-upload `malicious-invoice-injection.pdf`.
3. Click **Scan as untrusted evidence**.
4. Confirm the result is **FLAGGED & QUARANTINED**.
5. Inspect the matched snippets and reason codes for instruction override, Guardian bypass, tool execution requests, secret extraction, and concealment.
6. Confirm all three safety facts: `0` tool calls, document content not sent to the model, and no business state change.

The scanner accepts a PDF up to 2 MB and eight pages. It validates the PDF signature, parses a bounded amount of text, examines active PDF structures, and applies deterministic injection rules. Suspicious document text is treated as data and never becomes an agent instruction or tool authorization.

## 4. Create a synthetic GST invoice with manual submission

1. Open `https://gst.gowshik.in/login`.
2. Use the prefilled Micro enterprise account, or choose Micro, Small, Medium, or Reviewer from the account list. The demo password is `xyena-demo`.
3. Open **Create invoice** from the left navigation.
4. Click **Autofill synthetic example**.
5. Review the generated invoice number, buyer, purchase order, place of supply, and two line items.
6. Observe the message **Example filled · review and save manually**.
7. The judge must explicitly click **Save draft invoice** to create it. Autofill never invokes the submit event or calls the invoice API.
8. Open the new invoice record and, if appropriate for the signed-in role, manually advance its lifecycle.
9. Return to the main live-demo agent trace and use a seeded scenario for repeatable judging. Newly created drafts remain visible in the GST portal and GST MCP search according to tenant and lifecycle policy.

## What a successful walkthrough demonstrates

- One main Xyena console orchestrates multiple independently hosted MCP platforms.
- Guardian evaluates each exact call instead of trusting the model or frontend.
- Judges can see both positive and negative deterministic decisions.
- Raw source data, tool identifiers, latency, call IDs, authorization, and provenance remain inspectable.
- The malicious document cannot promote itself into system instructions, agent context, or a tool call.
- Invoice autofill is convenient but human-controlled; submission always requires an explicit click.
- All judge data is synthetic and isolated by tenant.

## Presenter checklist

- Use the 6-platform tour first; it shows the widest platform coverage in one action.
- Click at least one Request, Response, and Guardian tab rather than only showing the final verdict.
- Run one negative invoice scenario so the judge sees fail-closed behavior.
- Upload the supplied malicious PDF and point to `0 tools executed`.
- In GST, click Autofill and pause before Save to prove that no automatic submission occurs.
- Never paste production credentials, API keys, bank data, or personal documents into the demo.
