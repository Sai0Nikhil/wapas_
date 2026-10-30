const $ = s => document.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const tm = iso => iso ? new Date(iso).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit",second:"2-digit"}) : "";
const STATE_LABEL = {NEW:"New",DECIDED:"Decided",SCHEDULED:"Queued",WAITING_OWNER:"Needs you",SENT:"Link sent",RECOVERED:"Recovered",STOPPED:"Stopped",BLOCKED:"Blocked",UNKNOWN:"Unknown"};
const REASON = {waiting_bank_recovery:"waiting for bank",quiet_hours:"quiet hours",gateway_retry:"Paytm error, will retry",opted_out:"opted out",duplicate:"duplicate order",reminder_cap:"reminders done, no payment",owner_amount:"above auto limit",owner_confidence:"agent not sure enough",owner_vip:"loyal customer",owner_skipped:"owner skipped",owner_timeout:"owner did not answer",gateway_unavailable:"gateway unavailable",agent_no_action:"agent: no action",agent_later:"agent: send later",learning_wait:"research arm",amount_mismatch:"amount mismatch: not credited",customer_says_paid:"says paid: checking, reminders paused",customer_debited:"says debited: owner told",customer_later:"will pay later: held",customer_other_method:"paying another way",customer_declined:"customer declined"};
const SRC = {simulated:["SIM","Simulated signal (demo data)"], "store-fake":["STORE","Store checkout · fake gateway"], paytm:["PAYTM","Paytm checkout (test env)"]};
let selected = null, faults = {}, lastWaves = null, env = "", tab = "ops", activeSession = null;
let sessionPromise = null;

async function getActiveSession() {
  if (activeSession) return activeSession;
  if (!sessionPromise) sessionPromise = fetch("/api/auth/session", {credentials:"same-origin", cache:"no-store"})
    .then(async response => response.ok ? response.json() : null)
    .then(data => {
      if (!data || !data.authenticated) {
        window.location.replace("/login");
        throw new Error("Sign-in required");
      }
      activeSession = data;
      const shop = "/s/" + encodeURIComponent(data.store_slug);
      document.querySelectorAll("#shop-link, #shop-link-orders").forEach(link => link.href = shop);
      const ownerOnlyTabs = ["ops", "khata", "sound", "staff", "trust", "research"];
      if (data.role !== "OWNER") {
        const pulse = document.querySelector("#opportunity-pulse-panel");
        if (pulse) pulse.hidden = true;
        ownerOnlyTabs.forEach(name => {
          const button = document.querySelector(`.tab[data-tab="${name}"]`);
          if (button) button.hidden = true;
        });
        document.querySelectorAll("[data-tab='ops'], [data-tab='khata'], [data-tab='sound'], [data-tab='staff'], [data-tab='trust'], [data-tab='research']")
          .forEach(button => { if (button.classList.contains("on")) button.classList.remove("on"); });
        document.querySelectorAll("[data-pane='ops'], [data-pane='khata'], [data-pane='sound'], [data-pane='staff'], [data-pane='trust'], [data-pane='research']")
          .forEach(pane => pane.hidden = true);
        tab = "counter";
        document.querySelector(".tab[data-tab='counter']")?.classList.add("on");
        document.querySelector("[data-pane='counter']")?.removeAttribute("hidden");
        const qr = document.querySelector("#store-qr-verify")?.closest(".panel");
        if (qr) qr.hidden = true;
      }
      fetch("/api/auth/memberships", {credentials:"same-origin", cache:"no-store"})
        .then(r => r.ok ? r.json() : null)
        .then(mdata => {
          if (mdata && mdata.memberships && mdata.memberships.length > 1) {
            const switcher = document.querySelector("#store-switcher");
            if (switcher) {
              switcher.style.display = "inline-block";
              switcher.innerHTML = mdata.memberships.map(m =>
                `<option value="${esc(m.id)}" ${m.id === data.membership_id ? "selected" : ""}>${esc(m.merchant_name)} · ${esc(m.store_name)}</option>`
              ).join("");
              switcher.onchange = async () => {
                const targetId = switcher.value;
                if (!targetId || targetId === data.membership_id) return;
                try {
                  await api("/api/auth/switch-membership", {method: "POST", body: {membership_id: targetId}});
                  window.location.reload();
                } catch (e) {
                  alert("Failed to switch store: " + e.message);
                }
              };
            }
          }
        }).catch(() => {});
      return activeSession;
    });
  return sessionPromise;

}

async function api(path, opts={}) {
  const method = (opts.method || "GET").toUpperCase();
  const identity = await getActiveSession();
  const headers = {"Content-Type":"application/json"};
  if (!(["GET", "HEAD", "OPTIONS"].includes(method))) headers["X-Wapas-CSRF"] = identity.csrf_token;
  const r = await fetch(path, {method, credentials:"same-origin", headers, body: opts.body ? JSON.stringify(opts.body) : undefined});
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m } catch(e){}; throw new Error(m); }
  return r.json();
}

async function uploadApi(path, formData) {
  const identity = await getActiveSession();
  const r = await fetch(path, {method:"POST", credentials:"same-origin",
    headers:{"X-Wapas-CSRF":identity.csrf_token}, body:formData});
  if (!r.ok) { let message = r.statusText; try { message = (await r.json()).detail || message; } catch(e){}; throw new Error(message); }
  return r.json();
}

// ---------------------------------------------------------------- tabs
document.querySelectorAll(".tab[data-tab]").forEach(b => b.onclick = () => {
  tab = b.dataset.tab;
  document.querySelectorAll(".tab[data-tab]").forEach(x => x.classList.toggle("on", x === b));
  document.querySelectorAll("[data-pane]").forEach(p => p.hidden = p.dataset.pane !== tab);
  if (tab === "counter") loadCounter();
  if (tab === "inventory") loadCatalog();
  if (tab === "khata") loadKhata();
  if (tab === "sound") pollSound();
  if (tab === "staff") loadStaff();
  if (tab === "trust") loadProof();
  if (tab === "research") loadLearning();
});

// ---------------------------------------------------------------- catalogue and stock
function moneyToPaise(value) {
  const m = String(value).trim().match(/^(\d+)(?:\.(\d{1,2}))?$/);
  if (!m) throw new Error("Enter a price with up to two decimal places");
  return Number(m[1]) * 100 + Number((m[2] || "").padEnd(2, "0"));
}

async function loadCatalog() {
  try {
    const products = await api("/api/merchant/catalog/products");
    const body = $("#catalog-rows");
    $("#catalog-empty").style.display = products.length ? "none" : "block";
    body.innerHTML = products.map(p => `<tr>
      <td><b>${esc(p.name)}</b><div class="muted">${esc(p.sku)}${p.barcode ? ` · ${esc(p.barcode)}` : ""} · ${esc(p.unit)}</div></td>
      <td class="num">₹${esc(p.price_fmt)}</td><td class="num">${esc(p.on_hand)}</td>
      <td class="num">${esc(p.reserved)}</td><td class="num">${esc(p.available)}</td>
      <td><span class="stock-state ${esc(p.stock_state.toLowerCase())}">${esc(p.stock_state.replace("_", " "))}</span></td>
    </tr>`).join("");
    $("#stock-product").innerHTML = products.length
      ? products.map(p => `<option value="${esc(p.id)}">${esc(p.name)} · ${esc(p.available)} ${esc(p.unit)} available</option>`).join("")
      : `<option value="">Add a product first</option>`;

    const names = Object.fromEntries(products.map(p => [p.id, p.name]));
    const movements = await api("/api/merchant/catalog/movements?limit=40");
    $("#movement-empty").style.display = movements.length ? "none" : "block";
    $("#movement-rows").innerHTML = movements.map(m => `<tr>
      <td>${tm(m.created_at)}</td><td>${esc(names[m.product_id] || m.product_id)}</td>
      <td>${esc(m.kind.replaceAll("_", " "))}</td><td class="num">${Number(m.on_hand_delta) > 0 ? "+" : ""}${esc(m.on_hand_delta)}</td>
      <td>${esc(m.reason || m.source_ref)}</td>
    </tr>`).join("");
    await loadOrders();
    if (activeSession?.role === "OWNER") await loadStoreQR();
    if (activeSession?.role === "OWNER") await loadOpportunityPulse();
  } catch (e) {
    $("#catalog-empty").textContent = e.message || "Could not load the saved catalogue";
    $("#catalog-empty").style.display = "block";
  }
}

async function loadOpportunityPulse() {
  const root = $("#opportunity-pulse");
  try {
    const pulse = await api("/api/merchant/opportunities/pulse?days=30");
    let summaryHtml = "";
    if (pulse.financial_breakdown || pulse.low_stock_summary || pulse.khata_summary) {
      const fb = pulse.financial_breakdown || {};
      const ls = pulse.low_stock_summary || {};
      const kh = pulse.khata_summary || {};
      const pf = pulse.pending_fulfillment_summary || {};
      summaryHtml = `<div class="pulse-indicators" style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap;">
        <span class="indicator-chip" style="background:var(--bg-subtle,#f1f5f9);padding:6px 12px;border-radius:6px;font-size:13px;">Low stock items: <b>${esc(ls.low_stock_count ?? 0)}</b></span>
        <span class="indicator-chip" style="background:var(--bg-subtle,#f1f5f9);padding:6px 12px;border-radius:6px;font-size:13px;">Verified sales (${pulse.window_days}d): <b>₹${((fb.verified_collected_total_paise ?? 0)/100).toFixed(2)}</b> (${esc(fb.verified_collected_count ?? 0)})</span>
        <span class="indicator-chip" style="background:var(--bg-subtle,#f1f5f9);padding:6px 12px;border-radius:6px;font-size:13px;">Khata outstanding: <b>₹${((kh.outstanding_total_paise ?? 0)/100).toFixed(2)}</b> (${esc(kh.customer_count ?? 0)} customers)</span>
        <span class="indicator-chip" style="background:var(--bg-subtle,#f1f5f9);padding:6px 12px;border-radius:6px;font-size:13px;">Pending fulfillment: <b>${esc(pf.pending_count ?? 0)}</b></span>
      </div>`;
    }
    if (!pulse.insights.length) {
      root.innerHTML = `${summaryHtml}<p class="empty">${esc(pulse.message)}</p>`;
      return;
    }
    root.innerHTML = `${summaryHtml}<div class="opportunity-list">${pulse.insights.map(item => `
      <article class="opportunity-item"><div class="panel-head"><b>${esc(item.query)}</b><span class="stock-state">${esc(item.outcome.replaceAll("_", " "))}</span></div>
      <p>${esc(item.sample_count)} searches in ${esc(item.window_days)} days · ${esc(item.provenance)}</p>
      <p class="muted">${esc(item.uncertainty)}</p><p>${esc(item.suggested_next_action)}</p>
      <small>First: ${esc(item.first_seen || "—")} · Last: ${esc(item.last_seen || "—")}</small></article>`).join("")}</div>`;
  } catch (e) { root.innerHTML = `<p class="empty">Could not load recorded search outcomes: ${esc(e.message)}</p>`; }
}

