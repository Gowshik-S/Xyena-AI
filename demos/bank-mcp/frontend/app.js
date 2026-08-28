const tools = [
  ["bank.aa.create_consent", "Mutation"],
  ["bank.aa.get_consent", "Sensitive read"],
  ["bank.aa.revoke_consent", "Privileged mutation"],
  ["bank.aa.fetch_information", "Consented read"],
  ["bank.accounts.list", "Sensitive read"],
  ["bank.accounts.get", "Sensitive read"],
  ["bank.accounts.get_balance", "Sensitive read"],
  ["bank.transactions.list", "Sensitive read"],
  ["bank.beneficiaries.verify", "Sensitive read"],
  ["bank.limits.get", "Sensitive read"],
  ["bank.transfers.prepare", "Mutation · prepare"],
  ["bank.transfers.execute", "Privileged · Guardian approval"],
  ["bank.transfers.get_status", "Sensitive read"],
  ["bank.beneficiaries.prepare_change", "Mutation · prepare"],
  ["bank.beneficiaries.execute_change", "Privileged · Guardian approval"],
  ["bank.reversals.prepare", "Mutation · prepare"],
  ["bank.reversals.execute", "Privileged · dual approval"],
  ["bank.holds.place", "Privileged · Guardian approval"],
  ["bank.holds.release", "Privileged · Guardian approval"],
];

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);
const money = (value, currency = "INR") => new Intl.NumberFormat("en-IN", {
  style: "currency", currency, maximumFractionDigits: 2,
}).format(Number(value));

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = value;
}

function renderTransactions(target, transactions, limit = transactions.length) {
  const element = byId(target);
  if (!element) return;
  const values = transactions.slice(0, limit);
  element.innerHTML = values.length ? values.map((transaction) => `
    <div class="transaction-item">
      <div><strong>${escapeHtml(transaction.description)}</strong><small>${escapeHtml(transaction.booked_on)} · ${escapeHtml(transaction.reference)}</small></div>
      <strong class="transaction-amount ${transaction.direction.toLowerCase()}">${transaction.direction === "CREDIT" ? "+" : "−"} ${money(transaction.amount, transaction.currency)}</strong>
    </div>
  `).join("") : '<p class="empty-block">No transactions are available in this evidence set.</p>';
}

