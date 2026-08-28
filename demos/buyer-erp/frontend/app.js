const tools = [
  ["erp.counterparties.verify", "Relationship evidence"],
  ["erp.purchase_orders.get", "Order and line evidence"],
  ["erp.purchase_orders.find_by_invoice", "Invoice reference resolution"],
  ["erp.receipts.get", "Posted fulfilment evidence"],
  ["erp.invoice_matches.get", "Three-way match evidence"],
  ["erp.invoice_acceptance.get", "Buyer acceptance evidence"],
];
const DEMO_UI_TOKEN = "xyena-demo";
const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);
const money = (value, currency = "INR") => new Intl.NumberFormat("en-IN", {
  style: "currency", currency, maximumFractionDigits: 2,
}).format(Number(value));
const setText = (id, value) => { const element = byId(id); if (element) element.textContent = value; };
const badgeClass = (status) => {
  if (["APPROVED", "FULFILLED", "POSTED", "MATCHED", "ACCEPTED"].includes(status)) return "good";
  if (["MISMATCHED", "DISPUTED", "REVIEW_REQUIRED", "REJECTED", "CANCELLED"].includes(status)) return "danger";
  if (["SUBMITTED", "PARTIALLY_FULFILLED", "PARTIAL_MATCH", "PARTIALLY_ACCEPTED"].includes(status)) return "pending";
  return "neutral";
};
const badge = (status) => `<span class="badge ${badgeClass(status)}">${escapeHtml(status.replaceAll("_", " "))}</span>`;

function renderOverview(data) {
  const orders = data.purchase_orders;
  const matches = data.invoice_matches;
  setText("openOrders", data.summary.open_purchase_orders);
  setText("orderedValue", money(data.summary.ordered_value));
  setText("receiptValue", money(data.summary.posted_receipt_value));
  setText("exceptionCount", data.summary.exceptions);
  const accepted = matches.find((match) => match.status === "ACCEPTED") || matches[0];
  if (accepted) {
    const order = orders.find((value) => value.id === accepted.purchase_order_id);
    const receipt = data.receipts.find((value) => value.id === accepted.receipt_id);
    setText("chainPo", order?.po_number || "No PO"); setText("chainPoState", order?.status || "Reference missing");
    setText("chainReceipt", receipt?.receipt_number || "No receipt"); setText("chainReceiptState", receipt?.status || "Not posted");
    setText("chainInvoice", accepted.invoice.invoice_number); setText("chainInvoiceState", `GST ${accepted.invoice.gst_status}`);
    setText("chainAcceptance", accepted.acceptance ? money(accepted.acceptance.accepted_amount) : "Not accepted"); setText("chainAcceptanceState", accepted.status);
  }
  const recent = byId("recentOrders");
  if (recent) recent.innerHTML = orders.length ? orders.slice(0, 5).map((order) => `
    <div class="record"><div><strong>${escapeHtml(order.po_number)}</strong><small>${escapeHtml(order.supplier_business_id)} · expected ${escapeHtml(order.expected_delivery_date || "not set")}</small></div><div class="record-value"><strong>${money(order.total, order.currency)}</strong>${badge(order.status)}</div></div>
  `).join("") : '<p class="empty">No purchase orders are available.</p>';
  const exceptions = matches.filter((match) => ["MISMATCHED", "DISPUTED", "REVIEW_REQUIRED", "PARTIAL_MATCH"].includes(match.status));
  const list = byId("exceptionList");
  if (list) list.innerHTML = exceptions.length ? exceptions.map((match) => `
    <div class="record"><div><strong>${escapeHtml(match.invoice.invoice_number)}</strong><small>${escapeHtml(match.discrepancies.join(" · ") || "Value requires review")}</small></div>${badge(match.status)}</div>
  `).join("") : '<p class="empty">No matching exceptions require attention.</p>';
}

function renderOrders(data) {
  const orders = data.purchase_orders;
  setText("orderCount", orders.length);
  setText("approvedOrderCount", orders.filter((order) => ["APPROVED", "PARTIALLY_FULFILLED", "FULFILLED", "CLOSED"].includes(order.status)).length);
  setText("orderedValue", money(data.summary.ordered_value));
  const rows = byId("orderRows");
  if (rows) rows.innerHTML = orders.length ? orders.map((order) => `
    <tr><td><strong>${escapeHtml(order.po_number)}</strong><small>${escapeHtml(order.id)}</small></td><td>${escapeHtml(order.supplier_business_id)}<small>${escapeHtml(order.seller_gstin)}</small></td><td>${escapeHtml(order.order_date)}<small>Expected ${escapeHtml(order.expected_delivery_date || "—")}</small></td><td class="right"><strong>${money(order.total, order.currency)}</strong><small>Tax ${money(order.tax, order.currency)}</small></td><td>${order.payment_terms_days} days</td><td>${badge(order.status)}</td><td>v${order.version}</td></tr>
  `).join("") : '<tr><td colspan="7" class="empty">No purchase orders are available.</td></tr>';
}

function renderReceipts(data) {
  const receipts = data.receipts;
  setText("receiptCount", receipts.length);
  setText("receiptValue", money(data.summary.posted_receipt_value));
  setText("postedReceiptCount", receipts.filter((receipt) => receipt.status === "POSTED").length);
  const rows = byId("receiptRows");
  if (rows) rows.innerHTML = receipts.length ? receipts.map((receipt) => `
    <tr><td><strong>${escapeHtml(receipt.receipt_number)}</strong><small>${escapeHtml(receipt.id)}</small></td><td><code>${escapeHtml(receipt.purchase_order_id)}</code></td><td>${escapeHtml(receipt.delivery_reference)}</td><td>${escapeHtml(receipt.posting_date)}</td><td class="right"><strong>${money(receipt.accepted_value)}</strong></td><td>${badge(receipt.status)}</td><td>v${receipt.version}</td></tr>
  `).join("") : '<tr><td colspan="7" class="empty">No receipts are available.</td></tr>';
}

