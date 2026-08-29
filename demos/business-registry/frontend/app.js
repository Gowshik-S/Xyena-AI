const page = document.body.dataset.page;
const titles = {
  dashboard: ["Registry overview", "Authoritative synthetic identity position"],
  businesses: ["Business register", "Search legal identity and registry state"],
  "business-new": ["Create pending record", "Registry operator intake"],
  "business-detail": ["Business folio", "Identity, ownership and relationship evidence"],
  changes: ["Change review queue", "Controlled identity corrections"],
  relationships: ["Relationship register", "Buyer, seller and group evidence"],
  audit: ["Registry audit ledger", "Committed operational history"],
  mcp: ["MCP connection", "Read-only Xyena identity evidence"],
};
const nav = [
  ["dashboard", "/dashboard", "Overview"],
  ["businesses", "/businesses", "Business register"],
  ["business-new", "/businesses/new", "Create record"],
  ["changes", "/change-requests", "Change review"],
  ["relationships", "/relationships", "Relationships"],
  ["audit", "/audit", "Audit ledger"],
  ["mcp", "/mcp-connection", "MCP connection"],
];

let sessionState = null;
const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);
const statusClass = (value) => `status status-${String(value || "pending").toLowerCase().replaceAll("_", "-")}`;
const formatDate = (value) => value ? new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)) : "—";
const addressText = (value) => value ? [value.line1, value.city, value.state_code, value.postal_code, value.country].filter(Boolean).join(", ") : "—";

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = sessionStorage.getItem("registry_csrf") || "";
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
  sessionStorage.setItem("registry_csrf", data.csrf_token);
  sessionState = data;
  return data;
}

function shell(session) {
  const template = byId("page-content");
  const content = template ? template.innerHTML : "";
  const [title, subtitle] = titles[page] || ["Business Registry", "Synthetic records office"];
  const role = session.roles.includes("REGISTRY_REVIEWER") ? "Registry reviewer" : "Registry operator";
  byId("portal-root").innerHTML = `
    <div class="demo-notice">Synthetic business registry — no MCA, Udyam, GSTN, Aadhaar, PAN or government system is connected</div>
    <div class="portal">
      <aside class="registry-rail">
        <a class="brand" href="/dashboard"><span class="brand-seal">BR</span><span><strong>XYENA REGISTRY</strong><small>Business evidence office</small></span></a>
        <section class="registry-scope">
          <p class="scope-label">Authenticated registry desk</p><strong>${escapeHtml(role)}</strong>
          <div class="scope-row"><span>User</span><span>${escapeHtml(session.user.display_name)}</span></div>
          <div class="scope-row"><span>Tenant</span><span>${escapeHtml(session.tenant_id)}</span></div>
          <div class="scope-row"><span>Source</span><span>SYNTHETIC</span></div>
        </section>
        <nav>${nav.filter(([key]) => key !== "business-new" || session.roles.includes("REGISTRY_OPERATOR")).map(([key, href, label]) => `<a class="nav-link ${page === key || (page === "business-detail" && key === "businesses") ? "active" : ""}" href="${href}">${label}</a>`).join("")}</nav>
        <div class="rail-footer"><button id="logoutButton">Sign out</button><p>Identity records are synthetic, versioned and tenant isolated.</p></div>
      </aside>
      <main class="workspace">
        <header class="workspace-header"><div><p class="eyebrow">${escapeHtml(subtitle)}</p><h1>${escapeHtml(title)}</h1></div><div class="header-actions"><span class="live-state" id="liveState">Live registry</span><span class="user-chip">${escapeHtml(session.user.display_name)}</span></div></header>
        ${content}
      </main>
    </div><div class="toast" id="toast" role="status"></div>`;
  byId("logoutButton").addEventListener("click", async () => {
    await api("/api/v1/auth/logout", { method: "POST", body: "{}" });
    sessionStorage.removeItem("registry_csrf");
    window.location.href = "/login";
  });
}

function connectEvents() {
  const events = new EventSource("/api/v1/events/stream");
  events.onopen = () => { if (byId("liveState")) byId("liveState").textContent = "Live registry"; };
  events.onerror = () => { if (byId("liveState")) byId("liveState").textContent = "Reconnecting"; };
  ["business.created", "business.activated", "business.suspended", "business.dissolved", "business.updated", "business.change_submitted"].forEach(name => {
    events.addEventListener(name, () => toast("A committed registry record changed. Refresh to view the latest version."));
  });
}

