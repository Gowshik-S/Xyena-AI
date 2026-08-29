const tools = [
  ["bank.accounts.list", "Sensitive read"],
  ["bank.accounts.get_balance", "Sensitive read"],
  ["bank.transactions.list", "Sensitive read"],
  ["bank.beneficiaries.verify", "Sensitive read"],
  ["bank.limits.get", "Sensitive read"],
  ["bank.transfers.prepare", "Mutation · exact proposal"],
  ["bank.transfers.execute", "Privileged · human approval"],
  ["bank.transfers.get_status", "Sensitive read"],
];

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);
const money = (value, currency = "INR") => new Intl.NumberFormat("en-IN", {
  style: "currency", currency, maximumFractionDigits: 2,
}).format(Number(value));
const time = (value) => value ? new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium", timeStyle: "medium",
}).format(new Date(value)) : "Pending";
const statusClass = (value) => ["SETTLED", "ACTIVE", "SUCCESS"].includes(value)
  ? "status-safe"
  : ["EXPIRED", "FAILED", "BLOCKED"].includes(value) ? "status-danger" : "status-review";

let dashboardToken = "";
let eventSource;

byId("toolGrid").innerHTML = tools.map(([name, risk]) => `
  <div class="tool-item"><code>${name}</code><small>${risk} · Guardian policy</small></div>
`).join("");

function renderAuthorizationSeal(data) {
  const action = data.prepared_actions.find((item) => item.execution);
  if (!action) {
    byId("authorizationSeal").innerHTML = '<p class="empty-block">A settled transfer will reveal its preparation, Guardian, execution and reconciliation chain.</p>';
    byId("ledgerRows").innerHTML = '<tr><td class="empty" colspan="4">No ledger entries committed.</td></tr>';
    byId("journalBalance").textContent = "No journal";
    byId("settlementNote").textContent = "Waiting for a settled transfer";
    return;
  }

  const execution = action.execution;
  const shortHash = `${action.canonical_action_hash.slice(0, 20)}…`;
  const steps = [
    ["01", "Prepared", action.proposed_action_id, `Hash ${shortHash}`],
    ["02", "Guardian authorized", execution.guardian_decision_id, `Consumed ${execution.authorization_id}`],
    ["03", "Executed once", execution.execution_id, execution.bank_reference],
    ["04", "Settled and reconciled", time(execution.settled_at), execution.reconciliation_required ? "Operator review required" : "Bank and ledger matched"],
  ];
  byId("authorizationSeal").innerHTML = steps.map(([number, label, primary, detail]) => `
    <div class="seal-step">
      <span class="seal-number">${number}</span>
      <div><strong>${escapeHtml(label)}</strong><code>${escapeHtml(primary)}</code><small>${escapeHtml(detail)}</small></div>
    </div>
  `).join("");
  byId("settlementNote").textContent = `${execution.bank_reference} · ${time(execution.settled_at)}`;

  const entries = data.ledger_entries.filter((entry) => entry.execution_id === execution.execution_id);
  byId("ledgerRows").innerHTML = entries.map((entry) => `
    <tr>
      <td><code>${escapeHtml(entry.journal_id)}</code></td>
      <td><strong>${escapeHtml(entry.ledger_account)}</strong></td>
      <td><span class="ledger-entry ${entry.entry_type.toLowerCase()}">${escapeHtml(entry.entry_type)}</span></td>
      <td class="align-right"><strong>${money(entry.amount, entry.currency)}</strong></td>
    </tr>
  `).join("") || '<tr><td class="empty" colspan="4">No ledger entries committed.</td></tr>';
  const debits = entries.filter((entry) => entry.entry_type === "DEBIT").reduce((sum, entry) => sum + Number(entry.amount), 0);
  const credits = entries.filter((entry) => entry.entry_type === "CREDIT").reduce((sum, entry) => sum + Number(entry.amount), 0);
  byId("journalBalance").textContent = debits === credits && entries.length
    ? `Balanced · ${money(debits)}` : "Journal requires review";
}