$("#opportunity-refresh").onclick = loadOpportunityPulse;

// ---------------------------------------------------------------- Sarkar typed tools and turn-based voice input
let sarkarRecorder = null, sarkarStream = null, sarkarChunks = [];
function renderSarkar(result) {
  const root = $("#sarkar-result");
  const data = result.data ? `<details><summary>Saved records read by Sarkar</summary><pre>${esc(JSON.stringify(result.data, null, 2))}</pre></details>` : "";
  const transcript = result.transcript ? `<p class="muted">Recognized speech: ${esc(result.transcript)}</p>` : "";
  const trace = result.tool_trace?.length ? `<details><summary>Typed tool trace</summary><pre>${esc(JSON.stringify(result.tool_trace.map(x => ({tool:x.tool, arguments:x.arguments})), null, 2))}</pre></details>` : "";
  let confirmation = "";
  if (result.confirmation) {
    const action = result.confirmation;
    confirmation = `<div class="appr"><p><b>Review:</b> add ${esc(action.quantity)} ${esc(action.unit)} to ${esc(action.product_name)}. Available now: ${esc(action.available_before)} ${esc(action.unit)}. Expires ${esc(new Date(action.expires_at).toLocaleTimeString())}.</p><button class="btn" id="sarkar-confirm-stock" type="button">Confirm stock receipt</button></div>`;
    setTimeout(() => {
      const button = $("#sarkar-confirm-stock");
      if (button) button.onclick = async () => {
        if (!window.confirm(`Confirm adding ${action.quantity} ${action.unit} to ${action.product_name}? This will create a stock movement.`)) return;
        button.disabled = true;
        try { renderSarkar(await api(`/api/merchant/sarkar/actions/${encodeURIComponent(action.action_id)}/confirm`, {method:"POST", body:{confirmation_token:action.token}})); }
        catch (e) { $("#sarkar-status").textContent = e.message; button.disabled = false; }
      };
    }, 0);
  }
  root.innerHTML = `<article class="sarkar-answer"><b>${esc(result.status || "ANSWERED")} · ${esc(result.engine || "Sarkar")}</b><p>${esc(result.message || "")}</p>${transcript}${confirmation}${data}${trace}</article>`;
}

async function sendSarkar(body) {
  const status = $("#sarkar-status");
  status.textContent = "Sarkar is checking saved store records…";
  try { renderSarkar(await api("/api/merchant/sarkar/ask", {method:"POST", body})); status.textContent = "Turn-based response. Voice requests are transcribed before the same typed tools run."; }
  catch (e) { status.textContent = e.message || "Sarkar could not complete that request."; }
}

$("#sarkar-form").onsubmit = async e => {
  e.preventDefault();
  const message = e.currentTarget.elements.message.value.trim();
  if (!message) { $("#sarkar-status").textContent = "Type a request or record a voice turn."; return; }
  await sendSarkar({message});
};

$("#sarkar-record").onclick = async () => {
  const status = $("#sarkar-status");
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    status.textContent = "Voice recording is not supported here. Type the request instead.";
    return;
  }
  try {
    sarkarStream = await navigator.mediaDevices.getUserMedia({audio:true});
    sarkarChunks = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
    sarkarRecorder = new MediaRecorder(sarkarStream, {mimeType:mime});
    sarkarRecorder.ondataavailable = event => { if (event.data.size) sarkarChunks.push(event.data); };
    sarkarRecorder.onstop = async () => {
      const blob = new Blob(sarkarChunks, {type:sarkarRecorder.mimeType || mime});
      sarkarStream?.getTracks().forEach(track => track.stop());
      sarkarStream = null;
      $("#sarkar-record").hidden = false; $("#sarkar-stop").hidden = true;
      if (!blob.size) { status.textContent = "No audio was recorded. Type the request instead."; return; }
      const reader = new FileReader();
      reader.onload = () => sendSarkar({audio_base64:String(reader.result).split(",")[1], mime_type:blob.type});
      reader.onerror = () => { status.textContent = "Could not read the recording. Type the request instead."; };
      reader.readAsDataURL(blob);
    };
    sarkarRecorder.start();
    $("#sarkar-record").hidden = true; $("#sarkar-stop").hidden = false;
    status.textContent = "Recording. Speak a short request, then choose Stop and send.";
  } catch (e) { status.textContent = "Microphone access was unavailable. Type the request instead."; }
};

$("#sarkar-stop").onclick = () => {
  if (sarkarRecorder?.state === "recording") sarkarRecorder.stop();
};

async function loadStoreQR() {
  const status = await api("/api/merchant/storefront/qr");
  $("#store-qr-message").textContent = status.message;
  $("#store-qr-result").hidden = !status.ready;
  if (status.ready) {
    $("#store-qr-image").src = status.qr_path + "?v=" + encodeURIComponent(status.verified_at || "");
    $("#store-qr-link").href = status.store_url;
    $("#store-qr-link").textContent = status.store_url;
  }
}

$("#store-qr-verify").onclick = async () => {
  const button = $("#store-qr-verify");
  button.disabled = true;
  $("#store-qr-message").textContent = "Checking the configured public address…";
  try { await api("/api/merchant/storefront/qr/verify", {method:"POST"}); await loadStoreQR(); }
  catch (e) { $("#store-qr-message").textContent = e.message || "Could not verify the storefront"; }
  finally { button.disabled = false; }
};

async function loadOrders() {
  const orders = await api("/api/merchant/orders?limit=40");
  $("#store-orders-empty").style.display = orders.length ? "none" : "block";
  $("#store-order-rows").innerHTML = orders.map(order => `<tr>
    <td><b>${esc(order.id)}</b><div class="muted">${tm(order.created_at)}</div></td>
    <td>${order.lines.map(line => `${esc(line.quantity)} ${esc(line.unit)} ${esc(line.name)}`).join("<br>")}</td>
    <td><span class="stock-state ${esc(order.status.toLowerCase())}">${esc(order.status.replaceAll("_", " "))}</span></td>
    <td>${esc(order.fulfillment_state.replaceAll("_", " "))}</td><td class="num">₹${esc(order.amount_fmt)}</td>
    <td>${order.status === "PAID" && order.fulfillment_state !== "FULFILLED" ? `<button class="btn ghost sm" data-fulfill="${esc(order.id)}">Mark fulfilled</button>` : ""}</td>
  </tr>`).join("");
  document.querySelectorAll("[data-fulfill]").forEach(button => button.onclick = async () => {
    if (!window.confirm(`Confirm that order ${button.dataset.fulfill} has been handed to the customer?`)) return;
    try { await api(`/api/merchant/orders/${encodeURIComponent(button.dataset.fulfill)}/fulfill`, {method:"POST", body:{confirm:true}}); loadOrders(); }
    catch (e) { alert(e.message); }
  });
}

$("#catalog-create").onsubmit = async e => {
  e.preventDefault();
  const f = e.currentTarget.elements;
  const msg = $("#catalog-create-msg");
  msg.textContent = "";
  try {
    const product = await api("/api/merchant/catalog/products", {method:"POST", body:{
      name:f.name.value, category:f.category.value, sku:f.sku.value, barcode:f.barcode.value,
      unit:f.unit.value, unit_price_paise:moneyToPaise(f.price.value),
      opening_stock:f.opening_stock.value || "0", low_stock_threshold:f.low_stock_threshold.value || "0",
    }});
    e.currentTarget.reset();
    msg.textContent = `${product.name} saved.`;
    loadCatalog();
  } catch (err) { msg.textContent = err.message; }
};

$("#stock-adjust").onsubmit = async e => {
  e.preventDefault();
  const f = e.currentTarget.elements;
  const msg = $("#stock-adjust-msg");
  msg.textContent = "";
  if (!f.product_id.value) { msg.textContent = "Add a product first."; return; }
  const key = f.idempotency_key.value || ("stock_" + (crypto.randomUUID ? crypto.randomUUID() : Date.now() + Math.random().toString(16).slice(2)));
  f.idempotency_key.value = key;
  const delta = f.delta.value.trim();
  if (!window.confirm(`Record stock change ${delta} ${f.product_id.selectedOptions[0].text.split(" · ")[0]}?`)) return;
  try {
    const result = await api(`/api/merchant/catalog/products/${encodeURIComponent(f.product_id.value)}/stock-adjustments`, {
      method:"POST", body:{delta, reason:f.reason.value, idempotency_key:key},
    });
    msg.textContent = `Saved. Available stock: ${result.product.available} ${result.product.unit}.`;
    f.delta.value = ""; f.reason.value = "";
    f.idempotency_key.value = "";
    loadCatalog();
  } catch (err) { msg.textContent = err.message; }
};

$("#catalog-refresh").onclick = loadCatalog;

// ---------------------------------------------------------------- counter bills
let counterProducts = [], currentBill = null, counterCreateKey = "";
const newIdempotencyKey = prefix => prefix + (window.crypto?.randomUUID ? window.crypto.randomUUID() : Date.now() + Math.random().toString(16).slice(2));
const paiseFormat = value => `${Math.floor(value / 100).toLocaleString("en-IN")}.${String(value % 100).padStart(2, "0")}`;

