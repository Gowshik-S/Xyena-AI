# Governed financing end-to-end flow

This coordinator joins Xyena, Guardian, the Ledger/Payment service and the Bank service without
creating a backdoor around approval. It uses one stable synthetic financing case and calls all
tools through the central MCP broker.

```text
Bank transfer prepare ─┐
                      ├─ Ledger disbursement prepare
                      └─ Guardian approves ledger posting
                                      ↓
                              balanced journal posts
                                      ↓
                      Guardian approves bank execution
                                      ↓
                      bank settles + emits 10-char reference
                                      ↓
                      ledger ingests receipt idempotently
                                      ↓
                   journal ↔ payment ↔ bank receipt MATCHED
```

Set `XYENA_MCP_GATEWAY_URL`, `XYENA_SERVICE_TOKEN`, `XYENA_E2E_RUN_ID`,
`XYENA_E2E_SESSION_ID`, `LEDGER_DEMO_URL` and `LEDGER_DEMO_SETTLEMENT_EVENT_TOKEN`. Then run:

```powershell
python demos/e2e/xyena_financing_flow.py start
```

The first privileged step returns `BLOCKED` until a Guardian approval exists. The coordinator
saves `.xyena-e2e-state.json`. After approving the exact call in Xyena, run:

```powershell
python demos/e2e/xyena_financing_flow.py resume
```

It may pause once more for bank execution approval. Approve and run `resume` again. The final
checkpoint state is `RECONCILED`. Reusing a call/event/idempotency ID with different parameters is
rejected at every boundary. An unknown bank outcome is never blindly retried.
