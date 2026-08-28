const byId = (id) => document.getElementById(id);
const DEMO_UI_TOKEN = "xyena-demo";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
const money = (value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value || 0));
const date = (value) => value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
const setText = (id, value) => { const node = byId(id); if (node) node.textContent = value; };
const statusClass = (value) => String(value || "").toLowerCase().replaceAll("_", "-");
const badge = (value) => `<span class="badge ${statusClass(value)}">${escapeHtml(String(value).replaceAll("_", " "))}</span>`;
const tools = [
  ["funder.programs.search", "Sensitive read"], ["funder.offers.request", "Preparation"],
  ["funder.offers.get", "Sensitive read"], ["funder.offers.reserve", "Privileged reservation"],
  ["funder.reservations.release", "State change"], ["funder.commitments.prepare", "Privileged preparation"],
  ["funder.commitments.confirm", "Protected confirmation"], ["funder.exposure.get", "Sensitive read"],
];
const navigation = [
  ["overview", "/", "Overview"], ["funders", "/funders", "Funders"],
  ["programs", "/programs", "Programs"], ["applications", "/applications", "Applications"],
  ["offers", "/offers", "Offers"], ["reservations", "/reservations", "Reservations"],
  ["commitments", "/commitments", "Commitments"], ["exposure", "/exposure", "Exposure"],
  ["activity", "/activity", "Activity"], ["mcp", "/mcp-connection", "MCP connection"],
];

function mountSidebar() {
  const sidebar = byId("sidebar"); if (!sidebar) return;
  const page = document.body.dataset.page;
  sidebar.innerHTML = `<a class="brand" href="/"><span class="brand-mark">FM</span><span><strong>Capital Exchange</strong><small>XYENA marketplace</small></span></a><nav aria-label="Marketplace operations">${navigation.map(([key, href, label]) => `<a class="nav-link ${page === key ? "active" : ""}" href="${href}">${label}</a>`).join("")}</nav><div class="authority-card"><span>Commitment boundary</span><strong>Reserve capacity, not money</strong><p>Only an exact Guardian-authorized commitment can reach the execution gateway.</p></div>`;
}

function renderOverview(data) {
  setText("activePrograms", data.summary.active_programs);
  setText("availableCapacity", money(data.summary.available_capacity));
  setText("reviewQueue", data.summary.applications_under_review);
  setText("liveOffers", data.summary.live_offers);
  const best = data.offers.find((offer) => ["ISSUED", "RESERVED"].includes(offer.status)) || data.offers[0];
  if (best) {
    setText("railFunder", best.funder_name || best.funder_id); setText("railAmount", money(best.approved_amount));
    setText("railAdvance", `${Number(best.advance_rate).toFixed(1)}%`); setText("railRate", `${Number(best.annual_rate).toFixed(2)}%`);
    setText("railFee", money(best.fee_amount)); setText("railTenor", `${best.tenor_days} days`); setText("railExpiry", date(best.expires_at));
  }
  const queue = byId("applicationQueue");
  if (queue) queue.innerHTML = data.applications.slice(0, 4).map((value) => `<div class="record"><div><strong>${escapeHtml(value.msme_name)}</strong><p>${escapeHtml(value.case_id)} · ${value.tenor_days} days · ${escapeHtml(value.industry)}</p></div><div class="amount">${money(value.requested_amount)}<small>${badge(value.status)}</small></div></div>`).join("") || '<p class="empty">No marketplace applications.</p>';
  renderCapacity(data);
}

function renderCapacity(data) {
  const list = byId("capacityList"); if (!list) return;
  list.innerHTML = data.programs.map((value) => {
    const used = Number(value.reserved_capacity) + Number(value.committed_capacity);
    const percent = Math.min(100, Math.round((used / Number(value.total_capacity)) * 100));
    return `<li><div class="capacity-line"><span><strong>${escapeHtml(value.program_code)}</strong><small>${escapeHtml(value.funder_name || "")}</small></span><span class="mono">${money(value.available_capacity)}</span></div><div class="bar ${percent > 75 ? "warn" : ""}"><i style="width:${percent}%"></i></div></li>`;
  }).join("");
}