async function loadCounter() {
  try {
    counterProducts = (await api("/api/merchant/catalog/products")).filter(p => p.status === "ACTIVE");
    $("#counter-product-select").innerHTML = counterProducts.length
      ? counterProducts.map(p => `<option value="${esc(p.id)}">${esc(p.name)} · ₹${esc(p.price_fmt)} · ${esc(p.available)} ${esc(p.unit)} available</option>`).join("")
      : `<option value="">Add products in Catalogue &amp; stock</option>`;
    updateCounterPrice();
    if (!currentBill) {
      const bills = await api("/api/merchant/bills?limit=30");
      const draft = bills.find(b => b.state === "DRAFT");
      if (draft) renderCounter(draft);
    }
  } catch (e) {
    $("#counter-status").textContent = e.message || "Could not load the Counter";
  }
}

function updateCounterPrice() {
  const p = counterProducts.find(x => x.id === $("#counter-product-select").value);
  $("#counter-selected-price").textContent = p ? `₹${p.price_fmt} per ${p.unit}` : "";
}

function renderCounter(bill) {
  currentBill = bill;
  $("#counter-empty").hidden = true;
  $("#counter-workspace").hidden = false;
  $("#counter-number").textContent = `${bill.bill_number} · revision ${bill.revision}`;
  $("#counter-state").textContent = bill.state;
  $("#counter-total").textContent = `₹${bill.total_fmt}`;
  $("#counter-payment").textContent = `Payment state: ${bill.payment_state} · Khata: ${bill.khata_state || "NOT_ON_KHATA"}`;
  const editable = bill.state === "DRAFT";
  $("#counter-add-product").hidden = !editable;
  $("#counter-barcode").hidden = !editable;
  $("#counter-inputs").hidden = !editable;
  $("#counter-issue").hidden = !editable;
  const canCancel = editable || (bill.state === "ISSUED" && !["PAID", "PENDING"].includes(bill.payment_state) && bill.khata_state !== "ON_KHATA");
  $("#counter-cancel").hidden = !canCancel;
  $("#counter-cancel").textContent = editable ? "Cancel draft" : "Void issued bill";
  $("#counter-khata").hidden = editable || bill.state !== "ISSUED" || bill.khata_state === "ON_KHATA" || !bill.customer_phone;
  const canCollect = !editable && bill.state === "ISSUED" && bill.payment_state !== "PAID";
  $("#counter-collection").hidden = !canCollect;
  $("#counter-payment-request").textContent = bill.payment_status === "INIT_UNKNOWN"
    ? "Retry / resolve payment link" : "Create payment link";
  const paymentLink = $("#counter-payment-url");
  const hasOpenLink = bill.payment_url && ["INIT_UNKNOWN", "PENDING", "PENDING_RECONCILIATION"].includes(bill.payment_status);
  paymentLink.hidden = !hasOpenLink;
  paymentLink.href = hasOpenLink ? bill.payment_url : "#";
  paymentLink.textContent = bill.payment_provider === "fake" ? "Open simulated payment link ↗" : "Open Paytm payment link ↗";
  $("#counter-lines").innerHTML = bill.lines.map(line => `<tr>
    <td><b>${esc(line.name)}</b><div class="muted">${esc(line.sku)} · ${esc(line.unit)}</div></td>
    <td class="num">${esc(line.quantity)}</td><td class="num">₹${paiseFormat(line.unit_price_paise)}</td>
    <td class="num">₹${esc(line.line_total_fmt)}</td>
    <td>${editable ? `<button class="btn ghost sm" data-line-remove="${esc(line.id)}">Remove</button>` : ""}</td>
  </tr>`).join("");
  document.querySelectorAll("[data-line-remove]").forEach(button => button.onclick = async () => {
    try { renderCounter(await api(`/api/merchant/bills/${encodeURIComponent(bill.id)}/lines/${encodeURIComponent(button.dataset.lineRemove)}`, {method:"DELETE"})); }
    catch (e) { $("#counter-status").textContent = e.message; }
  });
}

$("#counter-product-select").onchange = updateCounterPrice;
$("#counter-start").onclick = async () => {
  const button = $("#counter-start");
  if (!counterCreateKey) counterCreateKey = newIdempotencyKey("counter_");
  button.disabled = true;
  try {
    const customerName = $("#counter-customer-name").value.trim();
    const customerPhone = $("#counter-customer-phone").value.trim();
    if (customerPhone && !/^[6-9]\d{9}$/.test(customerPhone)) throw new Error("Enter a valid 10-digit customer phone for Khata.");
    const bill = await api("/api/merchant/bills", {method:"POST", body:{idempotency_key:counterCreateKey,
      customer_name:customerName, customer_phone:customerPhone}});
    currentBill = bill; counterCreateKey = ""; renderCounter(bill);
  } catch (e) { $("#counter-status").textContent = e.message; }
  finally { button.disabled = false; }
};

$("#counter-payment-request").onclick = async () => {
  if (!currentBill || currentBill.state !== "ISSUED") return;
  const msg = $("#counter-payment-message");
  msg.textContent = "";
  const button = $("#counter-payment-request");
  button.disabled = true;
  try {
    const activeAttempt = ["INIT_UNKNOWN", "PENDING", "PENDING_RECONCILIATION"].includes(currentBill.payment_status);
    const key = (activeAttempt && currentBill.payment_idempotency_key) || newIdempotencyKey("counter_link_");
    const result = await api(`/api/merchant/bills/${encodeURIComponent(currentBill.id)}/payments`, {
      method:"POST", body:{idempotency_key:key},
    });
    currentBill = await api(`/api/merchant/bills/${encodeURIComponent(currentBill.id)}`);
    renderCounter(currentBill);
    msg.textContent = result.mode === "SIMULATED"
      ? "Simulated collection link created. It is not a real payment."
      : result.checkout_url ? "Paytm collection link created. Payment remains pending until the server verifies it."
      : "The request is unresolved. Retry to check the same provider request; no payment is recorded.";
  } catch (e) { msg.textContent = e.message || "Could not create a payment link."; }
  finally { button.disabled = false; }
};

$("#counter-khata").onclick = async () => {
  if (!currentBill || currentBill.state !== "ISSUED" || !currentBill.customer_phone) return;
  if (!window.confirm(`Add ₹${currentBill.total_fmt} as credit owed by ${currentBill.customer_name || currentBill.customer_phone}? This does not record a payment.`)) return;
  try {
    const result = await api(`/api/merchant/bills/${encodeURIComponent(currentBill.id)}/khata`, {method:"POST", body:{}});
    currentBill = await api(`/api/merchant/bills/${encodeURIComponent(currentBill.id)}`);
    renderCounter(currentBill);
    $("#counter-status").textContent = `Added to Khata. Outstanding: ₹${result.account.outstanding_fmt}. Payment remains not recorded.`;
    loadKhata();
  } catch (e) { $("#counter-status").textContent = e.message; }
};

$("#counter-add-product").onsubmit = async e => {
  e.preventDefault();
  if (!currentBill || currentBill.state !== "DRAFT") return;
  const f = e.currentTarget.elements, productId = f.product_id.value;
  try {
    const bill = await api(`/api/merchant/bills/${encodeURIComponent(currentBill.id)}/lines/${encodeURIComponent(productId)}`, {
      method:"PUT", body:{quantity:f.quantity.value},
    });
    $("#counter-add-msg").textContent = "Line saved with the current catalogue price.";
    renderCounter(bill);
  } catch (err) { $("#counter-add-msg").textContent = err.message; }
};

function updateCounterProductOptions() {
  const select = $("#counter-product-select"), query = $("#counter-catalog-search").value.trim().toLowerCase();
  const prior = select.value;
  const found = counterProducts.filter(p => !query || (p.name + " " + p.sku + " " + p.barcode).toLowerCase().includes(query));
  select.replaceChildren();
  const empty = document.createElement("option"); empty.value = "";
  empty.textContent = found.length ? "Choose a saved product" : "No matching product; add it in Catalogue";
  select.append(empty);
  found.forEach(p => {
    const option = document.createElement("option"); option.value = p.id;
    option.textContent = p.name + " · ₹" + p.price_fmt + " · " + p.available + " " + p.unit + " available";
    select.append(option);
  });
  if (found.some(p => p.id === prior)) select.value = prior;
}
$("#counter-catalog-search").oninput = updateCounterProductOptions;

function counterQuantityMilli(value) {
  const match = /^(\d+)(?:\.(\d{1,3}))?$/.exec(String(value || "").trim());
  return match ? Number(match[1]) * 1000 + Number((match[2] || "").padEnd(3, "0")) : null;
}
function counterQuantityText(milli) {
  const whole = Math.floor(milli / 1000), fraction = String(milli % 1000).padStart(3, "0").replace(/0+$/, "");
  return fraction ? whole + "." + fraction : String(whole);
}
async function addProductToDraft(productId, quantity, increment) {
  if (!currentBill || currentBill.state !== "DRAFT") throw new Error("Start an editable Counter draft first.");
  const amount = counterQuantityMilli(quantity);
  if (!productId || amount === null || amount <= 0) throw new Error("Choose a saved product and enter a positive quantity.");
  let finalQuantity = amount;
  if (increment) {
    const currentLine = currentBill.lines.find(line => line.product_id === productId);
    finalQuantity += currentLine ? counterQuantityMilli(currentLine.quantity) : 0;
  }
  const updated = await api("/api/merchant/bills/" + encodeURIComponent(currentBill.id) + "/lines/" + encodeURIComponent(productId), {
    method:"PUT", body:{quantity:counterQuantityText(finalQuantity)},
  });
  renderCounter(updated);
  return updated;
}
$("#counter-add-product").onsubmit = async e => {
  e.preventDefault();
  const fields = e.currentTarget.elements;
  try { await addProductToDraft(fields.product_id.value, fields.quantity.value, false); $("#counter-add-msg").textContent = "Line saved with the current catalogue price."; }
  catch (err) { $("#counter-add-msg").textContent = err.message; }
};