async function initLogin() {
  document.querySelectorAll(".account-option").forEach(option => option.addEventListener("click", () => {
    byId("email").value = option.dataset.email;
    byId("password").focus();
  }));
  byId("loginForm").addEventListener("submit", async event => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    const message = byId("loginMessage");
    button.disabled = true; button.textContent = "Opening registry desk…";
    message.textContent = "Checking the isolated demonstration account."; message.classList.remove("error");
    try {
      const result = await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email: byId("email").value, password: byId("password").value }) });
      sessionStorage.setItem("registry_csrf", result.csrf_token);
      window.location.href = result.redirect;
    } catch (error) {
      message.textContent = error.message; message.classList.add("error");
    } finally { button.disabled = false; button.textContent = "Open registry desk"; }
  });
}

function businessRows(items) {
  if (!items.length) return '<tr><td colspan="7" class="empty-state"><strong>No matching records</strong>Change the filters or create a pending business record.</td></tr>';
  return items.map(item => `<tr><td><a href="/business?id=${encodeURIComponent(item.id)}"><strong>${escapeHtml(item.legal_name)}</strong></a><small>${escapeHtml(item.trade_name || "No trade name")}</small></td><td><code>${escapeHtml(item.registry_number)}</code></td><td>${escapeHtml(item.primary_gstin || "—")}</td><td><span class="${statusClass(item.business_type)}">${escapeHtml(item.business_type)}</span></td><td><span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span></td><td>${escapeHtml(item.msme_classification || "—")}</td><td>${item.version}</td></tr>`).join("");
}

async function initDashboard() {
  const data = await api("/api/v1/dashboard");
  byId("activeCount").textContent = data.status_counts.ACTIVE || 0;
  byId("reviewCount").textContent = data.status_counts.PENDING_REVIEW || 0;
  byId("changeCount").textContent = data.pending_changes;
  byId("flaggedCount").textContent = data.flagged_businesses;
  byId("dashboardBusinesses").innerHTML = businessRows(data.recent_businesses);
  byId("typeBreakdown").innerHTML = Object.entries(data.type_counts).map(([type, count]) => `<div class="record-card"><header><strong>${escapeHtml(type)}</strong><span class="status status-company">${count} records</span></header><p>Current tenant registry classification.</p></div>`).join("");
}

async function loadBusinesses() {
  const params = new URLSearchParams();
  if (byId("businessQuery")?.value) params.set("query", byId("businessQuery").value);
  if (byId("businessStatus")?.value) params.set("business_status", byId("businessStatus").value);
  if (byId("businessType")?.value) params.set("business_type", byId("businessType").value);
  const items = await api(`/api/v1/businesses?${params}`);
  byId("businessRows").innerHTML = businessRows(items);
  byId("resultCount").textContent = `${items.length} records`;
}

async function initBusinesses() {
  await loadBusinesses();
  byId("businessFilters").addEventListener("submit", async event => { event.preventDefault(); await loadBusinesses(); });
}

async function initBusinessNew() {
  byId("incorporationDate").value = new Date().toISOString().slice(0, 10);
  byId("autoFillBusinessButton").addEventListener("click", () => {
    const uniqueNumber = String(Date.now() % 10000000).padStart(7, "0");
    const shortNumber = uniqueNumber.slice(-4);
    const demoValues = {
      registryNumber: `U28999KA2026PTC${uniqueNumber}`,
      businessId: `biz_demo_veda_${uniqueNumber}`,
      businessTypeInput: "COMPANY",
      legalName: `Veda Precision Works ${shortNumber} Private Limited`,
      tradeName: `Veda Works ${shortNumber}`,
      incorporationDate: "2022-04-18",
      primaryGstin: `29XYENA${uniqueNumber}Z`,
      industryCode: "C2599",
      msmeClass: "MICRO",
      stateCode: "29",
      postalCode: "560058",
      addressLine1: "42 Peenya Industrial Estate, Phase 2",
      city: "Bengaluru",
    };
    Object.entries(demoValues).forEach(([id, value]) => {
      const field = byId(id);
      field.value = value;
      field.dispatchEvent(new Event("input", { bubbles: true }));
      field.dispatchEvent(new Event("change", { bubbles: true }));
    });
    toast("Every business field has been filled with a unique synthetic record.");
  });
  byId("businessForm").addEventListener("submit", async event => {
    event.preventDefault();
    const payload = {
      registry_number: byId("registryNumber").value,
      business_id: byId("businessId").value,
      business_type: byId("businessTypeInput").value,
      legal_name: byId("legalName").value,
      trade_name: byId("tradeName").value || null,
      incorporation_date: byId("incorporationDate").value,
      registered_state_code: byId("stateCode").value,
      address_line1: byId("addressLine1").value,
      city: byId("city").value,
      postal_code: byId("postalCode").value,
      industry_code: byId("industryCode").value || null,
      msme_classification: byId("msmeClass").value || null,
      primary_gstin: byId("primaryGstin").value || null,
    };
    try {
      const business = await api("/api/v1/businesses", { method: "POST", body: JSON.stringify(payload) });
      window.location.href = `/business?id=${encodeURIComponent(business.id)}`;
    } catch (error) { toast(error.message, true); }
  });
}