function renderFunders(data) {
  setText("funderCount", data.funders.length); setText("activeFunderCount", data.funders.filter((value) => value.status === "ACTIVE").length);
  const rows = byId("funderRows"); if (!rows) return;
  rows.innerHTML = data.funders.map((value) => `<tr><td><strong>${escapeHtml(value.display_name)}</strong><small>${escapeHtml(value.legal_name)}</small></td><td>${escapeHtml(value.institution_type)}</td><td>${value.supported_rails.map(escapeHtml).join(", ")}</td><td>${value.policy_metadata.review_sla_hours || "—"} hours</td><td>${badge(value.status)}</td><td class="mono">v${value.version}</td></tr>`).join("");
}

function renderPrograms(data) {
  setText("programCount", data.programs.length); setText("programCapacity", money(data.summary.available_capacity));
  const rows = byId("programRows"); if (rows) rows.innerHTML = data.programs.map((value) => `<tr><td><strong>${escapeHtml(value.name)}</strong><small>${escapeHtml(value.program_code)} · policy v${value.policy_version}</small></td><td>${escapeHtml(value.funder_name || value.funder_id)}</td><td>${money(value.minimum_amount)}–${money(value.maximum_amount)}</td><td>${Number(value.advance_rate_maximum).toFixed(0)}%</td><td>${value.tenor_minimum_days}–${value.tenor_maximum_days} days</td><td>${money(value.available_capacity)}</td><td>${badge(value.status)}</td></tr>`).join("");
  const rules = byId("ruleList"); if (rules) rules.innerHTML = data.programs.flatMap((program) => program.rules.map((rule) => `<div class="record"><div><strong>${escapeHtml(rule.rule_key.replaceAll("_", " "))}</strong><p>${escapeHtml(rule.input_field)} ${escapeHtml(rule.operator)} · ${escapeHtml(rule.reason_code)}</p></div><span class="mono">v${rule.version}</span></div>`)).join("") || '<p class="empty">No active rules.</p>';
}

function renderApplications(data) {
  setText("applicationCount", data.applications.length); setText("applicationReview", data.summary.applications_under_review);
  const rows = byId("applicationRows"); if (!rows) return;
  rows.innerHTML = data.applications.map((value) => `<tr><td><strong>${escapeHtml(value.msme_name)}</strong><small>${escapeHtml(value.case_id)}</small></td><td>${money(value.requested_amount)}</td><td>${value.tenor_days} days</td><td>${escapeHtml(value.region)}<small>${escapeHtml(value.industry)}</small></td><td>${value.evidence_receipt_ids.length} receipts</td><td>${badge(value.status)}</td><td class="mono">v${value.version}</td></tr>`).join("");
}

function renderOffers(data) {
  setText("offerCount", data.offers.length); setText("issuedOffers", data.offers.filter((value) => value.status === "ISSUED").length);
  const rows = byId("offerRows"); if (rows) rows.innerHTML = data.offers.map((value) => `<tr><td><strong>${escapeHtml(value.funder_name || value.funder_id)}</strong><small>${escapeHtml(value.program_name || value.program_id)}</small></td><td>${escapeHtml(value.msme_name || value.application_id)}</td><td>${money(value.approved_amount)}</td><td>${Number(value.annual_rate).toFixed(2)}%</td><td>${money(value.fee_amount)}</td><td>${value.tenor_days} days</td><td>${date(value.expires_at)}</td><td>${badge(value.status)}</td></tr>`).join("");
  const comparison = byId("comparisonRows"); if (comparison) comparison.innerHTML = data.offers.filter((value) => value.application_id === data.offers[0]?.application_id).map((value) => `<tr><td><strong>${escapeHtml(value.funder_name || value.funder_id)}</strong></td><td>${money(value.approved_amount)}</td><td>${Number(value.advance_rate).toFixed(1)}%</td><td>${Number(value.annual_rate).toFixed(2)}%</td><td>${money(value.fee_amount)}</td><td>${value.tenor_days} days</td><td>${badge(value.status)}</td></tr>`).join("");
}

function renderReservations(data) {
  setText("reservationCount", data.reservations.length); setText("activeReservations", data.summary.active_reservations);
  const rows = byId("reservationRows"); if (!rows) return;
  rows.innerHTML = data.reservations.map((value) => `<tr><td><strong>${escapeHtml(value.id)}</strong><small>${escapeHtml(value.offer_id)}</small></td><td>${escapeHtml(value.case_id)}</td><td>${money(value.reserved_amount)}</td><td>${date(value.expires_at)}</td><td>${badge(value.status)}</td><td>${escapeHtml(value.commit_reference || value.release_reference || "—")}</td><td class="mono">v${value.version}</td></tr>`).join("");
}