let scannerQueue = Promise.resolve(), scannerLastCode = "", scannerLastAt = 0;
async function resolveCounterCode(code, duplicateGuard=true) {
  const value = String(code || "").trim(), message = $("#counter-barcode-msg");
  if (!value) return;
  const stamp = Date.now();
  if (duplicateGuard && value === scannerLastCode && stamp - scannerLastAt < 650) {
    message.textContent = "Repeated scanner event ignored."; return;
  }
  scannerLastCode = value; scannerLastAt = stamp;
  scannerQueue = scannerQueue.catch(() => {}).then(async () => {
    message.textContent = "Looking up barcode or SKU…";
    let product;
    try { product = await api("/api/merchant/catalog/products/lookup?barcode=" + encodeURIComponent(value)); }
    catch (barcodeError) {
      try { product = await api("/api/merchant/catalog/products/lookup?sku=" + encodeURIComponent(value)); }
      catch (skuError) {
        $("#counter-catalog-search").value = value; updateCounterProductOptions(); $("#counter-catalog-search").focus();
        throw new Error("No active product matches that code. Catalogue search is filtered for manual selection.");
      }
    }
    await addProductToDraft(product.id, "1", true);
    message.textContent = product.name + " added. Further scans increase its quantity after a brief duplicate guard.";
    $("#counter-barcode").elements.code.value = "";
  });
  try { await scannerQueue; } catch (err) { message.textContent = err.message || "Barcode lookup failed."; }
}
$("#counter-barcode").onsubmit = e => { e.preventDefault(); return resolveCounterCode(e.currentTarget.elements.code.value); };

function renderCounterSuggestions(container, items) {
  container.replaceChildren();
  (items || []).forEach(item => {
    const card = document.createElement("div"); card.className = "counter-suggestion";
    const title = document.createElement("b"); title.textContent = item.recognized_name || "Unmatched line";
    const info = document.createElement("div"); info.className = "muted";
    info.textContent = "Catalogue score " + (item.candidates?.[0]?.catalogue_match ?? "none") +
      " · provider confidence " + (item.provider_confidence ?? "not supplied") + " · review required";
    card.append(title, info);
    const selectLabel = document.createElement("label"); selectLabel.textContent = "Select saved catalogue product";
    const select = document.createElement("select"), placeholder = document.createElement("option");
    placeholder.value = ""; placeholder.textContent = "Choose product"; select.append(placeholder);
    (item.candidates || []).forEach(candidate => {
      const option = document.createElement("option"); option.value = candidate.product_id;
      option.textContent = candidate.name + " · " + candidate.unit + " · match " + candidate.catalogue_match;
      select.append(option);
    });
    selectLabel.append(select);
    const quantityLabel = document.createElement("label"); quantityLabel.textContent = "Review quantity";
    const quantity = document.createElement("input"); quantity.inputMode = "decimal"; quantity.placeholder = "Enter quantity";
    quantity.value = item.quantity || ""; quantityLabel.append(quantity);
    const note = document.createElement("p"); note.className = "muted";
    note.textContent = item.candidates?.length ? (item.needs_clarification ? "Match or quantity is uncertain. Review both fields." : "Select the product and confirm its quantity.") : "No saved match. Use catalogue search above; nothing was added.";
    const button = document.createElement("button"); button.type = "button"; button.className = "btn ghost"; button.textContent = "Add reviewed line to draft";
    const outcome = document.createElement("p"); outcome.className = "form-message"; outcome.setAttribute("aria-live", "polite");
    button.onclick = async () => {
      button.disabled = true;
      try { await addProductToDraft(select.value, quantity.value, true); outcome.textContent = "Added using the saved catalogue price and stock check."; }
      catch (err) { outcome.textContent = err.message; }
      finally { button.disabled = false; }
    };
    card.append(note);
    if (item.candidates?.length) card.append(selectLabel, quantityLabel, button, outcome);
    container.append(card);
  });
}

async function submitCounterImage(form, kind) {
  const status = $("#counter-" + kind + "-status"), results = $("#counter-" + kind + "-results");
  const file = form.elements.image.files[0]; results.replaceChildren();
  if (!currentBill || currentBill.state !== "DRAFT") { status.textContent = "Open a draft first."; return; }
  if (!file) { status.textContent = "Choose a JPEG, PNG, or WebP image."; return; }
  status.textContent = "Checking image and recognition settings…";
  const body = new FormData(); body.append("image", file);
  body.append("consent_to_external_processing", String(form.elements.consent.checked));
  try {
    const data = await uploadApi("/api/merchant/bills/" + encodeURIComponent(currentBill.id) + "/input/" + kind, body);
    status.textContent = data.status + ": " + data.message;
    renderCounterSuggestions(results, data.items);
  } catch (err) { status.textContent = err.message + " Use catalogue search for manual entry."; }
}
$("#counter-photo-form").onsubmit = e => { e.preventDefault(); submitCounterImage(e.currentTarget, "photo"); };
$("#counter-parchi-form").onsubmit = e => { e.preventDefault(); submitCounterImage(e.currentTarget, "parchi"); };

async function reviewCounterText(text, status, results) {
  results.replaceChildren();
  if (!currentBill || currentBill.state !== "DRAFT") { status.textContent = "Open a draft first."; return; }
  status.textContent = "Matching typed lines against this store’s saved catalogue…";
  try {
    const data = await api("/api/merchant/bills/" + encodeURIComponent(currentBill.id) + "/input/text", {
      method:"POST", body:{text},
    });
    status.textContent = data.status + ": " + data.message;
    renderCounterSuggestions(results, data.items);
  } catch (err) { status.textContent = err.message; }
}
$("#counter-parchi-manual").onclick = () => reviewCounterText($("#counter-parchi-text").value,
  $("#counter-parchi-status"), $("#counter-parchi-results"));
$("#counter-voice-review-text").onclick = () => reviewCounterText($("#counter-voice-transcript").value,
  $("#counter-voice-status"), $("#counter-voice-results"));

let counterVoiceRecorder = null, counterVoiceStream = null, counterVoiceChunks = [], counterVoiceCancelled = false;
function stopCounterVoiceTracks() {
  counterVoiceStream?.getTracks().forEach(track => track.stop()); counterVoiceStream = null;
}
$("#counter-voice-start").onclick = async () => {
  const status = $("#counter-voice-status");
  if (!currentBill || currentBill.state !== "DRAFT") { status.textContent = "Open a draft first."; return; }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { status.textContent = "Voice recording is unavailable in this browser. Use typed catalogue input."; return; }
  try {
    counterVoiceStream = await navigator.mediaDevices.getUserMedia({audio:true});
    const type = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"].find(value => MediaRecorder.isTypeSupported?.(value));
    counterVoiceRecorder = type ? new MediaRecorder(counterVoiceStream, {mimeType:type}) : new MediaRecorder(counterVoiceStream);
    counterVoiceChunks = []; counterVoiceCancelled = false;
    counterVoiceRecorder.ondataavailable = event => { if (event.data.size) counterVoiceChunks.push(event.data); };
    counterVoiceRecorder.onstop = async () => {
      stopCounterVoiceTracks();
      $("#counter-voice-start").hidden = false; $("#counter-voice-stop").hidden = true; $("#counter-voice-cancel").hidden = true;
      if (counterVoiceCancelled) { $("#counter-voice-status").textContent = "Recording cancelled. Nothing was sent."; return; }
      status.textContent = "Transcribing this voice turn…";
      const blob = new Blob(counterVoiceChunks, {type:counterVoiceRecorder.mimeType || "audio/webm"});
      const body = new FormData(); body.append("audio", blob, "counter-voice.webm");
      body.append("consent_to_external_processing", String($("#counter-voice-consent").checked));
      try {
        const data = await uploadApi("/api/merchant/bills/" + encodeURIComponent(currentBill.id) + "/input/voice", body);
        status.textContent = data.status + ": " + data.message;
        $("#counter-voice-transcript").value = data.transcript || "";
        $("#counter-voice-transcript-wrap").hidden = false;
        $("#counter-voice-review-text").hidden = false;
        renderCounterSuggestions($("#counter-voice-results"), data.items);
      } catch (err) { status.textContent = err.message + " Use typed catalogue input."; }
    };
    counterVoiceRecorder.start();
    $("#counter-voice-start").hidden = true; $("#counter-voice-stop").hidden = false; $("#counter-voice-cancel").hidden = false;
    status.textContent = "Recording… Say the product names and quantities, then stop to review.";
  } catch (err) { status.textContent = "Microphone permission or recording failed: " + err.message + ". Use typed catalogue input."; }
};
$("#counter-voice-stop").onclick = () => { if (counterVoiceRecorder?.state === "recording") counterVoiceRecorder.stop(); };
$("#counter-voice-cancel").onclick = () => {
  counterVoiceCancelled = true; counterVoiceRecorder?.stop(); stopCounterVoiceTracks(); counterVoiceChunks = [];
  $("#counter-voice-start").hidden = false; $("#counter-voice-stop").hidden = true; $("#counter-voice-cancel").hidden = true;
  $("#counter-voice-status").textContent = "Recording cancelled. Nothing was sent.";
};