function recordCards(items, renderer, empty) {
  return items.length ? items.map(renderer).join("") : `<div class="empty-state">${escapeHtml(empty)}</div>`;
}

async function initBusinessDetail() {
  const id = new URLSearchParams(window.location.search).get("id");
  if (!id) { byId("businessDetail").innerHTML = '<div class="empty-state"><strong>No business selected</strong>Return to the business register.</div>'; return; }
  const business = await api(`/api/v1/businesses/${encodeURIComponent(id)}`);
  renderBusinessDetail(business);
}

function renderBusinessDetail(business) {
  const flags = business.risk_flags.length ? business.risk_flags.map(flag => `<span class="flag">${escapeHtml(flag)}</span>`).join("") : '<span class="status status-verified">No active flags</span>';
  byId("businessDetail").innerHTML = `
    <section class="folio"><div><p class="section-label">${escapeHtml(business.business_type)} · version ${business.version}</p><h2>${escapeHtml(business.legal_name)}</h2><span class="${statusClass(business.status)}">${escapeHtml(business.status)}</span></div><div class="folio-number"><strong>${escapeHtml(business.registry_number)}</strong><small>Registry folio number</small></div></section>
    <div class="action-bar"><div><a class="secondary-button" href="/businesses">Back to register</a></div><div id="businessActions"></div></div>
    <section class="detail-grid"><div class="detail-cell"><span>Business ID</span><strong><code>${escapeHtml(business.business_id)}</code></strong></div><div class="detail-cell"><span>GSTIN reference</span><strong>${escapeHtml(business.primary_gstin || "Not recorded")}</strong></div><div class="detail-cell"><span>MSME classification</span><strong>${escapeHtml(business.msme_classification || "Not declared")}</strong></div><div class="detail-cell"><span>Incorporated</span><strong>${formatDate(business.incorporation_date)}</strong></div><div class="detail-cell"><span>Trade name</span><strong>${escapeHtml(business.trade_name || "Not recorded")}</strong></div><div class="detail-cell"><span>Industry code</span><strong>${escapeHtml(business.industry_code || "Not recorded")}</strong></div><div class="detail-cell"><span>Registered address</span><strong>${escapeHtml(addressText(business.registered_address))}</strong></div><div class="detail-cell"><span>Source hash</span><strong><code>${escapeHtml(business.source_hash)}</code></strong></div></section>
    <section class="content-grid" style="margin-top:16px">
      <article class="panel"><div class="panel-header"><div><p class="section-label">Authority</p><h2>Authorized persons</h2></div></div><div class="panel-body"><div class="record-list">${recordCards(business.authorized_persons, person => `<div class="record-card"><header><strong>${escapeHtml(person.display_name)}</strong><span class="${statusClass(person.authorization_status)}">${escapeHtml(person.authorization_status)}</span></header><p>${escapeHtml(person.role)} · appointed ${formatDate(person.appointment_date)}</p><code>${escapeHtml(person.person_token)}</code></div>`, "No authorized person is active.")}</div></div></article>
      <article class="panel"><div class="panel-header"><div><p class="section-label">Identity posture</p><h2>Registry flags</h2></div></div><div class="panel-body"><div class="flag-list">${flags}</div><p class="panel-note" style="margin-top:14px">Flags are evidence signals for Xyena and do not themselves approve or reject financing.</p></div></article>
      <article class="panel"><div class="panel-header"><div><p class="section-label">Beneficial ownership</p><h2>Ownership links</h2></div></div><div class="panel-body"><div class="record-list">${recordCards(business.ownership, owner => `<div class="record-card"><header><strong>${escapeHtml(owner.owner_display_name)}</strong><span>${escapeHtml(owner.ownership_percentage)}%</span></header><p>${escapeHtml(owner.owner_type)} · ${escapeHtml(owner.verification_status)}</p><div class="ownership-bar"><span style="width:${Math.min(100, Number(owner.ownership_percentage))}%"></span></div></div>`, "No ownership evidence is recorded.")}</div></div></article>
      <article class="panel"><div class="panel-header"><div><p class="section-label">Counterparty graph</p><h2>Business relationships</h2></div></div><div class="panel-body"><div class="record-list">${recordCards(business.relationships, item => `<div class="record-card"><header><strong>${escapeHtml(item.relationship_type)}</strong><span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span></header><p>${escapeHtml(item.source_business.trade_name || item.source_business.legal_name)} → ${escapeHtml(item.target_business.trade_name || item.target_business.legal_name)}</p></div>`, "No approved relationship evidence is recorded.")}</div></div></article>
      <article class="panel panel-full"><div class="panel-header"><div><p class="section-label">Version history</p><h2>Names, addresses and proposed corrections</h2></div></div><div class="panel-body"><div class="content-grid"><div><h3>Name records</h3><div class="record-list">${recordCards(business.names, item => `<div class="record-card"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.name_type)} · version ${item.record_version} · from ${formatDate(item.effective_from)}</p></div>`, "No name history.")}</div></div><div><h3>Change requests</h3><div class="record-list">${recordCards(business.change_requests, item => `<div class="record-card"><header><strong>Target version ${item.target_version}</strong><span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span></header><div class="change-patch">${escapeHtml(JSON.stringify(item.requested_patch, null, 2))}</div><p>${escapeHtml(item.reason)}</p></div>`, "No change requests.")}</div></div></div></div></article>
    </section>
    <section class="panel" id="changeProposalPanel" style="display:none;margin-top:16px"><div class="panel-header"><div><p class="section-label">Operator proposal</p><h2>Request a controlled correction</h2></div><span class="panel-note">The active record changes only after reviewer approval</span></div><div class="panel-body"><form id="changeProposalForm" class="form-grid"><div class="field"><label for="proposedTradeName">New trade name</label><input id="proposedTradeName" value="${escapeHtml(business.trade_name || "")}" maxlength="160"></div><div class="field span-2"><label for="changeReason">Reason and evidence reference</label><input id="changeReason" minlength="10" maxlength="500" required placeholder="Explain why the registry identity should change"></div><div class="form-actions span-3"><button class="primary-button" type="submit">Send correction for review</button></div></form></div></section>`;
  const actions = [];
  if (sessionState.roles.includes("REGISTRY_REVIEWER")) {
    if (business.status === "PENDING_REVIEW") actions.push(["ACTIVE", "Activate record", "primary-button"], ["REJECTED", "Reject record", "danger-button"]);
    if (business.status === "ACTIVE") actions.push(["SUSPENDED", "Suspend record", "danger-button"], ["DISSOLVED", "Mark dissolved", "danger-button"]);
    if (business.status === "SUSPENDED") actions.push(["ACTIVE", "Reactivate record", "primary-button"], ["DISSOLVED", "Mark dissolved", "danger-button"]);
  }
  byId("businessActions").innerHTML = actions.map(([target, label, style]) => `<button class="${style}" data-status="${target}">${label}</button>`).join("") || '<span class="panel-note">No status decision is available for this role and state.</span>';
  byId("businessActions").addEventListener("click", async event => {
    const target = event.target.dataset.status; if (!target) return;
    const reason = window.prompt(`Record the reason to set this business to ${target}:`);
    if (!reason) return;
    try {
      await api(`/api/v1/businesses/${business.id}/status`, { method: "POST", headers: { "If-Match": String(business.version) }, body: JSON.stringify({ target_status: target, reason }) });
      window.location.reload();
    } catch (error) { toast(error.message, true); }
  });
  if (sessionState.roles.includes("REGISTRY_OPERATOR") && ["ACTIVE", "SUSPENDED"].includes(business.status)) {
    byId("changeProposalPanel").style.display = "block";
    byId("changeProposalForm").addEventListener("submit", async event => {
      event.preventDefault();
      try {
        await api(`/api/v1/businesses/${business.id}/change-requests`, { method: "POST", body: JSON.stringify({ target_version: business.version, trade_name: byId("proposedTradeName").value, reason: byId("changeReason").value }) });
        window.location.reload();
      } catch (error) { toast(error.message, true); }
    });
  }
}