function renderData(data) {
  const available = data.accounts.reduce((sum, account) => sum + Number(account.available_balance), 0);
  const highestLimit = data.accounts.reduce((highest, account) => Math.max(highest, Number(account.per_transfer_limit)), 0);
  const verified = data.beneficiaries.filter((beneficiary) => beneficiary.verified).length;
  const readyActions = data.prepared_actions.filter((action) => action.status === "READY_FOR_GUARDIAN").length;
  const credits = data.transactions.filter((transaction) => transaction.direction === "CREDIT").reduce((sum, transaction) => sum + Number(transaction.amount), 0);
  const debits = data.transactions.filter((transaction) => transaction.direction === "DEBIT").reduce((sum, transaction) => sum + Number(transaction.amount), 0);

  setText("availableFunds", money(available));
  setText("highestLimit", money(highestLimit));
  setText("accountCount", data.accounts.length);
  setText("beneficiaryCount", data.beneficiaries.length);
  setText("verifiedCount", verified);
  setText("reviewCount", data.beneficiaries.length - verified);
  setText("beneficiarySubtext", `${verified} of ${data.beneficiaries.length} currently verified`);
  setText("actionCount", data.prepared_actions.length);
  setText("readyActionCount", readyActions);
  setText("auditCount", data.audit_event_count);
  setText("consentCount", data.aa_consents.length);
  setText("fiRequestCount", data.fi_requests.length);
  setText("executionCount", data.transfer_executions.length);
  setText("holdCount", data.holds.filter((item) => item.status === "ACTIVE").length);
  setText("creditTotal", money(credits));
  setText("debitTotal", money(debits));
  setText("transactionCount", data.transactions.length);
  setText("tenantId", data.scope.tenant_id);
  setText("organizationId", data.scope.organization_id);
  setText("userId", data.scope.user_id);

  const accountRows = byId("accountRows");
  if (accountRows) accountRows.innerHTML = data.accounts.length ? data.accounts.map((account) => `
    <tr><td><strong>${escapeHtml(account.display_name)}</strong><small>${escapeHtml(account.masked_number)}</small></td><td><code>${escapeHtml(account.account_token)}</code></td><td class="align-right"><strong>${money(account.available_balance, account.currency)}</strong></td><td class="align-right">${money(account.per_transfer_limit, account.currency)}</td><td><span class="status status-safe">Active</span></td></tr>
  `).join("") : '<tr><td class="empty" colspan="5">No accounts exist in this signed scope.</td></tr>';

  const transactionRows = byId("transactionRows");
  if (transactionRows) transactionRows.innerHTML = data.transactions.length ? data.transactions.map((transaction) => `
    <tr><td>${escapeHtml(transaction.booked_on)}</td><td><strong>${escapeHtml(transaction.description)}</strong></td><td><code>${escapeHtml(transaction.reference)}</code></td><td><span class="direction direction-${transaction.direction.toLowerCase()}">${escapeHtml(transaction.direction)}</span></td><td class="align-right"><strong>${transaction.direction === "CREDIT" ? "+" : "−"} ${money(transaction.amount, transaction.currency)}</strong></td></tr>
  `).join("") : '<tr><td class="empty" colspan="5">No transaction evidence is available.</td></tr>';

  const beneficiaryRows = byId("beneficiaryRows");
  if (beneficiaryRows) beneficiaryRows.innerHTML = data.beneficiaries.length ? data.beneficiaries.map((beneficiary) => `
    <tr><td><strong>${escapeHtml(beneficiary.owner_name)}</strong></td><td><code>${escapeHtml(beneficiary.beneficiary_token)}</code></td><td>${escapeHtml(beneficiary.masked_account)}</td><td><span class="status ${beneficiary.verified ? "status-safe" : "status-review"}">${beneficiary.verified ? "Verified" : "Review required"}</span></td><td>${escapeHtml(beneficiary.status)}</td></tr>
  `).join("") : '<tr><td class="empty" colspan="5">No beneficiaries exist in this tenant.</td></tr>';

  const actionRows = byId("actionRows");
  if (actionRows) actionRows.innerHTML = data.prepared_actions.length ? data.prepared_actions.map((action) => `
    <tr><td><strong>${escapeHtml(action.proposed_action_id)}</strong></td><td><code title="${escapeHtml(action.canonical_action_hash)}">${escapeHtml(action.canonical_action_hash)}</code></td><td class="align-right"><strong>${money(action.amount, action.currency)}</strong></td><td><span class="status status-review">${escapeHtml(action.status)}</span></td></tr>
  `).join("") : '<tr><td class="empty" colspan="4">No action has been prepared through MCP.</td></tr>';

  const consentRows = byId("consentRows");
  if (consentRows) consentRows.innerHTML = data.aa_consents.length ? data.aa_consents.map((item) => `
    <tr><td><strong>${escapeHtml(item.consent_id)}</strong><small>${escapeHtml(item.purpose)}</small></td><td>${item.account_tokens.length}</td><td>${item.information_types.map(escapeHtml).join(", ")}</td><td><span class="status ${item.status === "ACTIVE" ? "status-safe" : "status-review"}">${escapeHtml(item.status)}</span></td><td>${escapeHtml(item.valid_until.slice(0, 10))}</td></tr>
  `).join("") : '<tr><td class="empty" colspan="5">No Account Aggregator consent exists.</td></tr>';

  const fiRows = byId("fiRows");
  if (fiRows) fiRows.innerHTML = data.fi_requests.length ? data.fi_requests.map((item) => `
    <tr><td><code>${escapeHtml(item.request_id)}</code></td><td>${escapeHtml(item.information_type)}</td><td><code>${escapeHtml(item.account_token)}</code></td><td><span class="status status-safe">${escapeHtml(item.status)}</span></td><td><code>${escapeHtml(item.evidence_receipt_id || "—")}</code></td></tr>
  `).join("") : '<tr><td class="empty" colspan="5">No FI request has been made through MCP.</td></tr>';

  const executionRows = byId("executionRows");
  if (executionRows) executionRows.innerHTML = data.transfer_executions.length ? data.transfer_executions.map((item) => `
    <tr><td><code>${escapeHtml(item.execution_id)}</code></td><td><code>${escapeHtml(item.bank_reference || "—")}</code></td><td class="align-right"><strong>${money(item.amount, item.currency)}</strong></td><td><span class="status status-safe">${escapeHtml(item.status)}</span></td></tr>
  `).join("") : '<tr><td class="empty" colspan="4">No Guardian-authorized transfer has settled.</td></tr>';

  const holdRows = byId("holdRows");
  if (holdRows) holdRows.innerHTML = data.holds.length ? data.holds.map((item) => `
    <tr><td><code>${escapeHtml(item.hold_id)}</code></td><td><code>${escapeHtml(item.account_token)}</code></td><td class="align-right">${money(item.amount, item.currency)}</td><td><span class="status ${item.status === "ACTIVE" ? "status-review" : "status-safe"}">${escapeHtml(item.status)}</span></td></tr>
  `).join("") : '<tr><td class="empty" colspan="4">No holds are recorded.</td></tr>';

  renderTransactions("overviewTransactions", data.transactions, 5);
}