let counterCameraStream = null, counterBarcodeDetector = null, counterCameraFrame = 0;
function stopCounterCamera(message) {
  if (counterCameraFrame) cancelAnimationFrame(counterCameraFrame); counterCameraFrame = 0;
  counterCameraStream?.getTracks().forEach(track => track.stop()); counterCameraStream = null;
  const video = $("#counter-camera-video"); video.pause(); video.srcObject = null; video.hidden = true;
  $("#counter-camera-stop").hidden = true; $("#counter-camera-start").hidden = false;
  $("#counter-camera-status").textContent = message || "Camera stopped.";
}
async function scanCounterCamera() {
  if (!counterCameraStream || !counterBarcodeDetector) return;
  try {
    const matches = await counterBarcodeDetector.detect($("#counter-camera-video"));
    if (matches.length && matches[0].rawValue) {
      const code = matches[0].rawValue; stopCounterCamera("Code found. Looking up the saved product…");
      $("#counter-barcode").elements.code.value = code; await resolveCounterCode(code, false); return;
    }
    counterCameraFrame = requestAnimationFrame(scanCounterCamera);
  } catch (err) { stopCounterCamera("Camera scan failed: " + err.message + ". Type or scan the code instead."); }
}
async function startCounterCamera() {
  const status = $("#counter-camera-status");
  if (!window.isSecureContext || !window.BarcodeDetector || !navigator.mediaDevices?.getUserMedia) {
    status.textContent = "Camera scanning is unavailable here. Use a scanner keyboard or type a barcode/SKU."; return;
  }
  try {
    const supported = window.BarcodeDetector.getSupportedFormats ? await window.BarcodeDetector.getSupportedFormats() : [];
    const formats = ["ean_13", "ean_8", "upc_a", "code_128", "qr_code"].filter(format => !supported.length || supported.includes(format));
    counterBarcodeDetector = new BarcodeDetector(formats.length ? {formats} : undefined);
    counterCameraStream = await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:"environment"}}, audio:false});
    const video = $("#counter-camera-video"); video.srcObject = counterCameraStream; video.hidden = false; await video.play();
    $("#counter-camera-start").hidden = true; $("#counter-camera-stop").hidden = false;
    status.textContent = "Camera active. Point it at one product barcode."; scanCounterCamera();
  } catch (err) { stopCounterCamera("Camera permission or startup failed: " + err.message + ". Use a scanner or type the code."); }
}
const counterCameraSupported = window.isSecureContext && !!window.BarcodeDetector && !!navigator.mediaDevices?.getUserMedia;
if (counterCameraSupported) $("#counter-camera-start").hidden = false;
else $("#counter-camera-status").textContent = "Camera scanning is not supported here. A keyboard scanner or typed code still works.";
$("#counter-camera-start").onclick = startCounterCamera;
$("#counter-camera-stop").onclick = () => stopCounterCamera();

$("#counter-issue").onclick = async () => {
  if (!currentBill || currentBill.state !== "DRAFT") return;
  if (!window.confirm(`Issue bill ${currentBill.bill_number} for ₹${currentBill.total_fmt}? Payment will remain NOT RECORDED until verified.`)) return;
  try {
    renderCounter(await api(`/api/merchant/bills/${encodeURIComponent(currentBill.id)}/issue`, {method:"POST"}));
    $("#counter-status").textContent = "Bill issued. Payment has not been recorded.";
  } catch (e) { $("#counter-status").textContent = e.message; }
};

$("#counter-cancel").onclick = async () => {
  if (!currentBill || !["DRAFT", "ISSUED"].includes(currentBill.state)) return;
  const description = currentBill.state === "DRAFT" ? "Cancel draft" : "Void issued bill and release its stock reservation";
  if (!window.confirm(`${description} ${currentBill.bill_number}?`)) return;
  try {
    renderCounter(await api(`/api/merchant/bills/${encodeURIComponent(currentBill.id)}/cancel`, {method:"POST"}));
    $("#counter-status").textContent = "Bill cancelled. Its stock reservation was released.";
  } catch (e) { $("#counter-status").textContent = e.message; }
};

// ---------------------------------------------------------------- khata ledger
let selectedKhataAccount = "";
async function loadKhata() {
  try {
    const accounts = await api("/api/merchant/khata/accounts?limit=100");
    $("#khata-empty").style.display = accounts.length ? "none" : "block";
    $("#khata-accounts").innerHTML = accounts.map(account => `<tr>
      <td><b>${esc(account.name)}</b></td><td>${esc(account.phone)}</td>
      <td class="num">₹${esc(account.outstanding_fmt)}</td>
      <td><button class="btn ghost sm" data-khata-open="${esc(account.id)}">View ledger</button></td>
    </tr>`).join("");
    document.querySelectorAll("[data-khata-open]").forEach(button => button.onclick = () => showKhataAccount(button.dataset.khataOpen));
    if (selectedKhataAccount && accounts.some(x => x.id === selectedKhataAccount)) await showKhataAccount(selectedKhataAccount);
  } catch (e) { $("#khata-empty").textContent = e.message || "Could not load Khata"; $("#khata-empty").style.display = "block"; }
}

async function showKhataAccount(accountId) {
  try {
    const data = await api(`/api/merchant/khata/accounts/${encodeURIComponent(accountId)}`);
    selectedKhataAccount = accountId;
    $("#khata-detail-panel").hidden = false;
    $("#khata-account-title").textContent = `${data.account.name} · ${data.account.phone}`;
    $("#khata-balance").textContent = `₹${data.account.outstanding_fmt} outstanding`;
    const form = $("#khata-repayment-form");
    form.elements.account_id.value = accountId;
    const collectionForm = $("#khata-collection-form");
    collectionForm.elements.idempotency_key.value = data.pending_collection?.idempotency_key || "";
    if (!collectionForm.elements.amount.value) {
      collectionForm.elements.amount.value = (data.outstanding_paise / 100).toFixed(2);
    }
    const collectionLink = $("#khata-collection-link");
    collectionLink.replaceChildren();
    if (data.pending_collection?.checkout_url) {
      const link = document.createElement("a");
      link.href = data.pending_collection.checkout_url;
      link.target = "_blank"; link.rel = "noopener";
      link.textContent = data.pending_collection.provider === "fake" ? "Open simulated payment link ↗" : "Open Paytm payment link ↗";
      collectionLink.append(link);
    } else if (data.pending_collection) {
      collectionLink.textContent = "Collection is unresolved. Retry below to resolve the same request.";
    } else {
      collectionLink.textContent = "Payment is applied to Khata only after verified Paytm status.";
    }
    const reversed = new Set(data.entries.map(x => x.reverses_entry_id).filter(Boolean));
    $("#khata-entries").innerHTML = data.entries.map(entry => {
      const amount = `₹${entry.amount_fmt}`;
      const sign = entry.delta_paise > 0 ? "+" : "−";
      const canReverse = entry.entry_type !== "REVERSAL" && !reversed.has(entry.id);
      return `<tr><td>${tm(entry.created_at)}</td><td>${esc(entry.entry_type.replaceAll("_", " "))}</td>
        <td class="num">${sign}${amount}</td><td class="num">₹${paiseFormat(entry.running_balance_paise)}</td>
        <td>${esc(entry.note || entry.source_type.replaceAll("_", " "))}<div class="muted">${esc(entry.recording_basis.replaceAll("_", " "))}</div></td>
        <td>${canReverse ? `<button class="btn ghost sm" data-khata-reverse="${esc(entry.id)}">Reverse</button>` : ""}</td></tr>`;
    }).join("");
    document.querySelectorAll("[data-khata-reverse]").forEach(button => button.onclick = async () => {
      const reason = window.prompt("Reason for this correction (required):");
      if (!reason || reason.trim().length < 3) return;
      try { await api(`/api/merchant/khata/entries/${encodeURIComponent(button.dataset.khataReverse)}/reverse`, {method:"POST", body:{reason:reason.trim()}}); await showKhataAccount(accountId); }
      catch (e) { alert(e.message); }
    });
  } catch (e) { $("#khata-repayment-message").textContent = e.message; }
}

$("#khata-refresh").onclick = loadKhata;
$("#khata-collection-form").onsubmit = async e => {
  e.preventDefault();
  const form = e.currentTarget, msg = $("#khata-collection-message");
  msg.textContent = "";
  const button = form.querySelector("button[type='submit']");
  button.disabled = true;
  try {
    const accountId = selectedKhataAccount;
    if (!accountId) throw new Error("Select a Khata account first.");
    const key = form.elements.idempotency_key.value || newIdempotencyKey("khata_link_");
    form.elements.idempotency_key.value = key;
    const result = await api(`/api/merchant/khata/accounts/${encodeURIComponent(accountId)}/payment-links`, {
      method:"POST", body:{amount_paise:moneyToPaise(form.elements.amount.value), idempotency_key:key},
    });
    form.elements.idempotency_key.value = result.idempotency_key || key;
    msg.textContent = result.mode === "SIMULATED"
      ? "Simulated collection link created. It is not a real payment."
      : result.checkout_url ? "Paytm collection link created. Khata will change only after the server verifies payment."
      : "The request is unresolved. Retry to check the same provider request; the ledger is unchanged.";
    await showKhataAccount(accountId);
    await loadKhata();
  } catch (err) { msg.textContent = err.message || "Could not create a collection link."; }
  finally { button.disabled = false; }
};
$("#khata-repayment-form").onsubmit = async e => {
  e.preventDefault();
  const form = e.currentTarget, msg = $("#khata-repayment-message");
  msg.textContent = "";
  try {
    const key = form.elements.idempotency_key.value || newIdempotencyKey("khata_repay_");
    form.elements.idempotency_key.value = key;
    const result = await api(`/api/merchant/khata/accounts/${encodeURIComponent(form.elements.account_id.value)}/repayments`, {
      method:"POST", body:{amount_paise:moneyToPaise(form.elements.amount.value), method:form.elements.method.value,
        idempotency_key:key, note:form.elements.note.value, confirm_received:form.elements.confirm_received.checked},
    });
    msg.textContent = `Recorded as merchant-confirmed receipt. Outstanding: ₹${paiseFormat(result.outstanding_paise)}.`;
    form.elements.amount.value = ""; form.elements.note.value = ""; form.elements.confirm_received.checked = false;
    form.elements.idempotency_key.value = "";
    await showKhataAccount(form.elements.account_id.value);
    await loadKhata();
  } catch (err) { msg.textContent = err.message; }
};

// ---------------------------------------------------------------- operations
function header(st) {
  env = st.environment;
  const live = env.startsWith("paytm");
  $("#envtag").className = "envtag " + (live ? "live" : "sim");
  $("#envtag").textContent = live ? (env === "paytm-staging" ? "Paytm test environment" : "Paytm production") : "Fake gateway · simulated";
  $("#merchant").textContent = activeSession?.store_name || st.merchant;
  $("#ownerch").textContent = st.telegram ? "also on the owner's Telegram" : "console only (Telegram not configured)";
}