async function initChanges() {
  const items = await api("/api/v1/change-requests");
  byId("changeRows").innerHTML = items.length ? items.map(item => `<tr><td><a href="/business?id=${item.business.id}"><strong>${escapeHtml(item.business.legal_name)}</strong></a><small>${escapeHtml(item.business.registry_number)}</small></td><td>${item.target_version}</td><td><div class="change-patch">${escapeHtml(JSON.stringify(item.requested_patch))}</div></td><td>${escapeHtml(item.reason)}</td><td><span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span></td><td>${formatDate(item.created_at)}</td><td class="change-actions" data-id="${item.id}">${item.status === "SUBMITTED" && sessionState.roles.includes("REGISTRY_REVIEWER") ? '<button class="text-button" data-decision="approve">Approve</button> <button class="text-button" data-decision="reject">Reject</button>' : "—"}</td></tr>`).join("") : '<tr><td colspan="7" class="empty-state">No change requests.</td></tr>';
  byId("changeRows").addEventListener("click", async event => {
    const decision = event.target.dataset.decision; if (!decision) return;
    const id = event.target.closest(".change-actions").dataset.id;
    const reason = window.prompt(`Record the reviewer reason to ${decision} this correction:`);
    if (!reason) return;
    try {
      await api(`/api/v1/change-requests/${id}/${decision}`, { method: "POST", body: JSON.stringify({ decision_reason: reason }) });
      window.location.reload();
    } catch (error) { toast(error.message, true); }
  });
}