function renderCommitments(data) {
  setText("commitmentCount", data.commitments.length); setText("committedValue", money(data.summary.committed_value));
  const rows = byId("commitmentRows"); if (!rows) return;
  rows.innerHTML = data.commitments.map((value) => `<tr><td><strong>${escapeHtml(value.id)}</strong><small>${escapeHtml(value.reservation_id)}</small></td><td>${money(value.committed_amount)}</td><td>${badge(value.status)}</td><td>${escapeHtml(value.guardian_authorization_id || "Awaiting Guardian")}</td><td>${escapeHtml(value.execution_reference || "—")}</td><td>${badge(value.settlement_status)}</td><td class="mono">v${value.version}</td></tr>`).join("");
}

function renderExposure(data) {
  setText("exposureCommitted", money(data.summary.committed_value)); setText("exposureAvailable", money(data.summary.available_capacity));
  renderCapacity(data);
  const rows = byId("exposureRows"); if (!rows) return;
  rows.innerHTML = data.programs.map((value) => `<tr><td><strong>${escapeHtml(value.name)}</strong><small>${escapeHtml(value.funder_name || "")}</small></td><td>${money(value.total_capacity)}</td><td>${money(value.reserved_capacity)}</td><td>${money(value.committed_capacity)}</td><td>${money(value.available_capacity)}</td><td>${badge(value.status)}</td></tr>`).join("");
}

function renderActivity(data) {
  setText("auditCount", data.audit_events.length); setText("outboxCount", data.summary.pending_outbox_events);
  const timeline = byId("timeline"); if (!timeline) return;
  timeline.innerHTML = data.audit_events.map((value) => `<li><strong>${escapeHtml(value.event_type.replaceAll("_", " "))}</strong><small>${escapeHtml(value.aggregate_type)} · ${escapeHtml(value.aggregate_id)} · v${value.aggregate_version}</small><small>${escapeHtml(value.actor_type)} ${escapeHtml(value.actor_id)} · ${date(value.occurred_at)} · ${escapeHtml(value.correlation_id)}</small></li>`).join("") || '<li><strong>No audit events recorded.</strong></li>';
}

function renderTools() { const grid = byId("toolGrid"); if (grid) grid.innerHTML = tools.map(([name, type]) => `<div class="tool"><code>${name}</code><small>${type}</small></div>`).join(""); }
function render(data) { renderOverview(data); renderFunders(data); renderPrograms(data); renderApplications(data); renderOffers(data); renderReservations(data); renderCommitments(data); renderExposure(data); renderActivity(data); renderTools(); setText("tenantId", data.tenant_id); }
function connection(state, text) { const node = byId("disconnect"); if (node) { node.dataset.state = state; node.disabled = state !== "ready"; } setText("connectionLabel", text); }

async function loadData(token, automatic = false) {
  const form = byId("accessForm"); const button = form?.querySelector("button"); const message = byId("accessMessage"); const label = button?.textContent;
  if (button) { button.disabled = true; button.textContent = "Loading…"; } if (message) { message.classList.remove("error"); message.textContent = "Loading the tenant-scoped marketplace."; }
  try {
    const response = await fetch("/api/v1/dashboard", { headers: { "X-Funder-UI-Token": token } });
    if (!response.ok) throw new Error(response.status === 401 ? "The marketplace token was not accepted." : `The marketplace API returned ${response.status}.`);
    const data = await response.json(); render(data); sessionStorage.setItem("xyena-funder-ui-token", token); byId("access")?.classList.add("connected"); connection("ready", "Marketplace connected");
  } catch (error) { sessionStorage.removeItem("xyena-funder-ui-token"); connection("error", "Connection failed"); if (message) { message.classList.add("error"); message.textContent = error.message; } if (automatic) byId("access")?.classList.remove("connected"); }
  finally { if (button) { button.disabled = false; button.textContent = label; } }
}

byId("accessForm")?.addEventListener("submit", (event) => { event.preventDefault(); loadData(byId("token").value); });
byId("disconnect")?.addEventListener("click", () => { sessionStorage.removeItem("xyena-funder-ui-token"); location.reload(); });
mountSidebar(); renderTools();
const saved = sessionStorage.getItem("xyena-funder-ui-token");
if (byId("token")) byId("token").value = saved || DEMO_UI_TOKEN;
if (saved) loadData(saved, true);