function renderMatches(data) {
  const matches = data.invoice_matches;
  setText("matchCount", matches.length); setText("supportedValue", money(data.summary.supported_invoice_value));
  setText("acceptedMatchCount", matches.filter((match) => ["ACCEPTED", "PARTIALLY_ACCEPTED"].includes(match.status)).length);
  setText("exceptionCount", data.summary.exceptions);
  const list = byId("matchList");
  if (!list) return;
  list.innerHTML = matches.length ? matches.map((match) => `
    <article class="match-card"><div class="match-title"><div><strong>${escapeHtml(match.invoice.invoice_number)}</strong><small>GST ${escapeHtml(match.invoice.gst_status)} · source v${match.invoice.source_version} · ${escapeHtml(match.invoice.irn_token || "no IRN")}</small></div>${badge(match.status)}</div><div class="match-values"><div><span>PO value</span><strong>${money(match.po_value)}</strong></div><div><span>Posted receipt</span><strong>${money(match.receipt_value)}</strong></div><div><span>Invoice claim</span><strong>${money(match.invoice_value)}</strong></div><div><span>Supported value</span><strong>${money(match.supported_value)}</strong></div></div>${match.discrepancies.length ? `<div class="discrepancies">${escapeHtml(match.discrepancies.join(" · "))}</div>` : ""}</article>
  `).join("") : '<article class="panel"><p class="empty">No invoice matches are available.</p></article>';
}

function renderCounterparties(data) {
  const values = data.counterparties;
  const approved = values.filter((value) => value.relationship_status === "APPROVED").length;
  setText("counterpartyCount", values.length); setText("approvedCounterpartyCount", approved); setText("reviewCounterpartyCount", values.length - approved);
  const rows = byId("counterpartyRows");
  if (rows) rows.innerHTML = values.length ? values.map((value) => `
    <tr><td><strong>${escapeHtml(value.legal_name)}</strong><small>${escapeHtml(value.business_id)}</small></td><td>${escapeHtml(value.role)}</td><td><code>${escapeHtml(value.gstin)}</code></td><td>${value.payment_terms_days} days</td><td>${badge(value.relationship_status)}</td><td>${value.risk_flags.length ? escapeHtml(value.risk_flags.join(", ")) : "None"}</td></tr>
  `).join("") : '<tr><td colspan="6" class="empty">No counterparties are available.</td></tr>';
}

function renderActivity(data) {
  setText("auditCount", data.audit_events.length); setText("outboxCount", data.summary.pending_outbox_events);
  const timeline = byId("timeline");
  if (timeline) timeline.innerHTML = data.audit_events.length ? data.audit_events.map((event) => `
    <li><strong>${escapeHtml(event.event_type.replaceAll("_", " "))}</strong><small>${escapeHtml(event.aggregate_type)} · ${escapeHtml(event.aggregate_id)} · v${event.aggregate_version}</small><small>${escapeHtml(event.actor_type)} ${escapeHtml(event.actor_id)} · ${escapeHtml(event.occurred_at)} · ${escapeHtml(event.correlation_id)}</small></li>
  `).join("") : '<li><strong>No audit events have been recorded.</strong></li>';
}

function renderTools() {
  const grid = byId("toolGrid"); if (!grid) return;
  grid.innerHTML = tools.map(([name, description]) => `<div class="tool"><code>${name}</code><small>${description} · sensitive read</small></div>`).join("");
}

function render(data) { renderOverview(data); renderOrders(data); renderReceipts(data); renderMatches(data); renderCounterparties(data); renderActivity(data); setText("tenantId", data.tenant_id); }
function setConnection(state, label) { const button = byId("disconnect"); if (!button) return; button.dataset.state = state; button.disabled = state !== "ready"; setText("connectionLabel", label); }

async function loadData(token, automatic = false) {
  const form = byId("accessForm"); const button = form?.querySelector("button"); const message = byId("accessMessage"); const label = button?.textContent;
  if (button) { button.disabled = true; button.textContent = "Loading…"; } if (message) { message.classList.remove("error"); message.textContent = "Loading the tenant-scoped ERP dataset."; }
  try {
    const response = await fetch("/api/v1/dashboard", { headers: { "X-ERP-UI-Token": token } });
    if (!response.ok) throw new Error(response.status === 401 ? "The ERP dashboard token was not accepted." : `The ERP API returned status ${response.status}.`);
    const data = await response.json(); render(data); sessionStorage.setItem("xyena-erp-ui-token", token); setConnection("ready", "Synthetic ERP connected"); byId("access")?.classList.add("connected");
  } catch (error) { sessionStorage.removeItem("xyena-erp-ui-token"); setConnection("error", "Connection failed"); if (message) { message.classList.add("error"); message.textContent = error.message; } if (automatic) byId("access")?.classList.remove("connected"); }
  finally { if (button) { button.disabled = false; button.textContent = label; } }
}

renderTools();
byId("accessForm")?.addEventListener("submit", (event) => { event.preventDefault(); loadData(byId("token").value); });
byId("disconnect")?.addEventListener("click", () => { sessionStorage.removeItem("xyena-erp-ui-token"); window.location.reload(); });
const savedToken = sessionStorage.getItem("xyena-erp-ui-token");
if (byId("token")) byId("token").value = savedToken || DEMO_UI_TOKEN;
if (savedToken) loadData(savedToken, true);