async function initRelationships() {
  const items = await api("/api/v1/relationships");
  byId("relationshipList").innerHTML = items.length ? items.map(item => `<div class="relationship-chain"><div><strong>${escapeHtml(item.source_business.legal_name)}</strong><small>${escapeHtml(item.source_business.registry_number)}</small></div><div class="relationship-arrow"><span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span><br>${escapeHtml(item.relationship_type)} →</div><div><strong>${escapeHtml(item.target_business.legal_name)}</strong><small>${escapeHtml(item.target_business.registry_number)}</small></div></div>`).join("") : '<div class="empty-state">No relationship evidence.</div>';
}

async function initAudit() {
  const items = await api("/api/v1/audit");
  byId("auditRows").innerHTML = items.length ? items.map(item => `<tr><td><strong>${escapeHtml(item.event_type)}</strong><small>${formatDate(item.occurred_at)}</small></td><td>${escapeHtml(item.aggregate_type)}</td><td><code>${escapeHtml(item.aggregate_id)}</code></td><td>${item.version}</td><td>${escapeHtml(item.actor_type)}</td><td>${escapeHtml(item.reason || "—")}</td></tr>`).join("") : '<tr><td colspan="6" class="empty-state">No audit events.</td></tr>';
}

function initMcp() {
  const tools = [
    ["registry.businesses.get", "Current identity and registry state"],
    ["registry.businesses.verify", "Field-by-field claimed identity comparison"],
    ["registry.businesses.search", "Bounded tenant candidate search"],
    ["registry.ownership.get", "Verified ownership graph"],
    ["registry.relationships.get", "Buyer, seller and group relationships"],
    ["registry.authorized_persons.get", "Tokenized current authority"],
  ];
  byId("mcpTools").innerHTML = tools.map(([name, purpose]) => `<div class="tool-card"><code>${name}</code><p>${purpose}. Sensitive read · Guardian policy.</p></div>`).join("");
  byId("mcpTenant").textContent = sessionState.tenant_id;
}

const initializers = {
  dashboard: initDashboard, businesses: initBusinesses, "business-new": initBusinessNew,
  "business-detail": initBusinessDetail, changes: initChanges, relationships: initRelationships,
  audit: initAudit, mcp: initMcp,
};

document.addEventListener("DOMContentLoaded", async () => {
  if (page === "login") { await initLogin(); return; }
  try {
    const current = await loadSession(); shell(current); connectEvents();
    if (initializers[page]) await initializers[page]();
  } catch (error) { if (page !== "login") console.error(error); }
});
