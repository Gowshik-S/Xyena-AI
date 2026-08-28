const tools = [
  ["bank.accounts.list", "Sensitive read"],
  ["bank.accounts.get_balance", "Sensitive read"],
  ["bank.transactions.list", "Sensitive read"],
  ["bank.beneficiaries.verify", "Sensitive read"],
  ["bank.limits.get", "Sensitive read"],
  ["bank.transfers.prepare", "Mutation · preparation only"],
  ["bank.transfers.get_status", "Sensitive read"],
];

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);
const money = (value, currency = "INR") => new Intl.NumberFormat("en-IN", {
  style: "currency", currency, maximumFractionDigits: 2,
}).format(Number(value));

byId("toolGrid").innerHTML = tools.map(([name, risk]) => `
  <div class="tool-item"><code>${name}</code><small>${risk} · Guardian policy</small></div>
`).join("");

function render(data) {
  const total = data.accounts.reduce((sum, account) => sum + Number(account.available_balance), 0);
  const verified = data.beneficiaries.filter((beneficiary) => beneficiary.verified).length;
  byId("availableFunds").textContent = money(total);
  byId("accountCount").textContent = data.accounts.length;
  byId("verifiedCount").textContent = verified;
  byId("beneficiarySubtext").textContent = `${verified} of ${data.beneficiaries.length} currently verified`;
  byId("actionCount").textContent = data.prepared_actions.length;
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
      <td><strong>${escapeHtml(action.proposed_action_id)}</strong></td>
      <td><code title="${escapeHtml(action.canonical_action_hash)}">${escapeHtml(action.canonical_action_hash)}</code></td>
      <td class="align-right"><strong>${money(action.amount, action.currency)}</strong></td>
      <td><span class="status status-review">${escapeHtml(action.status)}</span></td>
    </tr>
  `).join("") : '<tr><td class="empty" colspan="4">No action has been prepared through MCP.</td></tr>';
}

byId("accessForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  const message = byId("formMessage");
  const connection = byId("connectionState");
  button.disabled = true;
  button.textContent = "Connecting…";
  message.classList.remove("error");
  message.textContent = "Loading the scoped synthetic dataset.";
  try {
    const response = await fetch("/api/v1/demo/summary", {
      headers: { "X-Demo-Token": byId("token").value },
    });
    if (!response.ok) throw new Error(response.status === 401 ? "The dashboard token was not accepted." : `Request failed (${response.status}).`);
    const data = await response.json();
    render(data);
    connection.dataset.state = "ready";
    byId("connectionLabel").textContent = "Synthetic dataset connected";
    message.textContent = "Connected. MCP remains protected by its separate workload token and signed runtime scope.";
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
