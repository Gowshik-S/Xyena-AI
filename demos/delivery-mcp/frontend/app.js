const DeliveryApp = (() => {
  const storageKey = "xyena_delivery_role_token";
  let token = localStorage.getItem(storageKey) || "";
  let session = null;
  let detail = null;
  let stream = null;

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const money = value => new Intl.NumberFormat("en-IN", {style:"currency", currency:"INR", maximumFractionDigits:0}).format(Number(value || 0));
  const dateTime = value => value ? new Intl.DateTimeFormat("en-IN", {dateStyle:"medium", timeStyle:"short"}).format(new Date(value)) : "—";
  const statusClass = value => /DELIVERED$|ACCEPTED|VERIFIED/.test(value) ? "good" : /FAILED|REJECTED|CANCELLED|MISMATCH/.test(value) ? "bad" : "warn";
  const badge = value => `<span class="badge ${statusClass(value || "")}">${escapeHtml(String(value || "UNKNOWN").replaceAll("_", " "))}</span>`;

  async function api(path, options = {}) {
    if (!token) throw new Error("Enter a role token to connect this console.");
    const headers = {"X-Demo-Token": token, ...(options.headers || {})};
    if (options.body && typeof options.body !== "string") {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }
    const response = await fetch(path, {...options, headers});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }

  function toast(message, isError = false) {
    q(".toast")?.remove();
    const node = document.createElement("div");
    node.className = "toast";
    if (isError) node.style.background = "#8f2d24";
    node.textContent = message;
    document.body.append(node);
    setTimeout(() => node.remove(), 4200);
  }

  function showError(error, target = "#notice") {
    const node = q(target);
    if (node) {
      node.className = "notice error";
      node.textContent = error.message || String(error);
      node.hidden = false;
    }
    toast(error.message || String(error), true);
  }

  async function connect() {
    token = q("#role-token")?.value.trim() || token;
    if (!token) return showError(new Error("A role token is required."));
    localStorage.setItem(storageKey, token);
    try {
      session = await api("/api/v1/session");
      q("#session-role").textContent = session.role.replaceAll("_", " ");
      q("#notice")?.setAttribute("hidden", "");
      toast(`Connected as ${session.actor_id}`);
      document.dispatchEvent(new CustomEvent("delivery:connected"));
      stream?.close();
      stream = new EventSource(`/api/v1/events/stream?token=${encodeURIComponent(token)}`);
      stream.addEventListener("delivery", () => document.dispatchEvent(new CustomEvent("delivery:event")));
    } catch (error) { showError(error); }
  }

  function initShell() {
    const input = q("#role-token");
    if (input) input.value = token;
    q("#connect")?.addEventListener("click", connect);
    input?.addEventListener("keydown", event => { if (event.key === "Enter") connect(); });
    if (token) connect();
  }

  async function initDashboard() {
    const load = async () => {
      try {
        const data = await api("/api/v1/dashboard");
        const inMotion = (data.counts.DISPATCHED || 0) + (data.counts.IN_TRANSIT || 0) + (data.counts.OUT_FOR_DELIVERY || 0);
        q("#metrics").innerHTML = [
          ["In motion", inMotion, "Active carrier workflow"],
          ["Awaiting acceptance", (data.counts.DELIVERED_PENDING_ACCEPTANCE || 0) + (data.counts.PARTIAL_PENDING_ACCEPTANCE || 0), "Requires proof and buyer action"],
          ["Verified value", money(data.total_accepted_value), "Accepted source value"],
          ["Exceptions", data.alerts.length, "Open operational signals"],
        ].map(([label,value,note]) => `<article class="metric"><span class="label">${label}</span><strong>${value}</strong><small>${note}</small></article>`).join("");
        q("#status-table").innerHTML = Object.entries(data.counts).sort((a,b)=>b[1]-a[1]).map(([name,count]) => `<tr><td>${badge(name)}</td><td><strong>${count}</strong></td></tr>`).join("") || `<tr><td class="empty">No deliveries</td></tr>`;
        q("#alerts").innerHTML = data.alerts.length ? data.alerts.map(a => `<div class="notice error"><strong>${escapeHtml(a.delivery_number)}</strong><br>${escapeHtml(a.type.replaceAll("_", " "))}</div>`).join("") : `<div class="empty">No open exceptions.</div>`;
        q("#audit").innerHTML = data.recent_audit_trail.length ? data.recent_audit_trail.map(a => `<div class="timeline-item"><strong>${escapeHtml(a.event_type)}</strong><span>${escapeHtml(a.actor_id)} · ${dateTime(a.occurred_at)}</span></div>`).join("") : `<div class="empty">No audit activity.</div>`;
      } catch (error) { showError(error); }
    };
    document.addEventListener("delivery:connected", load);
    document.addEventListener("delivery:event", debounce(load, 300));
    if (token) load();
  }

  async function initList() {
    const load = async () => {
      try {
        const params = new URLSearchParams();
        const search = q("#search")?.value.trim();
        const status = q("#status-filter")?.value;
        if (search) params.set("search", search);
        if (status) params.set("status", status);
        const rows = await api(`/api/v1/deliveries?${params}`);
        q("#delivery-count").textContent = `${rows.length} records`;
        q("#delivery-rows").innerHTML = rows.length ? rows.map(d => `<tr>
          <td><a class="link" href="/detail?id=${encodeURIComponent(d.id)}">${escapeHtml(d.delivery_number)}</a><br><small>${escapeHtml(d.tracking_number || "Tracking pending")}</small></td>
          <td>${escapeHtml(d.purchase_order_id)}<br><small>${escapeHtml(d.invoice_number || "No invoice")}</small></td>
          <td>${escapeHtml(d.carrier_id || "Unassigned")}</td><td>${badge(d.status)}</td>
          <td>${money(d.declared_value)}</td><td>${money(d.verified_delivered_value)}</td><td>v${d.version}</td>
        </tr>`).join("") : `<tr><td colspan="7" class="empty">No deliveries match these filters.</td></tr>`;
      } catch (error) { showError(error); }
    };
    q("#search")?.addEventListener("input", debounce(load, 250));
    q("#status-filter")?.addEventListener("change", load);
    q("#refresh")?.addEventListener("click", load);
    document.addEventListener("delivery:connected", load);
    document.addEventListener("delivery:event", debounce(load, 300));
    if (token) load();
  }

  function debounce(fn, wait) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); }; }

  const field = (name, label, type="text", value="", full=false) => `<div class="field ${full ? "full" : ""}"><label for="f-${name}">${label}</label><input id="f-${name}" name="${name}" type="${type}" value="${escapeHtml(value)}" required></div>`;
  function modal(title, fields, onSubmit, submitLabel="Confirm") {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `<form class="modal"><div class="modal-head"><h3>${escapeHtml(title)}</h3><button type="button" class="btn close">Close</button></div><div class="form-grid">${fields}</div><div class="modal-foot"><button type="button" class="btn close">Cancel</button><button class="btn primary" type="submit">${escapeHtml(submitLabel)}</button></div></form>`;
    qa(".close", backdrop).forEach(button => button.addEventListener("click", () => backdrop.remove()));
    q("form", backdrop).addEventListener("submit", async event => {
      event.preventDefault();
      const submit = q("button[type=submit]", backdrop); submit.disabled = true;
      try { await onSubmit(Object.fromEntries(new FormData(event.currentTarget))); backdrop.remove(); await loadDetail(); }
      catch (error) { submit.disabled = false; showError(error); }
    });
    document.body.append(backdrop);
  }

  async function mutate(path, body={}) {
    const result = await api(path, {method:"POST", headers:{"If-Match": String(detail.version)}, body});
    toast("Workflow updated successfully.");
    return result;
  }

  function actionButtons() {
    if (!session || !detail) return "";
    const role = session.role, state = detail.status;
    const buttons = [];
    if (["SELLER_OPERATOR","DEMO_ADMIN"].includes(role) && state === "CREATED") buttons.push(["ready","Mark ready","primary"]);
    if (["SELLER_OPERATOR","DEMO_ADMIN"].includes(role) && state === "READY_TO_DISPATCH") buttons.push(["dispatch","Dispatch","primary"]);
    if (["CARRIER_OPERATOR","DEMO_ADMIN"].includes(role) && ["DISPATCHED","IN_TRANSIT","OUT_FOR_DELIVERY","DELIVERY_FAILED"].includes(state)) buttons.push(["transit","Transit event",""]);
    if (["CARRIER_OPERATOR","DEMO_ADMIN"].includes(role) && ["IN_TRANSIT","OUT_FOR_DELIVERY"].includes(state)) buttons.push(["attempt","Delivery attempt","primary"]);
    if (["CARRIER_OPERATOR","DEMO_ADMIN"].includes(role) && ["DELIVERED_PENDING_ACCEPTANCE","PARTIAL_PENDING_ACCEPTANCE"].includes(state)) buttons.push(["proof","Capture proof",""]);
    if (role === "DELIVERY_REVIEWER" && detail.proofs.some(p => p.verification_status === "PENDING_VERIFICATION")) buttons.push(["review-proof","Review proof","primary"]);
    if (["BUYER_RECEIVER","DEMO_ADMIN"].includes(role) && ["DELIVERED_PENDING_ACCEPTANCE","PARTIAL_PENDING_ACCEPTANCE"].includes(state)) buttons.push(["accept","Buyer acceptance","primary"]);
    if (["SELLER_OPERATOR","DELIVERY_REVIEWER"].includes(role) && !["DELIVERED","PARTIALLY_ACCEPTED","REJECTED","CANCELLED"].includes(state)) buttons.push(["cancel","Cancel","danger"]);
    if (["SELLER_OPERATOR","CARRIER_OPERATOR","BUYER_RECEIVER"].includes(role)) buttons.push(["correction","Request correction",""]);
    if (role === "DELIVERY_REVIEWER" && detail.corrections.some(c => c.status === "PENDING")) buttons.push(["review-correction","Review correction",""]);
    return buttons.map(([id,label,style]) => `<button class="btn ${style}" data-action="${id}">${label}</button>`).join("") || `<span class="badge">Read-only for this role and state</span>`;
  }

  function wireActions() {
    qa("[data-action]").forEach(button => button.addEventListener("click", () => runAction(button.dataset.action)));
  }

  function quantities(prefix, sourceField) {
    return detail.items.map(item => field(`${prefix}_${item.sku}`, `${item.sku} (${sourceField}: ${item[sourceField]})`, "number", item[sourceField])).join("");
  }

  function valuesWithPrefix(values, prefix) {
    return Object.fromEntries(Object.entries(values).filter(([key]) => key.startsWith(prefix + "_")).map(([key,value]) => [key.slice(prefix.length + 1), value]));
  }

  async function runAction(action) {
    if (action === "ready") return mutate(`/api/v1/deliveries/${detail.id}/ready`).then(loadDetail);
    if (action === "dispatch") return modal("Dispatch delivery", field("carrier_id","Carrier ID","text",detail.carrier_id || "carrier_fastfreight",true) + quantities("qty","ordered_quantity"), values => mutate(`/api/v1/deliveries/${detail.id}/dispatch`, {carrier_id:values.carrier_id,item_quantities:valuesWithPrefix(values,"qty")}), "Dispatch");
    if (action === "transit") return modal("Record transit event", `<div class="field full"><label>Event</label><select name="event_type"><option>IN_TRANSIT</option><option>OUT_FOR_DELIVERY</option><option>DELIVERY_DELAYED</option><option>DELIVERY_RESUMED</option></select></div>${field("notes","Operational note","text","",true)}`, values => mutate(`/api/v1/deliveries/${detail.id}/events`, {event_type:values.event_type,notes:values.notes || null}));
    if (action === "attempt") return modal("Record delivery attempt", `<div class="field full"><label>Result</label><select name="success"><option value="true">Successful</option><option value="false">Failed</option></select></div>${quantities("delivered","dispatched_quantity")}${field("failure_reason","Failure reason (failed attempts)","text","",true)}`, values => mutate(`/api/v1/deliveries/${detail.id}/delivery-attempt`, {success:values.success === "true",item_quantities:values.success === "true" ? valuesWithPrefix(values,"delivered") : {},failure_reason:values.success === "true" ? null : values.failure_reason}));
    if (action === "proof") return modal("Capture proof metadata", `<div class="field"><label>Proof type</label><select name="proof_type"><option>SIGNATURE</option><option>PHOTO</option><option>OTP</option><option>DOCUMENT</option></select></div>${field("mime_type","MIME type","text","image/png")}${field("restricted_object_key","Restricted object key","text",`pod/${detail.id}/proof`,true)}${field("content_hash","SHA-256 content hash","text","",true)}`, values => mutate(`/api/v1/deliveries/${detail.id}/proofs`, {...values,security_flags:[]}));
    if (action === "review-proof") { const proof = detail.proofs.find(p => p.verification_status === "PENDING_VERIFICATION"); return modal("Independent proof review", `<div class="field full"><label>Decision</label><select name="verified"><option value="true">Verify</option><option value="false">Reject</option></select></div>${field("rejection_reason","Rejection reason (when rejected)","text","",true)}`, values => mutate(`/api/v1/deliveries/${detail.id}/proofs/${proof.id}/review`, {verified:values.verified === "true",rejection_reason:values.verified === "true" ? null : values.rejection_reason})); }
    if (action === "accept") { const fields = detail.items.map(i => field(`accepted_${i.sku}`,`${i.sku} accepted (delivered ${i.delivered_quantity})`,"number",i.delivered_quantity) + field(`rejected_${i.sku}`,`${i.sku} rejected`,"number","0") + field(`reason_${i.sku}`,`${i.sku} rejection reason`,"text","")).join(""); return modal("Record buyer acceptance", fields, values => mutate(`/api/v1/deliveries/${detail.id}/acceptance`, {items:detail.items.map(i=>({sku:i.sku,accepted_quantity:values[`accepted_${i.sku}`],rejected_quantity:values[`rejected_${i.sku}`],reason:values[`reason_${i.sku}`] || null}))}), "Accept quantities"); }
    if (action === "cancel") return modal("Cancel delivery", field("reason","Cancellation reason","text","",true), values => mutate(`/api/v1/deliveries/${detail.id}/cancel`, values), "Cancel delivery");
    if (action === "correction") return modal("Request controlled correction", `<div class="field"><label>Type</label><select name="correction_type"><option>REFERENCE</option><option>IDENTITY</option><option>TRACKING</option><option>ADDRESS</option></select></div>${field("field_name","Field name")}${field("field_value","Replacement value","text","",true)}${field("reason","Reason","text","",true)}`, values => mutate(`/api/v1/deliveries/${detail.id}/corrections`, {correction_type:values.correction_type,proposed_changes:{[values.field_name]:values.field_value},reason:values.reason}));
    if (action === "review-correction") { const correction = detail.corrections.find(c=>c.status === "PENDING"); return modal("Review correction", `<div class="field full"><label>Decision</label><select name="approve"><option value="true">Approve</option><option value="false">Reject</option></select></div>${field("reason","Review reason","text","",true)}`, values => mutate(`/api/v1/corrections/${correction.id}/review`, {approve:values.approve === "true",reason:values.reason || null})); }
  }

  async function loadDetail() {
    const id = new URLSearchParams(location.search).get("id");
    if (!id) return showError(new Error("No delivery ID was supplied."));
    try {
      detail = await api(`/api/v1/deliveries/${encodeURIComponent(id)}`);
      q("#detail-title").textContent = detail.delivery_number;
      q("#detail-subtitle").textContent = `${detail.purchase_order_id} · ${detail.tracking_number || "Tracking pending"}`;
      q("#detail-status").innerHTML = `${badge(detail.status)} <span class="badge">v${detail.version}</span>`;
      q("#actions").innerHTML = actionButtons();
      const meta = [["Seller",detail.seller_business_id],["Buyer",detail.buyer_id],["Carrier",detail.carrier_id || "Unassigned"],["Invoice",detail.invoice_number || "—"],["Declared value",money(detail.declared_value)],["Verified value",money(detail.verified_delivered_value)],["Dispatch",dateTime(detail.dispatch_date)],["Delivered",dateTime(detail.delivered_at)]];
      q("#metadata").innerHTML = meta.map(([label,value])=>`<div class="meta"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
      q("#item-rows").innerHTML = detail.items.map(i=>`<tr><td><strong>${escapeHtml(i.sku)}</strong><br><small>${escapeHtml(i.description)}</small></td><td>${i.ordered_quantity}</td><td>${i.dispatched_quantity}</td><td>${i.delivered_quantity}</td><td>${i.accepted_quantity}</td><td>${i.rejected_quantity}</td><td>${money(i.supported_unit_value)}</td></tr>`).join("");
      q("#timeline").innerHTML = detail.events.length ? detail.events.slice().reverse().map(e=>`<div class="timeline-item"><strong>${escapeHtml(e.event_type)}</strong><span>${escapeHtml(e.actor)} · ${dateTime(e.occurred_at)} · v${e.version}</span>${e.notes ? `<p>${escapeHtml(e.notes)}</p>` : ""}</div>`).join("") : `<div class="empty">No events.</div>`;
      q("#proofs").innerHTML = detail.proofs.length ? detail.proofs.map(p=>`<tr><td>${escapeHtml(p.proof_type)}</td><td><code>${escapeHtml(p.content_hash.slice(0,14))}…</code></td><td>${badge(p.verification_status)}</td><td>${dateTime(p.captured_at)}</td></tr>`).join("") : `<tr><td colspan="4" class="empty">No proof metadata captured.</td></tr>`;
      wireActions();
    } catch (error) { showError(error); }
  }

  function initDetail() {
    document.addEventListener("delivery:connected", loadDetail);
    document.addEventListener("delivery:event", debounce(loadDetail, 300));
    if (token) loadDetail();
  }

  return {initShell, initDashboard, initList, initDetail};
})();

document.addEventListener("DOMContentLoaded", DeliveryApp.initShell);