function render(data) {
  const total = data.accounts.reduce((sum, account) => sum + Number(account.available_balance), 0);
  const verified = data.beneficiaries.filter((beneficiary) => beneficiary.verified).length;
  byId("availableFunds").textContent = money(total);
  byId("accountCount").textContent = data.accounts.length;
  byId("verifiedCount").textContent = verified;
  byId("beneficiarySubtext").textContent = `${verified} of ${data.beneficiaries.length} currently verified`;
  byId("actionCount").textContent = data.prepared_actions.length;
  byId("settledCount").textContent = data.settled_transfer_count;
  byId("settledVolume").textContent = `${money(data.settled_transfer_volume)} settled through the synthetic rail`;
  byId("auditCount").textContent = data.audit_event_count;
  byId("tenantId").textContent = data.scope.tenant_id;
  byId("organizationId").textContent = data.scope.organization_id;
  byId("userId").textContent = data.scope.user_id;

  byId("accountRows").innerHTML = data.accounts.length ? data.accounts.map((account) => `
    <tr>
      <td><strong>${escapeHtml(account.display_name)}</strong><small>${escapeHtml(account.masked_number)}</small></td>
      <td><code>${escapeHtml(account.account_token)}</code></td>
      <td class="align-right"><strong>${money(account.available_balance, account.currency)}</strong></td>
      <td class="align-right">${money(account.per_transfer_limit, account.currency)}</td>
      <td><span class="status status-safe">Active</span></td>
    </tr>
  `).join("") : '<tr><td class="empty" colspan="5">No accounts in this scope.</td></tr>';

  byId("beneficiaryList").innerHTML = data.beneficiaries.length ? data.beneficiaries.map((beneficiary) => `
    <div class="list-item">
      <div><strong>${escapeHtml(beneficiary.owner_name)}</strong><small>${escapeHtml(beneficiary.masked_account)} · ${escapeHtml(beneficiary.beneficiary_token)}</small></div>
      <span class="status ${beneficiary.verified ? "status-safe" : "status-review"}">${beneficiary.verified ? "Verified" : "Review"}</span>
    </div>
  `).join("") : '<p class="empty-block">No beneficiaries in this scope.</p>';

  byId("transactionList").innerHTML = data.transactions.length ? data.transactions.map((transaction) => `
    <div class="transaction-item">
      <div><strong>${escapeHtml(transaction.description)}</strong><small>${escapeHtml(transaction.booked_on)} · ${escapeHtml(transaction.reference)}</small></div>
      <strong class="transaction-amount ${transaction.direction.toLowerCase()}">${transaction.direction === "CREDIT" ? "+" : "−"} ${money(transaction.amount, transaction.currency)}</strong>
    </div>
  `).join("") : '<p class="empty-block">No transactions in this window.</p>';

  byId("actionRows").innerHTML = data.prepared_actions.length ? data.prepared_actions.map((action) => `
    <tr>
      <td><strong>${escapeHtml(action.proposed_action_id)}</strong><small>${escapeHtml(action.beneficiary_token)}</small></td>
      <td><code title="${escapeHtml(action.canonical_action_hash)}">${escapeHtml(action.canonical_action_hash)}</code></td>
      <td class="align-right"><strong>${money(action.amount, action.currency)}</strong></td>
      <td><span class="status ${statusClass(action.status)}">${escapeHtml(action.status)}</span></td>
      <td>${action.execution ? `<strong>${escapeHtml(action.execution.bank_reference)}</strong><small>${escapeHtml(action.execution.execution_id)}</small>` : '<small>Guardian authorization pending</small>'}</td>
    </tr>
  `).join("") : '<tr><td class="empty" colspan="5">No action has been prepared through MCP.</td></tr>';

  renderAuthorizationSeal(data);
}

async function loadSummary() {
  const response = await fetch("/api/v1/demo/summary", {
    headers: dashboardToken ? { "X-Demo-Token": dashboardToken } : {},
  });
  if (!response.ok) throw new Error(response.status === 401 ? "The dashboard token was not accepted." : `Request failed (${response.status}).`);
  render(await response.json());
}

function connectEventStream() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource("/api/v1/demo/events");
  eventSource.addEventListener("transfer.settled", async () => {
    try {
      await loadSummary();
      byId("connectionLabel").textContent = "Live settlement received";
    } catch (error) {
      byId("formMessage").textContent = error.message;
    }
  });
  eventSource.onerror = () => {
    byId("connectionLabel").textContent = "Live stream reconnecting";
  };
}

byId("accessForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  const message = byId("formMessage");
  const connection = byId("connectionState");
  dashboardToken = byId("token").value;
  button.disabled = true;
  button.textContent = "Connecting…";
  message.classList.remove("error");
  message.textContent = "Loading the scoped synthetic bank and ledger state.";
  try {
    await loadSummary();
    connectEventStream();
    connection.dataset.state = "ready";
    byId("connectionLabel").textContent = "Live synthetic bank connected";
    message.textContent = "Connected. This screen observes execution; commands remain restricted to the MCP Gateway and Guardian.";
  } catch (error) {
    connection.dataset.state = "error";
    byId("connectionLabel").textContent = "Connection failed";
    message.classList.add("error");
    message.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Open dashboard";
  }
});

document.querySelectorAll(".nav-link").forEach((link) => link.addEventListener("click", () => {
  document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("active"));
  link.classList.add("active");
}));