function kpis(c) {
  const sim = !env.startsWith("paytm");
  const k = (l, v, cls="") => `<div class="kpi ${cls}"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  $("#kpis").innerHTML = k("Payments flagged", c.flagged) + k("Customers contacted", c.contacted) +
    k("Paid · confirmed", c.paid, "acc") + k("Waiting for you", c.waiting_owner, "amb") +
    k("Stopped / blocked", c.stopped_by_policy) +
    k("Verified recovered" + (sim ? ` <span class="simtag">fake gateway</span>` : ""), "₹" + c.recovered_fmt, "big");
}

function caseRows(cases) {
  $("#cases-empty").style.display = cases.length ? "none" : "block";
  $("#cases tbody").innerHTML = cases.map(c => {
    const [tag, title] = SRC[c.source] || ["", ""];
    return `<tr data-id="${esc(c.id)}" class="${c.id === selected ? "sel" : ""}">
      <td><b>${esc(c.name)}</b> <span class="src ${esc(c.source)}" title="${esc(title)}">${tag}</span><div class="muted">${esc(c.order_id)} · ${esc(c.bank)}</div></td>
      <td class="num">₹${esc(c.amount_fmt)}</td><td>${esc(c.language_name)}</td>
      <td><span class="st ${esc(c.state)}">${esc(STATE_LABEL[c.state] || c.state)}</span></td>
      <td class="muted">${esc(REASON[c.reason] || "")}${c.messages_sent > 1 ? ` · ${c.messages_sent - 1} reminder${c.messages_sent > 2 ? "s" : ""}` : ""}</td>
    </tr>`}).join("");
  document.querySelectorAll("#cases tbody tr").forEach(tr => tr.onclick = () => { selected = tr.dataset.id; refresh(); });
}

function approvals(cases) {
  const w = cases.filter(c => c.state === "WAITING_OWNER");
  $("#approvals").innerHTML = w.length ? w.map(c => `
    <div class="appr"><div class="row"><span>${esc(c.name)}</span><span>₹${esc(c.amount_fmt)}</span></div>
      <p><b>Why you:</b> ${esc(REASON[c.reason] || c.reason)}. <b>Proposal:</b> one Paytm link in ${esc(c.language_name)}, then stop. No answer = nobody is contacted.</p>
      <div class="btns"><button class="btn" data-ap="${esc(c.id)}">Approve</button><button class="btn ghost" data-sk="${esc(c.id)}">Skip</button><button class="btn ghost" data-sel="${esc(c.id)}">Why?</button></div></div>`).join("")
    : `<p class="empty">Nothing needs you right now.</p>`;
  document.querySelectorAll("[data-ap]").forEach(b => b.onclick = () => act(() => api("/api/owner/approve/" + b.dataset.ap, {method:"POST"})));
  document.querySelectorAll("[data-sk]").forEach(b => b.onclick = () => act(() => api("/api/owner/skip/" + b.dataset.sk, {method:"POST"})));
  document.querySelectorAll("[data-sel]").forEach(b => b.onclick = () => { selected = b.dataset.sel; refresh(); });
}

const CH = {"telegram-demo-customer": "Telegram · demo customer phone", "console-inbox": "console inbox (not delivered)", "console-demo": "typed in console"};
function inbox(msgs) {
  $("#inbox").innerHTML = msgs.length ? msgs.map(m => `
    <div class="msg ${m.direction === "in" ? "in" : ""}"><div class="who"><span>${m.direction === "in" ? "From " : "To "}${esc(m.name)} · ${esc(m.language)}${m.channel ? " · " + esc(CH[m.channel] || m.channel) : ""}</span><span>${tm(m.at)}</span></div>
    <div class="txt" lang="${esc(m.language)}">${linkify(esc(m.text))}</div></div>`).join("") : `<p class="empty">No messages yet.</p>`;
}
const linkify = t => t.replace(/(https?:\/\/[^\s।<]+)/g, u => `<a href="${u.replace(/[.)]$/,"")}" target="_blank">${u}</a>`);

function logs(events) {
  $("#log").innerHTML = events.map(e => `<div class="logi"><span class="t">${tm(e.at)}</span><span class="tag">${esc(e.kind)}</span><span>${esc(e.text)}</span></div>`).join("");
}

const short = v => Array.isArray(v) ? v.map(short).join("; ") : v && typeof v === "object" ? Object.entries(v).map(([k, x]) => `${k} ${short(x)}`).join(", ") : typeof v === "number" && !Number.isInteger(v) ? v.toFixed(3) : String(v);
const flat = r => r && typeof r === "object" ? Object.entries(r).map(([k, v]) => `<span><i>${esc(k.replace(/_/g, " "))}</i> ${esc(short(v))}</span>`).join("") : esc(String(r));

async function detail() {
  if (!selected) return;
  let d;
  try { d = await api("/api/cases/" + encodeURIComponent(selected)); } catch(e) { selected = null; return; }
  const dec = d.decision, job = d.job, card = job.card;
  const steps = job.steps.map(s => `<li class="${s.state}"><span class="t">${tm(s.at) || "—"}</span><div><b>${esc(s.title)}</b><div class="muted">${esc(s.detail)}</div></div></li>`).join("");
  const checks = card ? card.policy.checks.map(c => `<li class="${c.ok === false ? "no" : "yes"}">${c.ok === false ? "✕" : "✓"} ${esc(c.rule)}</li>`).join("") : "";
  const cardHtml = card ? `
    <div class="io">
      <div class="k">INPUT</div><div>${card.input.map(esc).join("<br>")}</div>
      <div class="k">DECISION</div><div><b>${esc(card.decision)}</b><div class="muted">recommended by ${esc(card.decided_by)}</div></div>
      <div class="k">REASON</div><div>${esc(card.reason)}${card.evidence.length ? `<ul class="ev">${card.evidence.map(e => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}</div>
      <div class="k">POLICY</div><div><span class="verdict ${esc(card.policy.verdict)}">${esc(card.policy.verdict)}</span> <span class="muted">rule ${esc(card.policy.rule)} · policy ${esc(card.policy.version)}</span><ul class="checks">${checks}</ul></div>
      <div class="k">ACTION</div><div>${esc(card.action)}</div>
      <div class="k">RESULT</div><div><b>${esc(card.result)}</b></div>
    </div>` : `<p class="empty">The agent has not decided yet.</p>`;
  const [tag, title] = SRC[job.source.kind] || ["", ""];
  $("#detail").innerHTML = `
    <div class="dhead"><div><div class="name">${esc(d.name)} <span class="src ${esc(job.source.kind)}" title="${esc(title)}">${tag}</span></div>
      <div class="muted">Order ${esc(d.order_id)} · ₹${esc(d.amount_fmt)} · ${esc(d.language_name)} · ${esc(job.source.label)}</div></div>
      <span class="st ${esc(d.state)}">${esc(STATE_LABEL[d.state] || d.state)}</span></div>
    <div class="cols2">
      <div><h3>The job, step by step</h3><ol class="steps">${steps}</ol></div>
      <div><h3>Decision record</h3>${cardHtml}</div>
    </div>
    ${dec && dec.trace && dec.trace.length ? `<details class="raw"><summary>What the agent looked up (${dec.trace.length} tool call${dec.trace.length > 1 ? "s" : ""})</summary><ol class="trace">${dec.trace.map(x => `<li class="${x.rejected ? "rej" : ""}"><span class="tool">${esc(x.tool)}()${x.rejected ? " — refused, not an allowed tool" : ""}</span><div class="kv">${flat(x.result)}</div></li>`).join("")}</ol></details>` : ""}
    <details class="raw"><summary>Timeline (${d.timeline.length})</summary><ul class="tl">${d.timeline.map(t => `<li><span class="t">${tm(t.at)}</span><span>${esc(t.text)}</span></li>`).join("") || "<li class='muted'>—</li>"}</ul></details>
    ${dec && dec.raw_output ? `<details class="raw"><summary>Raw model output</summary><pre>${esc(dec.raw_output)}</pre></details>` : ""}
    <p class="muted" style="margin:10px 0 0"><a href="/api/cases/${encodeURIComponent(d.id)}/evidence" target="_blank">Export evidence bundle (JSON)</a> · environment: ${esc(job.environment)}</p>`;
}

async function refresh() {
  try {
    const st = await api("/api/state");
    faults = st.faults;
    header(st); kpis(st.counts); caseRows(st.cases); approvals(st.cases); inbox(st.messages); logs(st.events);
    document.querySelectorAll(".toggle").forEach(b => b.classList.toggle("active", !!(b.dataset.act === "timeout" ? faults.status_timeout : faults.gateway_down)));
    $("#bank").textContent = st.bank.degraded ? `Bank A failing ${st.bank.recent_failures}/${st.bank.recent_attempts} in 15 min` : "";
    if (!selected && st.cases.length) selected = (st.cases.find(c => c.order_id === "A118") || st.cases[0]).id;
    await detail();
  } catch (e) { $("#ctlnote").textContent = "Server not reachable: " + e.message; }
}

async function act(fn) {
  try { $("#ctlnote").textContent = "…"; const r = await fn(); $("#ctlnote").textContent = "simulated signals and injected faults, labelled as such"; await refresh(); return r; }
  catch (e) { $("#ctlnote").textContent = e.message; }
}

document.querySelectorAll("[data-act]").forEach(b => b.onclick = () => {
  const a = b.dataset.act, need = () => { if (!selected) throw new Error("Select a case first"); return encodeURIComponent(selected); };
  const map = {
    spike: () => api("/api/demo/spike", {method:"POST"}),
    bank: () => api("/api/demo/bank-recovers", {method:"POST"}),
    pay: () => api("/api/demo/pay/" + need(), {method:"POST"}),
    wrong: () => api("/api/demo/pay-wrong-amount/" + need(), {method:"POST"}),
    dup: () => api("/api/demo/duplicate-callback/" + need(), {method:"POST"}),
    stop: () => api("/api/demo/stop/" + need(), {method:"POST"}),
    timeout: () => api("/api/demo/fault/status-timeout?on=" + !faults.status_timeout, {method:"POST"}),
    down: () => api("/api/demo/fault/gateway-down?on=" + !faults.gateway_down, {method:"POST"}),
    reset: () => { if (!confirm("Reset all demo data?")) return Promise.resolve(); selected = null; $("#eval").innerHTML = ""; return api("/api/demo/reset", {method:"POST"}); },
  };
  act(map[a]);
});

// ---------------------------------------------------------------- customer replies
async function sendReply(text) {
  if (!selected) { $("#rres").textContent = "Select a case first."; return; }
  if (!text.trim()) return;
  $("#rres").textContent = "…";
  try {
    const r = await api("/api/customer/reply/" + encodeURIComponent(selected), {method: "POST", body: {text}});
    $("#rres").innerHTML = `Understood as <b>${esc((r.intent || "").replace(/_/g, " "))}</b>${r.when_hours ? ` (${r.when_hours} h)` : ""} by ${esc(r.reasoner || "")} → ${esc(r.action || "")}`;
    await refresh();
  } catch (e) { $("#rres").textContent = e.message; }
}
document.querySelectorAll("[data-reply]").forEach(b => b.onclick = () => sendReply(b.dataset.reply));
$("#rsend").onclick = () => sendReply($("#rtext").value);
$("#rtext").addEventListener("keydown", e => { if (e.key === "Enter") sendReply($("#rtext").value); });

// ---------------------------------------------------------------- Ask Wapas
async function ask(payload) {
  const r = await api("/api/voice/ask", {method:"POST", body: payload});
  const tr = r.trace || {};
  const bits = [];
  if (tr.stt) bits.push(tr.stt.ok ? `heard by Sarvam ${tr.stt.model} (${tr.stt.language || "auto"}, ${tr.stt.ms} ms)` : `speech-to-text: ${tr.stt.fallback}`);
  if (tr.tts) bits.push(tr.tts.ok ? `spoken by Sarvam ${tr.tts.model} in ${tr.tts.language} (${tr.tts.ms} ms)` : `voice: ${tr.tts.fallback}`);
  bits.push(tr.reasoning || "");
  $("#answer").innerHTML = `${r.question ? `<div class="muted">“${esc(r.question)}”</div>` : ""}
    ${r.answer_local ? `<div class="hi" lang="${esc(r.language)}">${esc(r.answer_local)}</div>` : ""}
    <div class="hi" lang="hi">${esc(r.answer_hi)}</div><div class="en">${esc(r.answer_en)}</div>
    <div class="muted tr">${bits.filter(Boolean).map(esc).join(" · ")}</div>`;
  if (r.audio_b64) new Audio(`data:${r.audio_mime || "audio/wav"};base64,` + r.audio_b64).play().catch(() => {});
  else if ("speechSynthesis" in window) { const u = new SpeechSynthesisUtterance(r.answer_local || r.answer_hi); u.lang = (r.answer_local ? r.language : "hi") + "-IN"; speechSynthesis.speak(u); }
}
$("#askbtn").onclick = () => ask({text: $("#q").value});
$("#q").addEventListener("keydown", e => { if (e.key === "Enter") ask({text: $("#q").value}); });
let rec = null, chunks = [];
$("#mic").onclick = async () => {
  if (rec && rec.state === "recording") { rec.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    rec = new MediaRecorder(stream); chunks = [];
    rec.ondataavailable = e => chunks.push(e.data);
    rec.onstop = async () => {
      $("#mic").classList.remove("rec"); stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(chunks, {type: rec.mimeType}); const buf = await blob.arrayBuffer();
      let bin = ""; new Uint8Array(buf).forEach(b => bin += String.fromCharCode(b));
      ask({audio_b64: btoa(bin), mime: rec.mimeType, text: $("#q").value});
    };
    rec.start(); $("#mic").classList.add("rec");
  } catch (e) { $("#ctlnote").textContent = "Microphone unavailable: " + e.message; }
};

// ---------------------------------------------------------------- trust & proof
const badge = s => `<span class="dot ${esc(String(s).toLowerCase().replace(/\s+/g, "-"))}">${esc(s)}</span>`;
async function loadProof() {
  try {
    const r = await api("/api/proof");
    $("#proof").innerHTML = `<div class="integ">${r.items.map(i => `${badge(i.status)}<span><b>${esc(i.name)}</b> <span class="muted">${esc(i.detail)}</span></span>`).join("")}</div>
      <p class="muted" style="margin-top:10px">Environment: <b>${esc(r.environment)}</b>${r.doctor_at ? ` · last live check ${tm(r.doctor_at)}` : " · live check not run yet"}</p>`;
  } catch (e) { $("#proof").innerHTML = `<p class="empty">${esc(e.message)}</p>`; }
}
$("#doctor").onclick = async () => {
  $("#integ").innerHTML = `<p class="empty">Calling each service…</p>`;
  try {
    const r = await api("/api/integrations");
    $("#integ").innerHTML = r.map(x => `<div class="doc">${badge(x.status)} <b>${esc(x.name)}</b> <span class="muted">${esc(x.summary)}</span>
      <ul>${x.checks.map(c => `<li class="${c.ok === false ? "no" : c.ok ? "yes" : "na"}">${c.ok === false ? "✕" : c.ok ? "✓" : "–"} ${esc(c.item)}: <span class="muted">${esc(c.detail)}${c.ms != null ? ` · ${c.ms} ms` : ""}</span></li>`).join("")}</ul></div>`).join("");
    loadProof();
  } catch (e) { $("#integ").innerHTML = `<p class="empty">${esc(e.message)}</p>`; }
};

// ---------------------------------------------------------------- research
function evalPanel(m) {
  if (!m || !m.batch) return;
  const pct = x => (x * 100).toFixed(1) + "%";
  const ci = m.uplift_ci.map(x => (x * 100).toFixed(1)).join(" to ");
  $("#eval").innerHTML = `<div class="metrics">
    <div class="metric p"><div class="l">Treated · verified</div><div class="v">${pct(m.treated_rate)}</div><div class="s">${m.treated_recovered}/${m.treated_n} simulated cases</div></div>
    <div class="metric"><div class="l">vs hold-out</div><div class="v">${(m.uplift >= 0 ? "+" : "") + (m.uplift*100).toFixed(1)} pts</div><div class="s">hold-out ${pct(m.holdout_rate)} (n=${m.holdout_n}) · 95% CI ${ci}</div></div>
    <div class="metric"><div class="l">Escalated · messages</div><div class="v">${pct(m.escalation_rate)}</div><div class="s">set by the assumed ticket mix · ${m.outreach_per_recovery ? m.outreach_per_recovery.toFixed(2) : "—"} msgs/recovery</div></div>
    <div class="metric"><div class="l">Safety invariants</div><div class="v">${m.duplicates} · ${m.breaches}</div><div class="s">duplicate sends · policy breaches</div></div></div>
    <div class="note">${esc(m.note)} Reasoner: ${esc(m.reasoner || "rules")}.</div>`;
}
const DIAG = {bank_side: "Bank-side failures", customer_side: "Customer-side failures"};
function armBlock(L) {
  const arm = (d, a, best) => `<div class="bar"><span class="lab">${a}</span><span class="trk"><span class="fill ${best ? "best" : ""}" style="width:${(d[a].mean * 100).toFixed(1)}%"></span></span><span class="num">${(d[a].mean * 100).toFixed(0)}% paid · n=${d[a].n}</span></div>`;
  return `<div class="arms">` + Object.entries(L).map(([k, d]) => {
    const n = d.now.n + d.wait.n, best = d.now.mean >= d.wait.mean ? "now" : "wait";
    return `<div class="arm"><h4>${DIAG[k] || k}</h4>${arm(d, "now", n && best === "now")}${arm(d, "wait", n && best === "wait")}<div class="muted">${n ? `Leaning: <b>${best === "now" ? "send now" : "wait, then send"}</b>` : "No outcomes yet"}</div></div>`;
  }).join("") + `</div>`;
}
function learnPanel(r) {
  if (!r) return;
  const live = Object.entries(r.live).map(([k, d]) => `<tr><td>${DIAG[k]}</td><td class="num">${d.contacted_closed}</td><td class="num">${d.verified_paid}</td><td class="num">${d.rate == null ? "—" : (d.rate * 100).toFixed(0) + "%"}</td><td class="num">${d.ci95 ? d.ci95.map(x => (x * 100).toFixed(0)).join("–") + "%" : "—"}</td></tr>`).join("");
  let h = `<h4>Live customers · passive evidence only</h4>
    <table class="mini"><thead><tr><th></th><th class="num">closed</th><th class="num">verified paid</th><th class="num">rate</th><th class="num">95% CI</th></tr></thead><tbody>${live}</tbody></table>
    <p class="muted">Observe → verify with Paytm → store → aggregate. Shown to the agent as evidence; it never picks or randomises an action for a real customer.</p>`;
  const has = L => L && Object.values(L).some(d => d.now.n + d.wait.n > 0);
  if (has(r.eval)) {
    h += `<h4 style="margin-top:14px">Research batch · simulated customers · Thompson sampling on send timing</h4>` + armBlock(r.eval);
    if (r.true_lift) h += `<div class="muted" style="margin-top:6px">Simulation truth (hidden from Wapas): bank-side now +${r.true_lift["bank_side:now"] * 100} / wait +${r.true_lift["bank_side:wait"] * 100} pts; customer-side now +${r.true_lift["customer_side:now"] * 100} / wait +${r.true_lift["customer_side:wait"] * 100} pts. One 400-case batch can miss a 7-point gap; across 20 seeds the right arm won 15/20 (bank) and 18/20 (customer).</div>`;
    if (lastWaves && lastWaves.length) {
      const mx = Math.max(...lastWaves.map(w => w.now + w.wait)) || 1;
      h += `<div class="muted" style="margin-top:10px">Traffic per wave (<span style="color:#6B86D6">■ now</span> <span style="color:var(--green)">■ wait</span>), 20% exploratory:</div>
        <div class="waves">${lastWaves.map(w => `<div class="w" title="wave ${w.wave}: now ${w.now}, wait ${w.wait}"><span class="now" style="height:${w.now / mx * 100}%"></span><span class="wait" style="height:${w.wait / mx * 100}%"></span></div>`).join("")}</div>`;
    }
  }
  $("#learn").innerHTML = h;
}
async function loadLearning() { try { learnPanel(await api("/api/learning")); } catch (e) {} }
$("#evalbtn").onclick = async () => {
  $("#eval").innerHTML = `<p class="empty">Running 400 simulated cases…</p>`;
  try { const m = await api("/api/eval/run?n=400", {method:"POST"}); evalPanel(m); lastWaves = m.waves; loadLearning(); }
  catch (e) { $("#eval").innerHTML = `<p class="empty">${esc(e.message)}</p>`; }
};

$("#logout").onclick = async () => {
  try { await api("/api/auth/logout", {method:"POST"}); } catch (e) {}
  activeSession = null;
  window.location.replace("/login");
};

let soundDeviceKey = "", soundEnabled = false, soundReady = false, soundPollInFlight = false;
const soundEntries = new Map();
let activePaymentAudio = null;
function sourceLabel(type) {
  return ({RECOVERY:"Recovery payment", COUNTER_BILL:"Counter bill", SHOP_ORDER:"Shop order",
           KHATA_COLLECTION:"Khata collection"})[type] || "Verified payment";
}
function soundEventRow(item) {
  const row = document.createElement("div");
  row.className = "logi sound-event";
  const when = document.createElement("span"); when.className = "t";
  const stamp = new Date(item.verified_at);
  when.textContent = Number.isNaN(stamp.valueOf()) ? "Time unavailable" :
    stamp.toLocaleString("en-IN", {dateStyle:"medium", timeStyle:"short"});
  const label = document.createElement("span"); label.className = "tag"; label.textContent = sourceLabel(item.source_type);
  const detail = document.createElement("span");
  detail.textContent = `₹${paiseFormat(item.amount_paise)} ${item.currency} · transaction ${item.provider_transaction_id || "reference unavailable"}`;
  const progress = document.createElement("span"); progress.className = "sound-delivery";
  const entry = {id:item.id, row, progress, delivered:true, acknowledged:false, audio:"pending"};
  function update() {
    const stages = ["Committed", "Delivered to this browser", entry.acknowledged ? "Acknowledged" : "Awaiting acknowledgement"];
    if (entry.audio === "played") stages.push("Audio finished");
    else if (entry.audio === "blocked") stages.push("Browser blocked audio");
    else if (entry.audio === "muted") stages.push("Sound muted");
    else if (entry.audio === "pending") stages.push("Audio not attempted");
    progress.textContent = stages.join(" · ");
  }
  update();
  row.append(when, label, detail, progress);
  const list = $("#sound-events");
  list.querySelector(".empty")?.remove();
  list.prepend(row);
  entry.update = update;
  return entry;
}
async function playPaymentChime() {
  const audio = new Audio("/static/payment-chime.wav");
  activePaymentAudio = audio;
  await new Promise((resolve, reject) => {
    const finish = (error) => {
      clearTimeout(timeout);
      if (activePaymentAudio === audio) activePaymentAudio = null;
      if (error) reject(error); else resolve();
    };
    const timeout = setTimeout(() => finish(new Error("Audio playback did not finish")), 8000);
    audio.addEventListener("ended", () => finish(), {once:true});
    audio.addEventListener("pause", () => {
      if (audio.currentTime < audio.duration) finish(new Error("Alert sound was muted"));
    }, {once:true});
    audio.addEventListener("error", () => finish(new Error("Audio playback failed")), {once:true});
    audio.play().catch(finish);
  });
}
async function initializeSound() {
  if (activeSession?.role !== "OWNER") return;
  const key = `wapas_sound_enabled:${activeSession.merchant_id}:${activeSession.store_id}`;
  soundEnabled = localStorage.getItem(key) === "true";
  soundDeviceKey = localStorage.getItem("wapas_sound_device_id") ||
    (window.crypto?.randomUUID ? window.crypto.randomUUID() : "device_" + Math.random().toString(36).slice(2) + Date.now());
  localStorage.setItem("wapas_sound_device_id", soundDeviceKey);
  $("#sound-toggle").setAttribute("aria-pressed", String(soundEnabled));
  $("#sound-toggle").textContent = soundEnabled ? "Turn sound off" : "Enable sound";
  $("#sound-status").textContent = soundEnabled
    ? "Sound is enabled for this browser; playback completion is shown on each event."
    : "Sound is muted. Committed events still appear here with delivery and acknowledgement status.";
  await api("/api/merchant/sound/device", {method:"POST", body:{device_key:soundDeviceKey}});
  soundReady = true;
  await pollSound();
}
$("#sound-toggle").onclick = async () => {
  soundEnabled = !soundEnabled;
  if (!soundEnabled && activePaymentAudio) {
    activePaymentAudio.pause();
    activePaymentAudio.currentTime = 0;
  }
  localStorage.setItem(`wapas_sound_enabled:${activeSession.merchant_id}:${activeSession.store_id}`, String(soundEnabled));
  $("#sound-toggle").setAttribute("aria-pressed", String(soundEnabled));
  $("#sound-toggle").textContent = soundEnabled ? "Turn sound off" : "Enable sound";
  $("#sound-status").textContent = soundEnabled
    ? "Sound is enabled for this browser; playback completion is shown on each event."
    : "Sound is muted. Committed events still appear here with delivery and acknowledgement status.";
  if (soundEnabled) await pollSound();
};
async function pollSound() {
  if (!soundReady || !soundDeviceKey || activeSession?.role !== "OWNER" || soundPollInFlight) return;
  soundPollInFlight = true;
  try {
    const data = await api(`/api/merchant/sound/events?device_key=${encodeURIComponent(soundDeviceKey)}&limit=50`);
    for (const item of data.events) {
      let entry = soundEntries.get(item.id);
      if (!entry) {
        entry = soundEventRow(item);
        soundEntries.set(item.id, entry);
        if (soundEnabled) {
          try { await playPaymentChime(); entry.audio = "played"; }
          catch (e) {
            if (!soundEnabled || e.message === "Alert sound was muted") entry.audio = "muted";
            else { entry.audio = "blocked"; $("#sound-status").textContent = "This browser blocked or could not finish the alert sound. The verified payment remains visible below."; }
          }
        } else {
          entry.audio = "muted";
        }
        entry.update();
      }
    }
    const ack = data.events.length ? await api("/api/merchant/sound/events/ack", {
      method:"POST", body:{device_key:soundDeviceKey, event_ids:data.events.map(item => item.id)},
    }) : null;
    const acknowledgedThrough = ack ? Number(ack.acknowledged_through || 0) : 0;
    for (const [id, entry] of soundEntries) {
      if (id <= acknowledgedThrough) { entry.acknowledged = true; entry.update(); }
    }
  } catch (e) {
    $("#sound-status").textContent = e.message || "Verified payment alerts could not be refreshed.";
  } finally {
    soundPollInFlight = false;
  }
}

getActiveSession().then(() => {
  initializeSound().catch(e => { $("#sound-status").textContent = e.message || "Sound Mode could not connect to this store."; });
  api("/api/eval").then(m => { evalPanel(m); if (m && m.waves) lastWaves = m.waves; }).catch(() => {});
  refresh();
  setInterval(refresh, 1500);
  setInterval(() => { if (tab === "trust") loadProof(); if (tab === "research") loadLearning(); }, 5000);
  setInterval(pollSound, 3000);
}).catch(() => {});

// ---------------------------------------------------------------- staff & team
async function loadStaff() {
  const tbody = document.querySelector("#staff-table tbody");
  const empty = document.querySelector("#staff-empty");
  if (!tbody) return;
  try {
    const data = await api("/api/merchant/staff");
    const staff = data.staff || [];
    if (!staff.length) {
      tbody.innerHTML = "";
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    tbody.innerHTML = staff.map(s => `
      <tr>
        <td><b>${esc(s.username)}</b></td>
        <td><span class="chip ${s.role === 'OWNER' ? 'owner' : 'staff'}">${esc(s.role)}</span></td>
        <td><span class="status-badge ${s.is_active ? 'active' : 'inactive'}">${s.is_active ? 'Active' : 'Disabled'}</span></td>
        <td>${esc(tm(s.created_at))}</td>
        <td>
          <button class="btn sm ${s.is_active ? 'ghost' : ''}" onclick="toggleStaff('${esc(s.membership_id)}', ${!s.is_active})">
            ${s.is_active ? 'Disable' : 'Enable'}
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    if (empty) { empty.textContent = "Error loading team: " + err.message; empty.hidden = false; }
  }
}

async function toggleStaff(membershipId, makeActive) {
  try {
    await api(`/api/merchant/staff/${encodeURIComponent(membershipId)}`, {
      method: "PATCH",
      body: {is_active: makeActive},
    });
    loadStaff();
  } catch (err) {
    alert("Action failed: " + err.message);
  }
}

document.querySelector("#add-staff-form")?.addEventListener("submit", async event => {
  event.preventDefault();
  const msg = document.querySelector("#add-staff-msg");
  const btn = document.querySelector("#add-staff-btn");
  const username = document.querySelector("#staff-username").value.trim();
  const password = document.querySelector("#staff-password").value;
  const role = document.querySelector("#staff-role").value;

  if (!username || !password) return;
  if (btn) btn.disabled = true;
  if (msg) { msg.textContent = "Adding team member…"; msg.style.color = "var(--muted)"; }

  try {
    await api("/api/merchant/staff", {
      method: "POST",
      body: {username, password, role},
    });
    if (msg) { msg.textContent = "Member added successfully!"; msg.style.color = "#15803d"; }
    document.querySelector("#staff-username").value = "";
    document.querySelector("#staff-password").value = "";
    loadStaff();
  } catch (err) {
    if (msg) { msg.textContent = err.message || "Failed to add member."; msg.style.color = "#b91c1c"; }
  } finally {
    if (btn) btn.disabled = false;
  }
});