function renderToolCatalog() {
  const grid = byId("toolGrid");
  if (!grid) return;
  grid.innerHTML = tools.map(([name, risk]) => `
    <div class="tool-item"><code>${name}</code><small>${risk} · Guardian policy</small></div>
  `).join("");
}

function setConnection(state, label) {
  const connection = byId("disconnectButton");
  if (!connection) return;
  connection.dataset.state = state;
  connection.disabled = state !== "ready";
  setText("connectionLabel", label);
  connection.title = state === "ready" ? "Clear this tab's dashboard access" : "Dashboard access is locked";
}

async function loadData(token, automatic = false) {
  const form = byId("accessForm");
  const button = form?.querySelector("button");
  const message = byId("formMessage");
  const originalLabel = button?.textContent;
  if (button) { button.disabled = true; button.textContent = "Loading…"; }
  if (message) { message.classList.remove("error"); message.textContent = "Loading the scoped synthetic dataset."; }
  try {
    const response = await fetch("/api/v1/demo/summary", { headers: { "X-Demo-Token": token } });
    if (!response.ok) throw new Error(response.status === 401 ? "The dashboard token was not accepted." : `The bank API returned status ${response.status}.`);
    const data = await response.json();
    renderData(data);
    sessionStorage.setItem("xyena-bank-demo-ui-token", token);
    setConnection("ready", "Synthetic dataset connected");
    byId("accessPanel")?.classList.add("access-panel-connected");
    if (message) message.textContent = "Connected for this browser tab. Select the status control to lock it again.";
  } catch (error) {
    sessionStorage.removeItem("xyena-bank-demo-ui-token");
    setConnection("error", "Connection failed");
    if (message) { message.classList.add("error"); message.textContent = error.message; }
    if (automatic) byId("accessPanel")?.classList.remove("access-panel-connected");
  } finally {
    if (button) { button.disabled = false; button.textContent = originalLabel; }
  }
}

renderToolCatalog();
const accessForm = byId("accessForm");
accessForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  loadData(byId("token").value);
});
byId("disconnectButton")?.addEventListener("click", () => {
  sessionStorage.removeItem("xyena-bank-demo-ui-token");
  window.location.reload();
});

const savedToken = sessionStorage.getItem("xyena-bank-demo-ui-token");
if (savedToken) {
  byId("token").value = savedToken;
  loadData(savedToken, true);
}
