const page = document.body.dataset.page;
const titles = {
  dashboard: ["Operations overview", "Current filing and invoice position"],
  invoices: ["Invoice register", "Search and govern the invoice lifecycle"],
  "invoice-new": ["Create invoice", "Record a new source invoice"],
  "invoice-detail": ["Invoice record", "Authoritative invoice state and history"],
  taxpayers: ["Taxpayer profile", "Registration and identity record"],
  returns: ["Return summaries", "Period turnover and liability"],
  classification: ["MSME classification", "Composite investment and turnover assessment"],
  audit: ["Audit ledger", "Immutable operational activity"],
  mcp: ["MCP connection", "Read-only Xyena evidence interface"],
};
const nav = [
  ["dashboard", "/dashboard", "Overview"],
  ["invoices", "/invoices", "Invoices"],
  ["invoice-new", "/invoices/new", "Create invoice"],
  ["taxpayers", "/taxpayers", "Taxpayer"],
  ["returns", "/returns", "Returns"],
  ["classification", "/classification", "MSME classification"],
  ["audit", "/audit", "Audit ledger"],
  ["mcp", "/mcp-connection", "MCP connection"],
];

let sessionState = null;
const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);
const money = (value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
const compactMoney = (value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
const statusClass = (value) => `status status-${String(value || "pending").toLowerCase().replaceAll("_", "-")}`;
const formatDate = (value) => value ? new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)) : "—";

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = sessionStorage.getItem("gst_csrf") || "";
  const response = await fetch(path, { credentials: "same-origin", ...options, headers });
  if (response.status === 401 && page !== "login") {
    window.location.href = "/login";
    throw new Error("Sign in to continue.");
  }
  const body = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status}).`);
  return body;
}

function toast(message, isError = false) {
  const element = byId("toast");
  if (!element) return;
  element.textContent = message;
  element.className = `toast show${isError ? " error" : ""}`;
  window.clearTimeout(element._timer);
  element._timer = window.setTimeout(() => element.className = "toast", 3500);
}

async function loadSession() {
  const data = await api("/api/v1/auth/session");
  sessionStorage.setItem("gst_csrf", data.csrf_token);
  sessionState = data;
  return data;
}

function shell(session) {
  const template = byId("page-content");
  const content = template ? template.innerHTML : "";
  const [title, subtitle] = titles[page] || ["GST portal", "Synthetic operations"];
  byId("portal-root").innerHTML = `
    <div class="demo-notice">Synthetic GST environment — no GSTN, Udyam, Aadhaar, PAN or government system is connected</div>
    <div class="portal">
      <aside class="docket-rail">
        <a class="brand" href="/dashboard"><span class="brand-seal">GST</span><span><strong>XYENA GST</strong><small>e-Invoice operations</small></span></a>
        <section class="enterprise-docket">
          <p class="docket-label">Active tax docket</p>
          <strong>${escapeHtml(session.enterprise.trade_name)}</strong>
          <div class="docket-row"><span>GSTIN</span><span>${escapeHtml(session.enterprise.gstin)}</span></div>
          <div class="docket-row"><span>Class</span><span>${escapeHtml(session.enterprise.classification)}</span></div>
          <div class="docket-row"><span>FY</span><span>${escapeHtml(session.enterprise.financial_year)}</span></div>
          <div class="docket-row"><span>Source</span><span>${escapeHtml(session.enterprise.classification_provenance)}</span></div>
        </section>
        <nav>${nav.map(([key, href, label]) => `<a class="nav-link ${page === key || (page === "invoice-detail" && key === "invoices") ? "active" : ""}" href="${href}">${label}</a>`).join("")}</nav>
        <div class="rail-footer"><button id="logoutButton">Sign out</button><p>All records are synthetic and isolated to the active enterprise membership.</p></div>
      </aside>
      <main class="workspace">
        <header class="workspace-header">
          <div><p class="eyebrow">${escapeHtml(subtitle)}</p><h1>${escapeHtml(title)}</h1></div>
          <div class="header-actions"><span class="live-state" id="liveState">Live database</span><span class="user-chip">${escapeHtml(session.user.display_name)}</span></div>
        </header>
        ${session.memberships.length > 1 ? `<div class="filters"><div class="field"><label for="enterpriseSwitch">Active enterprise</label><select id="enterpriseSwitch">${session.memberships.map(item => `<option value="${item.enterprise_id}" ${item.enterprise_id === session.enterprise.id ? "selected" : ""}>${escapeHtml(item.trade_name)} · ${escapeHtml(item.classification)}</option>`).join("")}</select></div></div>` : ""}
        ${content}
      </main>
    </div><div class="toast" id="toast" role="status"></div>`;
  byId("logoutButton").addEventListener("click", async () => {
    await api("/api/v1/auth/logout", { method: "POST", body: "{}" });
    sessionStorage.removeItem("gst_csrf");
    window.location.href = "/login";
  });
  byId("enterpriseSwitch")?.addEventListener("change", async (event) => {
    await api("/api/v1/auth/enterprise", { method: "POST", body: JSON.stringify({ enterprise_id: event.target.value }) });
    window.location.reload();
  });
}

function connectEvents() {
  const events = new EventSource("/api/v1/events/stream");
  events.onopen = () => { if (byId("liveState")) byId("liveState").textContent = "Live database"; };
  events.onerror = () => { if (byId("liveState")) byId("liveState").textContent = "Reconnecting"; };
  ["invoice.created", "invoice.submitted", "invoice.registered", "invoice.rejected", "invoice.cancelled", "enterprise.classification_changed"].forEach(name => {
    events.addEventListener(name, () => toast("A committed record changed. Refresh to view the latest version."));
  });
}

async function initLogin() {
  const options = document.querySelectorAll(".account-option");
  options.forEach(option => option.addEventListener("click", () => {
    byId("email").value = option.dataset.email;
    byId("password").focus();
  }));
  byId("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button");
    const message = byId("loginMessage");
    button.disabled = true; button.textContent = "Opening tax docket…";
    message.textContent = "Checking the isolated demonstration account."; message.classList.remove("error");
    try {
      const result = await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email: byId("email").value, password: byId("password").value }) });
      sessionStorage.setItem("gst_csrf", result.csrf_token);
      window.location.href = result.redirect;
    } catch (error) {
      message.textContent = error.message; message.classList.add("error");
    } finally { button.disabled = false; button.textContent = "Open tax docket"; }
  });
}

async function initDashboard() {
  const data = await api("/api/v1/dashboard");
  const counts = data.invoice_counts;
  byId("registeredCount").textContent = counts.REGISTERED || 0;
  byId("pendingCount").textContent = (counts.SUBMITTED || 0) + (counts.DRAFT || 0);
  byId("taxableTurnover").textContent = compactMoney(data.registered_taxable_turnover);
  byId("taxTotal").textContent = compactMoney(data.registered_tax_total);
  byId("dashboardInvoices").innerHTML = invoiceRows(data.recent_invoices);
  const c = data.classification;
  byId("classificationCard").innerHTML = `<span class="${statusClass(c.verification_status)}">${escapeHtml(c.verification_status)}</span><h3>${escapeHtml(c.effective_classification)} enterprise</h3><p>${money(c.annual_turnover)} turnover · ${money(c.investment_amount)} investment</p><small>${escapeHtml(c.threshold_policy_version)}</small>`;
}

function invoiceRows(items) {
  if (!items.length) return '<tr><td colspan="6" class="empty-state"><strong>No invoices found</strong>Create a draft invoice to begin.</td></tr>';
  return items.map(item => `<tr><td><a href="/invoice?id=${encodeURIComponent(item.id)}"><strong>${escapeHtml(item.invoice_number)}</strong></a><small>${formatDate(item.invoice_date)}</small></td><td>${escapeHtml(item.buyer_name)}<small>${escapeHtml(item.buyer_gstin)}</small></td><td>${escapeHtml(item.financial_year)}</td><td class="numeric"><strong>${money(item.total_invoice_value)}</strong></td><td><span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span></td><td><code>${item.version}</code></td></tr>`).join("");
}

async function loadInvoices() {
  const params = new URLSearchParams();
  if (byId("invoiceQuery")?.value) params.set("query", byId("invoiceQuery").value);
  if (byId("invoiceStatus")?.value) params.set("invoice_status", byId("invoiceStatus").value);
  const items = await api(`/api/v1/invoices?${params}`);
  byId("invoiceRows").innerHTML = invoiceRows(items);
  byId("resultCount").textContent = `${items.length} records`;
}

async function initInvoices() {
  await loadInvoices();
  byId("invoiceFilters").addEventListener("submit", async (event) => { event.preventDefault(); await loadInvoices(); });
}

function lineRow() {
  return `<div class="line-row"><input data-field="description" placeholder="Goods or service" required><input data-field="hsn_sac" value="847990" required><input data-field="quantity" type="number" min="0.001" step="0.001" value="1" required><select data-field="unit"><option>NOS</option><option>KGS</option><option>MTR</option><option>HRS</option></select><input data-field="unit_price" type="number" min="0.01" step="0.01" required><input data-field="discount" type="number" min="0" step="0.01" value="0"><select data-field="gst_rate"><option>5</option><option>12</option><option selected>18</option><option>28</option></select><button type="button" class="remove-line" aria-label="Remove line">Remove</button></div>`;
}

async function initInvoiceNew() {
  const container = byId("lineRows");
  container.innerHTML = lineRow();
  byId("addLine").addEventListener("click", () => container.insertAdjacentHTML("beforeend", lineRow()));
  container.addEventListener("click", event => { if (event.target.matches(".remove-line") && container.children.length > 1) event.target.closest(".line-row").remove(); });
  byId("invoiceForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const lines = [...document.querySelectorAll("#lineRows .line-row")].map(row => Object.fromEntries([...row.querySelectorAll("[data-field]")].map(input => [input.dataset.field, input.value])));
    const payload = {
      invoice_number: byId("invoiceNumber").value,
      invoice_type: byId("invoiceType").value,
      invoice_date: byId("invoiceDate").value,
      buyer_gstin: byId("buyerGstin").value,
      buyer_name: byId("buyerName").value,
      purchase_order_id: byId("purchaseOrder").value || null,
      place_of_supply: byId("placeOfSupply").value,
      lines,
    };
    try {
      const invoice = await api("/api/v1/invoices", { method: "POST", body: JSON.stringify(payload) });
      window.location.href = `/invoice?id=${encodeURIComponent(invoice.id)}`;
    } catch (error) { toast(error.message, true); }
  });
  byId("invoiceDate").value = new Date().toISOString().slice(0, 10);
}

async function initInvoiceDetail() {
  const id = new URLSearchParams(window.location.search).get("id");
  if (!id) { byId("invoiceDetail").innerHTML = '<div class="empty-state"><strong>No invoice selected</strong>Return to the invoice register.</div>'; return; }
  const invoice = await api(`/api/v1/invoices/${encodeURIComponent(id)}`);
  renderInvoiceDetail(invoice);
}

function renderInvoiceDetail(invoice) {
  byId("invoiceDetail").innerHTML = `
    <section class="invoice-hero"><div><p class="section-label">${escapeHtml(invoice.invoice_type)} · ${escapeHtml(invoice.financial_year)}</p><h2>${escapeHtml(invoice.invoice_number)}</h2><span class="${statusClass(invoice.status)}">${escapeHtml(invoice.status)}</span></div><div class="invoice-total"><strong>${money(invoice.total_invoice_value)}</strong><small>Invoice total including tax</small></div></section>
    <div class="action-bar"><div><a class="secondary-button" href="/invoices">Back to register</a></div><div id="workflowActions"></div></div>
    <section class="detail-grid"><div class="detail-cell"><span>Seller GSTIN</span><strong>${escapeHtml(invoice.seller_gstin)}</strong></div><div class="detail-cell"><span>Buyer</span><strong>${escapeHtml(invoice.buyer_name)}</strong></div><div class="detail-cell"><span>Buyer GSTIN</span><strong>${escapeHtml(invoice.buyer_gstin)}</strong></div><div class="detail-cell"><span>Invoice date</span><strong>${formatDate(invoice.invoice_date)}</strong></div><div class="detail-cell"><span>Purchase order</span><strong>${escapeHtml(invoice.purchase_order_id || "Not linked")}</strong></div><div class="detail-cell"><span>Place of supply</span><strong>${escapeHtml(invoice.place_of_supply)}</strong></div><div class="detail-cell"><span>IRN</span><strong><code>${escapeHtml(invoice.irn || "Generated after registration")}</code></strong></div><div class="detail-cell"><span>Record version</span><strong>${invoice.version}</strong></div></section>
    <section class="content-grid" style="margin-top:16px"><article class="panel panel-full"><div class="panel-header"><div><p class="section-label">Server-calculated</p><h2>Line items and tax</h2></div></div><div class="table-wrap"><table><thead><tr><th>Item</th><th>HSN/SAC</th><th>Qty</th><th>Rate</th><th>Taxable</th><th>GST</th><th>Total</th></tr></thead><tbody>${invoice.lines.map(line => `<tr><td>${escapeHtml(line.description)}</td><td><code>${escapeHtml(line.hsn_sac)}</code></td><td>${escapeHtml(line.quantity)} ${escapeHtml(line.unit)}</td><td class="numeric">${money(line.unit_price)}</td><td class="numeric">${money(line.taxable_value)}</td><td class="numeric">${escapeHtml(line.gst_rate)}%</td><td class="numeric"><strong>${money(line.total_value)}</strong></td></tr>`).join("")}</tbody></table></div></article><article class="panel"><div class="panel-header"><div><p class="section-label">Lifecycle</p><h2>Status timeline</h2></div></div><div class="panel-body"><ol class="timeline">${invoice.history.map(item => `<li><strong>${escapeHtml(item.new_status)}</strong><small>Version ${item.version} · ${formatDate(item.occurred_at)}${item.reason ? ` · ${escapeHtml(item.reason)}` : ""}</small></li>`).join("") || '<li><strong>Current record</strong></li>'}</ol></div></article><article class="panel"><div class="panel-header"><div><p class="section-label">Document integrity</p><h2>Registration controls</h2></div></div><div class="panel-body"><p><strong>Taxable value</strong><br>${money(invoice.taxable_value)}</p><p><strong>CGST / SGST / IGST</strong><br>${money(invoice.cgst_amount)} / ${money(invoice.sgst_amount)} / ${money(invoice.igst_amount)}</p><p><strong>Source hash</strong><br><code class="identifier">${escapeHtml(invoice.source_document_hash || "Frozen on submission")}</code></p></div></article></section>`;
  const actions = [];
  if (invoice.status === "DRAFT" && sessionState.roles.includes("GST_OPERATOR")) actions.push(["submit", "Submit for review", "primary-button"]);
  if (invoice.status === "SUBMITTED" && sessionState.roles.includes("GST_REVIEWER")) { actions.push(["register", "Register invoice", "primary-button"]); actions.push(["reject", "Reject", "danger-button"]); }
  if (invoice.status === "REGISTERED" && sessionState.roles.includes("GST_REVIEWER")) actions.push(["cancel", "Cancel invoice", "danger-button"]);
  byId("workflowActions").innerHTML = actions.map(([action, label, style]) => `<button class="${style}" data-action="${action}">${label}</button>`).join("") || '<span class="panel-note">No workflow action is available for this account and state.</span>';
  byId("workflowActions").addEventListener("click", async event => {
    const action = event.target.dataset.action; if (!action) return;
    const needsReason = ["reject", "cancel"].includes(action);
    const reason = needsReason ? window.prompt(`Reason to ${action} this invoice:`) : null;
    if (needsReason && !reason) return;
    try {
      await api(`/api/v1/invoices/${invoice.id}/${action}`, { method: "POST", headers: { "If-Match": String(invoice.version) }, body: JSON.stringify({ reason }) });
      window.location.reload();
    } catch (error) { toast(error.message, true); }
  });
}

async function initTaxpayers() {
  const items = await api("/api/v1/taxpayers");
  byId("taxpayerCards").innerHTML = items.map(item => `<article class="panel"><div class="panel-header"><div><p class="section-label">${escapeHtml(item.taxpayer_type)}</p><h2>${escapeHtml(item.trade_name)}</h2></div><span class="${statusClass(item.registration_status)}">${escapeHtml(item.registration_status)}</span></div><div class="panel-body"><div class="detail-grid"><div class="detail-cell"><span>GSTIN</span><strong>${escapeHtml(item.gstin)}</strong></div><div class="detail-cell"><span>Legal name</span><strong>${escapeHtml(item.legal_name)}</strong></div><div class="detail-cell"><span>Registration date</span><strong>${formatDate(item.registration_date)}</strong></div><div class="detail-cell"><span>State code</span><strong>${escapeHtml(item.state_code)}</strong></div></div><p style="margin-top:16px"><strong>Registered address</strong><br>${escapeHtml(item.registered_address.line1)}, ${escapeHtml(item.registered_address.city)} · ${escapeHtml(item.registered_address.postal_code)}</p></div></article>`).join("");
}

async function initReturns() {
  const items = await api("/api/v1/returns");
  byId("returnRows").innerHTML = items.map(item => `<tr><td><strong>${escapeHtml(item.return_type)}</strong><small>${escapeHtml(item.period)}</small></td><td>${escapeHtml(item.gstin)}</td><td class="numeric">${money(item.turnover)}</td><td class="numeric">${money(item.tax_total)}</td><td class="numeric">${item.invoice_count}</td><td><span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span></td><td>${item.version}</td></tr>`).join("") || '<tr><td colspan="7" class="empty-state"><strong>No return version</strong>Generate a period return after invoices are registered.</td></tr>';
}

async function initClassification() {
  const data = await api("/api/v1/enterprises/current/classification");
  byId("classificationStages").innerHTML = [["Declared", data.declared_classification], ["Calculated", data.calculated_classification], ["Effective", data.effective_classification]].map(([label, value]) => `<div class="classification-stage"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  byId("classificationInputs").innerHTML = `<div class="detail-cell"><span>Annual turnover</span><strong>${money(data.annual_turnover)}</strong></div><div class="detail-cell"><span>Plant/equipment investment</span><strong>${money(data.investment_amount)}</strong></div><div class="detail-cell"><span>Financial year</span><strong>${escapeHtml(data.financial_year)}</strong></div><div class="detail-cell"><span>Verification</span><strong><span class="${statusClass(data.verification_status)}">${escapeHtml(data.verification_status)}</span></strong></div><div class="detail-cell"><span>Source</span><strong>${escapeHtml(data.source_type)}</strong></div><div class="detail-cell"><span>Policy</span><strong><code>${escapeHtml(data.threshold_policy_version)}</code></strong></div><div class="detail-cell"><span>Effective from</span><strong>${formatDate(data.effective_from)}</strong></div><div class="detail-cell"><span>Source reference</span><strong><code>${escapeHtml(data.source_reference)}</code></strong></div>`;
  if (sessionState.roles.includes("GST_REVIEWER")) {
    byId("classificationActions").innerHTML = '<button class="secondary-button" id="recalculateButton">Recalculate from snapshot</button>';
    byId("classificationReview").style.display = "block";
    byId("effectiveClassification").value = data.effective_classification;
  }
  byId("recalculateButton")?.addEventListener("click", async () => { try { await api("/api/v1/enterprises/current/classification/recalculate", { method: "POST", body: "{}" }); window.location.reload(); } catch (error) { toast(error.message, true); } });
  byId("classificationReviewForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    try {
      await api("/api/v1/enterprises/current/classification/review", {
        method: "POST",
        body: JSON.stringify({ effective_classification: byId("effectiveClassification").value, reason: byId("classificationReason").value }),
      });
      window.location.reload();
    } catch (error) { toast(error.message, true); }
  });
}

async function initAudit() {
  const items = await api("/api/v1/audit");
  byId("auditRows").innerHTML = items.map(item => `<tr><td><strong>${escapeHtml(item.event_type)}</strong><small>${formatDate(item.occurred_at)}</small></td><td>${escapeHtml(item.aggregate_type)}</td><td><code>${escapeHtml(item.aggregate_id)}</code></td><td>${item.version}</td><td>${escapeHtml(item.actor_type)}</td><td>${escapeHtml(item.reason || "—")}</td></tr>`).join("") || '<tr><td colspan="6" class="empty-state">No audit events.</td></tr>';
}

function initMcp() {
  const tools = ["gst.enterprises.get_classification", "gst.taxpayers.get", "gst.registrations.verify", "gst.invoices.get", "gst.invoices.verify", "gst.invoices.search", "gst.invoices.check_duplicate", "gst.returns.get_summary"];
  byId("mcpTools").innerHTML = tools.map(name => `<div class="tool-card"><code>${name}</code><p>Sensitive read · Guardian policy · signed enterprise scope</p></div>`).join("");
  byId("mcpTenant").textContent = sessionState.enterprise.tenant_id;
  byId("mcpEnterprise").textContent = sessionState.enterprise.id;
}

const initializers = { dashboard: initDashboard, invoices: initInvoices, "invoice-new": initInvoiceNew, "invoice-detail": initInvoiceDetail, taxpayers: initTaxpayers, returns: initReturns, classification: initClassification, audit: initAudit, mcp: initMcp };

document.addEventListener("DOMContentLoaded", async () => {
  if (page === "login") { await initLogin(); return; }
  try {
    const current = await loadSession(); shell(current); connectEvents();
    if (initializers[page]) await initializers[page]();
  } catch (error) { if (page !== "login") console.error(error); }
});
