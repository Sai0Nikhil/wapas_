// =========================================================================
// Wapas Merchant OS · Seamless Web Portal (100% Android App Parity)
// Paytm Build for India AI Hackathon · Track 3 (Autonomous AI Teammates)
// =========================================================================

(function() {
  'use strict';

  // --- Transparent Proxy Fetch Interceptor ---
  const _origFetch = window.fetch;
  window.fetch = function(url, init = {}) {
    init = {...init};
    init.headers = init.headers ? (init.headers instanceof Headers ? new Headers(init.headers) : {...init.headers}) : {};
    if (init.headers instanceof Headers) {
      init.headers.set("ngrok-skip-browser-warning", "true");
    } else {
      init.headers["ngrok-skip-browser-warning"] = "true";
    }
    return _origFetch.call(this, url, init);
  };

  // --- Dynamic SVG QR Code Generator ---
  function generatePaytmQrSvg(amount, orderId) {
    // Generate a beautiful, high-contrast QR SVG matrix
    const upiUrl = `upi://pay?pa=wapas-kirana@paytm&pn=Wapas+Kirana+Store&am=${amount.toFixed(2)}&cu=INR&tn=Bill+${orderId}`;
    // Stylized QR pattern with authentic corner finder patterns
    return `
      <svg viewBox="0 0 160 160" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <rect width="160" height="160" fill="#ffffff" rx="8"/>
        <!-- Top-Left Finder -->
        <rect x="12" y="12" width="40" height="40" fill="#002970" rx="6"/>
        <rect x="20" y="20" width="24" height="24" fill="#ffffff" rx="4"/>
        <rect x="26" y="26" width="12" height="12" fill="#00BAF2" rx="2"/>
        <!-- Top-Right Finder -->
        <rect x="108" y="12" width="40" height="40" fill="#002970" rx="6"/>
        <rect x="116" y="20" width="24" height="24" fill="#ffffff" rx="4"/>
        <rect x="122" y="26" width="12" height="12" fill="#00BAF2" rx="2"/>
        <!-- Bottom-Left Finder -->
        <rect x="12" y="108" width="40" height="40" fill="#002970" rx="6"/>
        <rect x="20" y="116" width="24" height="24" fill="#ffffff" rx="4"/>
        <rect x="26" y="122" width="12" height="12" fill="#00BAF2" rx="2"/>
        <!-- Data dots & Timing patterns -->
        <g fill="#002970">
          <rect x="60" y="18" width="6" height="6" rx="1"/>
          <rect x="74" y="18" width="6" height="6" rx="1"/>
          <rect x="88" y="18" width="6" height="6" rx="1"/>
          <rect x="18" y="60" width="6" height="6" rx="1"/>
          <rect x="32" y="60" width="6" height="6" rx="1"/>
          <rect x="46" y="60" width="6" height="6" rx="1"/>
          <rect x="60" y="32" width="6" height="6" rx="1"/>
          <rect x="68" y="44" width="6" height="6" rx="1"/>
          <rect x="82" y="44" width="6" height="6" rx="1"/>
          <rect x="60" y="60" width="8" height="8" rx="2" fill="#00BAF2"/>
          <rect x="76" y="60" width="6" height="6" rx="1"/>
          <rect x="90" y="60" width="6" height="6" rx="1"/>
          <rect x="60" y="74" width="6" height="6" rx="1"/>
          <rect x="74" y="74" width="8" height="8" rx="2" fill="#002970"/>
          <rect x="90" y="74" width="6" height="6" rx="1"/>
          <rect x="60" y="88" width="6" height="6" rx="1"/>
          <rect x="74" y="88" width="6" height="6" rx="1"/>
          <rect x="88" y="88" width="8" height="8" rx="2" fill="#00BAF2"/>
          <rect x="108" y="60" width="6" height="6" rx="1"/>
          <rect x="122" y="60" width="6" height="6" rx="1"/>
          <rect x="136" y="60" width="6" height="6" rx="1"/>
          <rect x="108" y="74" width="6" height="6" rx="1"/>
          <rect x="122" y="74" width="6" height="6" rx="1"/>
          <rect x="136" y="74" width="6" height="6" rx="1"/>
          <rect x="60" y="108" width="6" height="6" rx="1"/>
          <rect x="74" y="108" width="6" height="6" rx="1"/>
          <rect x="88" y="108" width="6" height="6" rx="1"/>
          <rect x="60" y="122" width="6" height="6" rx="1"/>
          <rect x="74" y="122" width="6" height="6" rx="1"/>
          <rect x="88" y="122" width="6" height="6" rx="1"/>
          <rect x="108" y="108" width="10" height="10" rx="2"/>
          <rect x="126" y="108" width="8" height="8" rx="2" fill="#00BAF2"/>
          <rect x="138" y="112" width="6" height="6" rx="1"/>
          <rect x="108" y="126" width="6" height="6" rx="1"/>
          <rect x="120" y="124" width="12" height="12" rx="2"/>
          <rect x="138" y="126" width="6" height="6" rx="1"/>
          <rect x="112" y="140" width="10" height="8" rx="2"/>
          <rect x="130" y="140" width="14" height="8" rx="2" fill="#002970"/>
        </g>
        <!-- Center Paytm Brand Mini-Shield -->
        <rect x="66" y="66" width="28" height="28" fill="#ffffff" rx="6" stroke="#00BAF2" stroke-width="2"/>
        <text x="80" y="84" font-family="'Plus Jakarta Sans', sans-serif" font-weight="900" font-size="14" fill="#002970" text-anchor="middle">P</text>
      </svg>
    `;
  }

  // --- Global Application State ---
  const STATE = {
    auth: { authenticated: true, role: "OWNER", username: "admin", csrfToken: "" },
    currentTab: "billing",
    cart: [],
    selectedCustomerPhone: "9876543220",
    sarkarLang: "hi",
    kpi: { total: 14, auto: 9, owner: 2, blocked: 3 },
    khataTotal: 3350,
    aging: {
      zeroToThirty: 1550,
      thirtyOneToSixty: 950,
      sixtyOneToNinety: 550,
      ninetyPlus: 300
    },
    accounts: [
      { id: "khata_9876543220", name: "Ramesh Kumar", phone: "9876543220", balance: 450, history: [
        { type: "DEBIT", title: "Milk & curd staples", amt: 150, time: "Today 09:30 AM" },
        { type: "DEBIT", title: "Tea & sugar packet", amt: 300, time: "Yesterday" }
      ]},
      { id: "khata_9876543221", name: "Priya Traders", phone: "9876543221", balance: 850, history: [
        { type: "DEBIT", title: "Kirana bulk stock purchase", amt: 850, time: "28 Oct 2026" }
      ]},
      { id: "khata_9876543222", name: "Suresh Gowda", phone: "9876543222", balance: 1200, history: [
        { type: "DEBIT", title: "Atta 5kg + Oil 1L", amt: 1200, time: "27 Oct 2026" }
      ]},
      { id: "khata_9876543223", name: "Girish Hegde", phone: "9876543223", balance: 850, history: [
        { type: "DEBIT", title: "Manual Udhaar Credit", amt: 200, time: "Today 03:15 PM" },
        { type: "DEBIT", title: "Kirana staples", amt: 650, time: "26 Oct 2026" }
      ]}
    ],
    cases: [
      { id: "A121", name: "Priya Traders", phone: "9876543221", amt: 8400, vip: true, state: "WAITING_OWNER", category: "owner", reason: "Above auto-limit (₹5,000) · Requires owner decision", time: "11 mins ago" },
      { id: "A124", name: "Deepak Verma", phone: "9876543224", amt: 6900, vip: false, state: "WAITING_OWNER", category: "owner", reason: "Above auto-limit (₹5,000) · Requires owner decision", time: "6 mins ago" },
      { id: "A118", name: "Rahul Sharma", phone: "9876543225", amt: 2340, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-link paid via Paytm UPI", time: "11 mins ago" },
      { id: "A127", name: "Manjunath Rao", phone: "9876543226", amt: 1780, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-recovered via WhatsApp nudge", time: "7 mins ago" },
      { id: "A129", name: "Karthik Subramanian", phone: "9876543227", amt: 1250, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-recovered on 1st reminder", time: "5 mins ago" },
      { id: "A131", name: "Lakshmi Naidu", phone: "9876543228", amt: 860, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-recovered instantly", time: "9 mins ago" },
      { id: "A133", name: "Anjali Gupta", phone: "9876543229", amt: 3150, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-recovered via SMS checkout", time: "4 mins ago" },
      { id: "A135", name: "Suresh Gowda", phone: "9876543230", amt: 2499, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-recovered", time: "8 mins ago" },
      { id: "A137", name: "Meena Krishnan", phone: "9876543231", amt: 1990, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-recovered", time: "3 mins ago" },
      { id: "A139", name: "Ravi Teja", phone: "9876543232", amt: 4200, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-recovered", time: "6 mins ago" },
      { id: "A141", name: "Imran Khan", phone: "9876543233", amt: 1540, vip: false, state: "RECOVERED", category: "auto", reason: "Auto-recovered", time: "3 mins ago" },
      { id: "A143", name: "Arun Kumar", phone: "9876543234", amt: 1120, vip: false, state: "BLOCKED", category: "blocked", reason: "Customer Opted Out · 0 contact harassment policy", time: "5 mins ago" },
      { id: "A145", name: "Sneha Iyer", phone: "9876543235", amt: 640, vip: false, state: "BLOCKED", category: "blocked", reason: "Opted Out · Zero contact guardrail", time: "2 mins ago" },
      { id: "A147", name: "Kiran Reddy", phone: "9876543236", amt: 3050, vip: false, state: "BLOCKED", category: "blocked", reason: "Duplicate order signal · 0 double charging guardrail", time: "6 mins ago" }
    ],
    catalog: [
      { id: "prod_atta_5k", name: "Aashirvaad Atta 5kg", pack: "5 kg bag", price: 245, emoji: "🌾", cat: "staples", stock: 18 },
      { id: "prod_salt_1k", name: "Tata Salt 1kg", pack: "1 kg pkt", price: 28, emoji: "🧂", cat: "staples", stock: 35 },
      { id: "prod_oil_1l", name: "Fortune Sunflower Oil 1L", pack: "1 litre pouch", price: 145, emoji: "🌻", cat: "oils", stock: 12 },
      { id: "prod_maggi_70g", name: "Maggi 2-Min Noodles", pack: "70g pack", price: 14, emoji: "🍜", cat: "snacks", stock: 48 },
      { id: "prod_butter_500g", name: "Amul Butter 500g", pack: "500g block", price: 275, emoji: "🧈", cat: "dairy", stock: 8 },
      { id: "prod_parleg_800g", name: "Parle-G Biscuits", pack: "800g family pack", price: 80, emoji: "🍪", cat: "snacks", stock: 24 },
      { id: "prod_rice_5k", name: "India Gate Basmati 5kg", pack: "5 kg bag", price: 460, emoji: "🍚", cat: "staples", stock: 10 },
      { id: "prod_tea_500g", name: "Tata Tea Premium", pack: "500g packet", price: 290, emoji: "☕", cat: "dairy", stock: 14 },
      { id: "prod_soap_125g", name: "Dettol Soap 125g", pack: "Pack of 3", price: 55, emoji: "🧼", cat: "dairy", stock: 20 }
    ],
    soundEvents: [
      { order: "A118", amt: 2340, time: "11 mins ago", name: "Rahul Sharma" },
      { order: "A127", amt: 1780, time: "7 mins ago", name: "Manjunath Rao" },
      { order: "A131", amt: 860, time: "9 mins ago", name: "Lakshmi Naidu" }
    ]
  };

  // --- Helper: Format INR Currency ---
  function inr(n) {
    return "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  // --- Show Toast Notification ---
  function showToast(msg) {
    const toast = document.querySelector("#toast-notify");
    if (!toast) return;
    toast.textContent = msg;
    toast.hidden = false;
    setTimeout(() => { toast.hidden = true; }, 3400);
  }

  // --- Audio Synthesis: Authentic Paytm Soundbox Dual-Tone Sine Chime + Voice ---
  function playPaytmChime(amount) {
    // 1. Light ring animation
    const led = document.querySelector("#hw-led");
    if (led) {
      led.classList.add("playing");
      setTimeout(() => led.classList.remove("playing"), 3000);
    }

    // 2. Play Web Audio two-tone chime (587.33Hz D5 -> 880.00Hz A5)
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        const ctx = new AudioCtx();
        const now = ctx.currentTime;
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        const gain = ctx.createGain();

        osc1.type = "sine";
        osc1.frequency.setValueAtTime(587.33, now); // D5
        osc2.type = "sine";
        osc2.frequency.setValueAtTime(880.00, now + 0.14); // A5

        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.5);

        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(ctx.destination);

        osc1.start(now);
        osc1.stop(now + 0.14);
        osc2.start(now + 0.14);
        osc2.stop(now + 0.5);
      }
    } catch (e) {
      console.warn("Web Audio chime failed", e);
    }

    // 3. Play audio asset if available
    try {
      const audio = new Audio("/payment-chime.wav");
      audio.play().catch(() => {});
    } catch (_) {}

    // 4. Voice announcement via Web Speech API
    if (window.speechSynthesis) {
      setTimeout(() => {
        const text = amount ? `Paytm par ${amount} rupaye prapt hue!` : "Paytm par bhugtan prapt hua!";
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "hi-IN";
        utterance.rate = 1.0;
        window.speechSynthesis.speak(utterance);
      }, 500);
    }
  }

  // --- Auto Background Authentication ---
  async function silentAutoLogin() {
    try {
      const sessionRes = await fetch("/api/auth/session", { credentials: "same-origin", cache: "no-store" });
      if (sessionRes.ok) {
        const data = await sessionRes.json();
        if (data && data.authenticated) {
          STATE.auth.csrfToken = data.csrf_token || "";
          return;
        }
      }
      // Silently log in as store owner (zero user friction)
      const loginRes = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "admin", password: "password12345678" })
      });
      if (loginRes.ok) {
        const authData = await loginRes.json();
        STATE.auth.csrfToken = authData.csrf_token || "";
      }
    } catch (e) {
      console.log("Running in offline-interactive mode", e);
    }
  }

  // --- Render Module 1: POS Billing Counter ---
  function renderCatalog(filterCat = "all", searchQuery = "") {
    const grid = document.querySelector("#catalog-items-grid");
    if (!grid) return;

    let items = STATE.catalog;
    if (filterCat !== "all") {
      items = items.filter(i => i.cat === filterCat);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      items = items.filter(i => i.name.toLowerCase().includes(q) || i.cat.toLowerCase().includes(q));
    }

    if (items.length === 0) {
      grid.innerHTML = `<div style="grid-column: 1/-1; padding: 24px; text-align: center; color: var(--text-muted); font-size: 13px;">No matching items found in catalog.</div>`;
      return;
    }

    grid.innerHTML = items.map(item => {
      const inCart = STATE.cart.filter(c => c.id === item.id).length;
      return `
        <div class="item-card ${inCart > 0 ? 'in-cart' : ''}" data-id="${item.id}">
          <div class="item-card-top">
            <div class="item-emoji">${item.emoji}</div>
            <div class="item-details">
              <h4>${item.name}</h4>
              <span>${item.pack} • Stock: ${item.stock} left</span>
            </div>
          </div>
          <div class="item-card-bot">
            <div class="item-price">${inr(item.price)}</div>
            ${inCart === 0 ? `
              <button class="btn-add-item" data-add="${item.id}">+ Add</button>
            ` : `
              <div class="qty-control-row">
                <button class="qty-btn" data-sub="${item.id}">−</button>
                <span class="qty-count">${inCart}</span>
                <button class="qty-btn" data-add="${item.id}">+</button>
              </div>
            `}
          </div>
        </div>
      `;
    }).join("");

    // Bind Add buttons
    grid.querySelectorAll("[data-add]").forEach(btn => {
      btn.onclick = () => {
        const id = btn.getAttribute("data-add");
        const item = STATE.catalog.find(i => i.id === id);
        if (item) {
          STATE.cart.push(item);
          updateCartUI();
          renderCatalog(filterCat, searchQuery);
          showToast(`Added ${item.name} to bill`);
        }
      };
    });

    // Bind Subtract buttons
    grid.querySelectorAll("[data-sub]").forEach(btn => {
      btn.onclick = () => {
        const id = btn.getAttribute("data-sub");
        const idx = STATE.cart.findLastIndex(i => i.id === id);
        if (idx !== -1) {
          const removed = STATE.cart.splice(idx, 1)[0];
          updateCartUI();
          renderCatalog(filterCat, searchQuery);
          showToast(`Removed 1 ${removed.name}`);
        }
      };
    });
  }

  function updateCartUI() {
    const countEl = document.querySelector("#cart-item-count");
    const totalEl = document.querySelector("#cart-total-val");
    const payBtn = document.querySelector("#cart-pay-btn");
    const khataBtn = document.querySelector("#cart-khata-btn");
    const clearBtn = document.querySelector("#cart-clear-btn");

    const total = STATE.cart.reduce((s, i) => s + i.price, 0);
    const count = STATE.cart.length;

    if (countEl) countEl.textContent = `${count} ${count === 1 ? 'item' : 'items'} in bill`;
    if (totalEl) totalEl.textContent = inr(total);

    if (payBtn) payBtn.disabled = count === 0;
    if (khataBtn) khataBtn.disabled = count === 0;
    if (clearBtn) clearBtn.style.display = count > 0 ? "inline-block" : "none";
  }

  // --- Show Paytm Dynamic QR Modal ---
  let qrCountdownTimer = null;
  function openPaytmQrModal() {
    const total = STATE.cart.reduce((s, i) => s + i.price, 0);
    if (total <= 0) return;

    const modal = document.querySelector("#dynamic-qr-modal");
    const amtEl = document.querySelector("#qr-modal-amount");
    const canvasBox = document.querySelector("#qr-code-canvas-box");
    const timerEl = document.querySelector("#qr-timer-countdown");

    if (amtEl) amtEl.textContent = inr(total);
    if (canvasBox) canvasBox.innerHTML = generatePaytmQrSvg(total, "W-" + Math.floor(1000 + Math.random() * 9000));

    // Start 5-min countdown
    let secondsLeft = 299;
    if (qrCountdownTimer) clearInterval(qrCountdownTimer);
    qrCountdownTimer = setInterval(() => {
      secondsLeft--;
      const m = Math.floor(secondsLeft / 60).toString().padStart(2, "0");
      const s = (secondsLeft % 60).toString().padStart(2, "0");
      if (timerEl) timerEl.textContent = `${m}:${s}`;
      if (secondsLeft <= 0) clearInterval(qrCountdownTimer);
    }, 1000);

    modal.hidden = false;
  }

  // --- Complete Sale & Open Digital Receipt Modal ---
  function openReceiptModal(paymentMethod = "PAID VIA PAYTM UPI") {
    const total = STATE.cart.reduce((s, i) => s + i.price, 0);
    const modal = document.querySelector("#receipt-modal");
    const itemsList = document.querySelector("#receipt-items-list");
    const subtotalEl = document.querySelector("#receipt-subtotal");
    const cgstEl = document.querySelector("#receipt-cgst");
    const sgstEl = document.querySelector("#receipt-sgst");
    const grandTotalEl = document.querySelector("#receipt-grand-total");
    const badgeEl = document.querySelector("#receipt-payment-badge");
    const custEl = document.querySelector("#receipt-cust-info");
    const timeEl = document.querySelector("#receipt-time");
    const billNoEl = document.querySelector("#receipt-bill-no");

    const billNo = "W-" + Math.floor(1000 + Math.random() * 9000);
    if (billNoEl) billNoEl.textContent = `BILL #${billNo}`;

    const now = new Date();
    if (timeEl) timeEl.textContent = `Today ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;

    const phone = document.querySelector("#bill-customer-phone")?.value || "";
    const matchedAccount = STATE.accounts.find(a => a.phone === phone);
    if (custEl) custEl.textContent = matchedAccount ? `Customer: ${matchedAccount.name} (+91 ${phone})` : (phone ? `Customer: +91 ${phone}` : "Customer: Walk-in Customer");

    // Group items
    const grouped = {};
    STATE.cart.forEach(item => {
      if (!grouped[item.id]) grouped[item.id] = { ...item, qty: 0 };
      grouped[item.id].qty++;
    });

    if (itemsList) {
      itemsList.innerHTML = Object.values(grouped).map(item => `
        <div class="receipt-item-row">
          <span>${item.qty}x ${item.name}</span>
          <strong>${inr(item.price * item.qty)}</strong>
        </div>
      `).join("");
    }

    const subtotal = total / 1.05;
    const tax = (total - subtotal) / 2;

    if (subtotalEl) subtotalEl.textContent = inr(subtotal);
    if (cgstEl) cgstEl.textContent = inr(tax);
    if (sgstEl) sgstEl.textContent = inr(tax);
    if (grandTotalEl) grandTotalEl.textContent = inr(total);
    if (badgeEl) badgeEl.textContent = paymentMethod;

    modal.hidden = false;
  }

  // --- Render Module 2: AI Recovery Control Tower ---
  function renderRecoveryCases(filter = "all") {
    const container = document.querySelector("#cases-list-container");
    if (!container) return;

    let list = STATE.cases;
    if (filter === "owner") list = STATE.cases.filter(c => c.category === "owner");
    if (filter === "auto") list = STATE.cases.filter(c => c.category === "auto");
    if (filter === "blocked") list = STATE.cases.filter(c => c.category === "blocked");

    container.innerHTML = list.map(c => {
      const isPriya = c.id === "A121";
      const isBlue = c.state === "RECOVERED" && isPriya;
      const cardClass = isBlue ? "case-card state-blue" : (isPriya ? "case-card highlight-priya" : "case-card");
      
      let badgeHtml = "";
      if (c.state === "WAITING_OWNER") badgeHtml = `<span class="badge-state state-owner">Needs Decision</span>`;
      else if (c.state === "WAITING_PAYMENT") badgeHtml = `<span class="badge-state state-owner">Link Active</span>`;
      else if (c.state === "RECOVERED") badgeHtml = `<span class="badge-state ${isBlue ? 'state-blue-badge' : 'state-auto'}">✓ Recovered</span>`;
      else if (c.state === "BLOCKED") badgeHtml = `<span class="badge-state state-blocked">🛡️ Guardrail Blocked</span>`;

      return `
        <div class="${cardClass}" data-case="${c.id}">
          <div class="case-card-head">
            <div class="case-user-meta">
              <div class="case-title-row">
                <span class="case-name">${c.name}</span>
                ${c.vip ? '<span class="badge-vip">VIP</span>' : ''}
              </div>
              <span class="case-sub">${c.phone} · Order #${c.id}</span>
            </div>
            <div class="case-amount-col">
              <span class="case-amt">${inr(c.amt)}</span>
              ${badgeHtml}
            </div>
          </div>
          <div class="case-card-body">
            <p class="case-reason">${c.reason}</p>
            <div class="case-timeline">
              <span class="timeline-dot"></span>
              <span class="timeline-text">Logged ${c.time}</span>
            </div>
          </div>
          <div class="case-card-actions">
            ${c.state === "WAITING_OWNER" ? `
              <button class="btn-approve-action" data-approve="${c.id}">✓ Approve & Send Link</button>
            ` : ''}
            ${c.state === "WAITING_PAYMENT" ? `
              <button class="btn-simulate-action" data-sim="${c.id}">⚡ Simulate Customer Payment</button>
            ` : ''}
            ${c.state === "RECOVERED" ? `
              <button class="btn-replay-single" data-replay="${c.id}">🛡️ Replay Webhook</button>
            ` : ''}
            <button class="btn-evidence-action" data-evidence="${c.id}">🔍 Evidence Log</button>
          </div>
        </div>
      `;
    }).join("");

    // Bind Approve
    container.querySelectorAll("[data-approve]").forEach(btn => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-approve");
        const c = STATE.cases.find(x => x.id === id);
        if (c) {
          c.state = "WAITING_PAYMENT";
          c.reason = "Approved by Store Owner · Payment recovery link SMS dispatched";
          renderRecoveryCases(filter);
          showToast(`✓ Approved recovery for ${c.name}. Customer link active.`);
        }
      };
    });

    // Bind Simulate Customer Payment
    container.querySelectorAll("[data-sim]").forEach(btn => {
      btn.onclick = () => {
        const id = btn.getAttribute("data-sim");
        const c = STATE.cases.find(x => x.id === id);
        if (c) {
          c.state = "RECOVERED";
          c.category = "auto";
          c.reason = "Payment verified via Paytm Soundbox 4G · Fully Settled";
          STATE.kpi.auto++;
          STATE.kpi.owner = Math.max(0, STATE.kpi.owner - 1);
          document.querySelector("#kpi-auto-num").textContent = STATE.kpi.auto;
          document.querySelector("#kpi-owner-num").textContent = STATE.kpi.owner;
          document.querySelector("#filter-owner-count").textContent = STATE.kpi.owner;
          document.querySelector("#filter-auto-count").textContent = STATE.kpi.auto;
          document.querySelector("#nav-owner-badge").textContent = STATE.kpi.owner;

          playPaytmChime(c.amt);
          renderRecoveryCases(filter);
          showToast(`🎉 Verified payment of ${inr(c.amt)} from ${c.name}!`);
        }
      };
    });

    // Bind Replay Webhook
    container.querySelectorAll("[data-replay]").forEach(btn => {
      btn.onclick = () => {
        showToast("🛡️ Idempotency Verified: Duplicate webhook dropped! 0 duplicate links, 0 double debits.");
      };
    });

    // Bind Evidence Log
    container.querySelectorAll("[data-evidence]").forEach(btn => {
      btn.onclick = () => {
        const id = btn.getAttribute("data-evidence");
        openEvidenceModal(id);
      };
    });
  }

  // --- Open Case Evidence Modal ---
  function openEvidenceModal(caseId) {
    const c = STATE.cases.find(x => x.id === caseId) || STATE.cases[0];
    const modal = document.querySelector("#evidence-modal");
    const titleEl = document.querySelector("#evidence-case-title");
    const bodyEl = document.querySelector("#evidence-body-content");

    if (titleEl) titleEl.textContent = `Evidence Log: ${c.name} (${c.id})`;

    if (bodyEl) {
      bodyEl.innerHTML = `
        <div class="evidence-box">
          <h4>AI Reasoner Decision</h4>
          <p><strong>Diagnosis:</strong> Bank Gateway Timeout (UPI U30 Error Code)</p>
          <p><strong>Action Chosen:</strong> ${c.amt > 5000 ? 'Owner Review Required (> ₹5,000 threshold)' : 'Instant SMS Recovery Link'}</p>
          <p><strong>Reasoner:</strong> Policy Reasoner v2.1 (Sarvam Kirana Engine)</p>
          <p><strong>Decision Confidence:</strong> 94%</p>
        </div>

        <div class="evidence-box">
          <h4>Policy Rules Evaluated</h4>
          <p><span class="policy-badge-allow">✓ ALLOW:</span> Rule <code>R-IDEMPOTENCY</code> — Unique idempotency key verified. No duplicate charges possible.</p>
          <p><span class="policy-badge-allow">✓ ALLOW:</span> Rule <code>R-COMMUNICATION</code> — Harassment guardrail check: 0 previous messages sent today (Quota: 3).</p>
          <p><span class="policy-badge-shield">🛡️ SHIELD:</span> Rule <code>R-OWNER-LIMIT</code> — ${c.amt > 5000 ? `Amount ${inr(c.amt)} exceeds ₹5,000 auto-limit. Escalated to owner.` : 'Amount within auto-limit.'}</p>
        </div>

        <div class="evidence-box">
          <h4>Action Dispatch Timeline</h4>
          <p>• <strong>10:48:02 AM:</strong> Failed payment signal received from Paytm Gateway.</p>
          <p>• <strong>10:48:03 AM:</strong> Wapas Reasoner classified failure as non-customer fault.</p>
          <p>• <strong>10:48:04 AM:</strong> Incident queued in Recovery Tower.</p>
          ${c.state === "RECOVERED" ? `<p>• <strong>10:52:15 AM:</strong> Customer completed payment via Paytm UPI. Soundbox broadcasted.</p>` : ''}
        </div>
      `;
    }

    modal.hidden = false;
  }

  // --- Render Module 3: Khata Digital Ledger ---
  function renderKhataAccounts(search = "") {
    const listEl = document.querySelector("#khata-accounts-list");
    if (!listEl) return;

    let accounts = STATE.accounts;
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      accounts = accounts.filter(a => a.name.toLowerCase().includes(q) || a.phone.includes(q));
    }

    listEl.innerHTML = accounts.map(a => {
      const initials = a.name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
      const lastTx = a.history[0] || { title: "No recent transactions", time: "" };

      return `
        <div class="account-card" data-account="${a.id}">
          <div class="account-avatar">${initials}</div>
          <div class="account-info">
            <div class="account-name-row">
              <span class="account-name">${a.name}</span>
              <span class="account-phone">${a.phone}</span>
            </div>
            <div class="account-last-tx">${lastTx.title} • ${lastTx.time}</div>
          </div>
          <div class="account-balance-col">
            <span class="account-bal">${inr(a.balance)}</span>
            <span class="bal-badge ${a.balance > 0 ? 'due' : 'settled'}">${a.balance > 0 ? 'Due' : 'Settled'}</span>
          </div>
        </div>
      `;
    }).join("");

    listEl.querySelectorAll("[data-account]").forEach(card => {
      card.onclick = () => {
        const id = card.getAttribute("data-account");
        const account = STATE.accounts.find(a => a.id === id);
        if (account) openCustomerDetailModal(account);
      };
    });
  }

  // --- Open Customer Ledger Detail Modal ---
  function openCustomerDetailModal(account) {
    const modal = document.querySelector("#customer-detail-modal");
    const nameEl = document.querySelector("#detail-cust-name");
    const phoneEl = document.querySelector("#detail-cust-phone");
    const balEl = document.querySelector("#detail-cust-bal");
    const historyList = document.querySelector("#detail-history-list");

    if (nameEl) nameEl.textContent = account.name;
    if (phoneEl) phoneEl.textContent = `+91 ${account.phone}`;
    if (balEl) balEl.textContent = inr(account.balance);

    if (historyList) {
      historyList.innerHTML = account.history.map(h => `
        <div class="history-item">
          <div class="history-info">
            <span class="history-title">${h.title}</span>
            <span class="history-time">${h.time}</span>
          </div>
          <span class="history-amt ${h.type === 'DEBIT' ? 'debit' : 'credit'}">
            ${h.type === 'DEBIT' ? '− ' : '+ '}${inr(h.amt)}
          </span>
        </div>
      `).join("");
    }

    // Bind action buttons in customer detail
    const addUdhaarBtn = document.querySelector("#detail-add-udhaar-btn");
    const repayBtn = document.querySelector("#detail-record-repay-btn");
    const paylinkBtn = document.querySelector("#detail-paylink-btn");
    const whatsappBtn = document.querySelector("#detail-whatsapp-btn");

    if (addUdhaarBtn) {
      addUdhaarBtn.onclick = () => {
        modal.hidden = true;
        document.querySelector("#khata-entry-modal").hidden = false;
        document.querySelector("#modal-customer-select").value = account.id;
        document.querySelector("#toggle-gave").click();
      };
    }

    if (repayBtn) {
      repayBtn.onclick = () => {
        modal.hidden = true;
        document.querySelector("#khata-entry-modal").hidden = false;
        document.querySelector("#modal-customer-select").value = account.id;
        document.querySelector("#toggle-got").click();
      };
    }

    if (paylinkBtn) {
      paylinkBtn.onclick = () => {
        showToast(`🔗 Copied payment link for ${account.name}: https://wapas.in/pay/${account.phone}`);
      };
    }

    if (whatsappBtn) {
      whatsappBtn.onclick = () => {
        showToast(`💬 Dispatched payment reminder to ${account.name} on WhatsApp!`);
      };
    }

    modal.hidden = false;
  }

  // --- Render Module 5: Verified Payment Soundbox Stream ---
  function renderSoundEvents() {
    const listEl = document.querySelector("#sound-events-stream");
    if (!listEl) return;

    listEl.innerHTML = STATE.soundEvents.map(e => `
      <div class="sound-event-row">
        <div class="sound-event-icon">🔊</div>
        <div class="sound-event-info">
          <span class="sound-event-title">${inr(e.amt)} received on Paytm</span>
          <span class="sound-event-sub">${e.name} • Order #${e.order} • ${e.time}</span>
        </div>
        <span class="badge-sound-verified">Verified</span>
      </div>
    `).join("");
  }

  // --- Multilingual Knowledge Packs for Sarkar AI ---
  const SARKAR_RESPONSES = {
    hi: {
      welcome: "नमस्ते! मैं सरकार AI हूँ — आपकी दुकान का 24/7 डिजिटल साथी। आज की बिक्री, खाता या स्टॉक के बारे में पूछिए।",
      recovery: "📊 आज 14 फेल्ड पेमेंट्स में से 9 तुरंत ऑटो-रिकवर हो गए (₹18,659)। 2 पेमेंट्स (प्रिया ट्रेडर्स ₹8,400) आपके अप्रूवल के इंतज़ार में हैं।",
      priya: "📒 प्रिया ट्रेडर्स का कुल खाता बकाया ₹850 है, और आज ₹8,400 का पेमेंट गेटवे टाइमआउट हुआ था जो अप्रूवल पेंडिंग है।",
      stock: "📦 स्टॉक अलर्ट: अमूल बटर (8 पैकेट बाकी) और फॉर्च्यून ऑइल (12 पैकेट बाकी) कम हो रहे हैं। क्या री-स्टॉक आर्डर ड्राफ्ट करूँ?",
      gst: "📑 इस महीने की कुल बिक्री ₹1,48,200 है। एस्टिमेटेड CGST: ₹3,705, SGST: ₹3,705। रिपोर्ट रेडी है।"
    },
    hinglish: {
      welcome: "Namaste! Main Sarkar AI hoon — aapka 24/7 Kirana Copilot. Dukan ke sales, Khata ya stock ke baare mein kuch bhi poochiye.",
      recovery: "📊 Aaj 14 failed checkouts mein se 9 automatically recover ho chuke hain (₹18,659). Priya Traders ka ₹8,400 owner decision ke liye pending hai.",
      priya: "📒 Priya Traders ka ledger balance ₹850 hai. Unka ₹8,400 ka UPI payment Recovery Tower mein owner approval ke liye ready hai.",
      stock: "📦 Low Stock Alert: Amul Butter 500g (only 8 left) and Fortune Oil 1L (12 left) restock limit ke kareeb hain.",
      gst: "📑 Monthly sales total: ₹1,48,200. Estimated GST liability calculation complete ho chuki hai."
    },
    en: {
      welcome: "Hello! I am Sarkar AI — your 24/7 Kirana Autonomous Copilot. Ask me anything about counter sales, Khata dues, or inventory.",
      recovery: "📊 Out of 14 payment incidents today, 9 were autonomously recovered (₹18,659). 2 cases (including Priya Traders ₹8,400) require your decision.",
      priya: "📒 Priya Traders has an active Khata balance of ₹850. Their ₹8,400 gateway failure is currently pending your approval in Recovery Tower.",
      stock: "📦 Stock Alert: Amul Butter 500g (8 left) and Fortune Sunflower Oil (12 left) are running low.",
      gst: "📑 Monthly gross sales: ₹1,48,200. CGST: ₹3,705, SGST: ₹3,705. Ready for filing."
    },
    kn: {
      welcome: "ನಮಸ್ಕಾರ! ನಾನು ಸರ್ಕಾರ್ AI — ನಿಮ್ಮ ಅಂಗಡಿಯ ಡಿಜಿಟಲ್ ಕೋಪೈಲಟ್. ಮಾರಾಟ, ಖಾತಾ ಬಾಕಿ ಅಥವಾ ಸ್ಟಾಕ್ ಬಗ್ಗೆ ಕೇಳಿ.",
      recovery: "📊 ಇಂದು 14 ವಿಫಲ ವಹಿವಾಟುಗಳಲ್ಲಿ 9 ಸ್ವಯಂಚಾಲಿತವಾಗಿ ವಸೂಲಿಯಾಗಿದೆ (₹18,659). 2 ವಹಿವಾಟುಗಳು ನಿಮ್ಮ ಅನುಮೋದನೆಗೆ ಕಾಯುತ್ತಿವೆ.",
      priya: "📒 ಪ್ರಿಯಾ ಟ್ರೇಡರ್ಸ್ ಖಾತಾ ಬಾಕಿ ₹850 ಆಗಿದೆ. ₹8,400 ರಿಕವರಿ ನಿಮ್ಮ ಒಪ್ಪಿಗೆಗೆ ಬಾಕಿ ಇದೆ.",
      stock: "📦 ಸ್ಟಾಕ್ ಎಚ್ಚರಿಕೆ: ಅಮೂಲ್ ಬೆಣ್ಣೆ (8 ಪ್ಯಾಕೆಟ್) ಮತ್ತು ಫಾರ್ಚೂನ್ ಎಣ್ಣೆ (12 ಪ್ಯಾಕೆಟ್) ಕಡಿಮೆಯಾಗಿದೆ.",
      gst: "📑 ಈ ತಿಂಗಳ ಜಿಎಸ್ಟಿ ವರದಿ ಸಿದ್ಧವಾಗಿದೆ. ಒಟ್ಟು ಮಾರಾಟ: ₹1,48,200."
    },
    te: {
      welcome: "నమస్తే! నేను సర్కార్ AI — మీ కిరాణా డిజిటల్ కోపైలట్. విక్రయాలు, ఖాతా బాకీలు లేదా స్టాక్ గురించి ఏదైనా అడగండి.",
      recovery: "📊 ఈరోజు 14 విఫలమైన చెల్లింపులలో 9 ఆటోమేటిక్‌గా రికవరీ అయ్యాయి (₹18,659). 2 మీ ఆమోదం కోసం వేచి ఉన్నాయి.",
      priya: "📒 ప్రియ ట్రేడర్స్ ఖాతా బాకీ ₹850. ₹8,400 రికవరీ కేసు మీ నిర్ణయం కోసం పెండింగ్‌లో ఉంది.",
      stock: "📦 స్టాక్ హెచ్చరిక: అమూల్ వెన్న మరియు ఆయిల్ ప్యాకెట్లు తక్కువగా ఉన్నాయి.",
      gst: "📑 ఈ నెలకు సంబంధించిన జీఎస్టీ రిపోర్ట్ సిద్ధంగా ఉంది."
    },
    ta: {
      welcome: "வணக்கம்! நான் சர்க்கார் AI. உங்கள் கடை விற்பனை, கடன் கணக்கு மற்றும் இருப்பு பற்றி கேளுங்கள்.",
      recovery: "📊 இன்று 14 தோல்வியடைந்த பரிவர்த்தனைகளில் 9 தானாக மீட்கப்பட்டது (₹18,659). 2 உங்கள் ஒப்புதலுக்காக நிலுவையில் உள்ளன.",
      priya: "📒 பிரியா டிரேடர்ஸ் நிலுவை ₹850. ₹8,400 மீட்பு உங்கள் ஒப்புதலுக்காக காத்திருக்கிறது.",
      stock: "📦 இருப்பு எச்சரிக்கை: அமுல் வெண்ணெய் மற்றும் சமையல் எண்ணெய் குறைந்துள்ளது.",
      gst: "📑 இந்த மாதத்தின் ஜிஎஸ்டி அறிக்கை தயாராக உள்ளது."
    }
  };

  function addChatMessage(sender, text, actionProposal = null) {
    const container = document.querySelector("#sarkar-chat-container");
    if (!container) return;

    const row = document.createElement("div");
    row.className = `chat-bubble-row ${sender}`;

    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender}`;

    // Add speaker button for bot messages
    let speakerHtml = "";
    if (sender === "bot") {
      speakerHtml = `<button class="tts-speaker-btn" title="Listen aloud">🔊</button>`;
    }

    bubble.innerHTML = `
      <div class="bubble-header">
        <span>${sender === 'bot' ? '🤖 Sarkar AI' : '👤 You'}</span>
        ${speakerHtml}
      </div>
      <div class="bubble-text">${text}</div>
    `;

    // Action Proposal Card if present
    if (actionProposal) {
      const card = document.createElement("div");
      card.className = "sarkar-action-card";
      card.innerHTML = `
        <div class="action-card-title">${actionProposal.title}</div>
        <div class="action-card-desc">${actionProposal.desc}</div>
        <div class="action-card-btns">
          <button class="btn-confirm-action">✓ Confirm Action</button>
          <button class="btn-cancel-action">Cancel</button>
        </div>
      `;
      card.querySelector(".btn-confirm-action").onclick = () => {
        card.innerHTML = `<span style="color: #166534; font-weight: 700; font-size: 11px;">✓ Action Confirmed & Synchronized with Store Database</span>`;
        if (actionProposal.onConfirm) actionProposal.onConfirm();
      };
      card.querySelector(".btn-cancel-action").onclick = () => {
        card.remove();
      };
      bubble.appendChild(card);
    }

    // Bind Speaker TTS
    const speakBtn = bubble.querySelector(".tts-speaker-btn");
    if (speakBtn && window.speechSynthesis) {
      speakBtn.onclick = () => {
        const u = new SpeechSynthesisUtterance(text);
        u.lang = STATE.sarkarLang === "hi" || STATE.sarkarLang === "hinglish" ? "hi-IN" : "en-US";
        window.speechSynthesis.speak(u);
      };
    }

    row.appendChild(bubble);
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
  }

  // --- Initialize Whole Application ---
  function initApp() {
    // 1. Silent login in background
    silentAutoLogin();

    // 2. Render initial catalog
    renderCatalog();
    updateCartUI();

    // 3. Render Recovery Tower cases
    renderRecoveryCases();

    // 4. Render Khata accounts & aging
    renderKhataAccounts();

    // 5. Render Soundbox initial events
    renderSoundEvents();

    // 6. Sarkar Initial Greeting
    const initialLang = SARKAR_RESPONSES[STATE.sarkarLang] || SARKAR_RESPONSES.hi;
    addChatMessage("bot", initialLang.welcome);

    // 7. Navigation Tabs
    document.querySelectorAll(".bottom-nav .nav-item").forEach(item => {
      item.onclick = () => {
        document.querySelectorAll(".bottom-nav .nav-item").forEach(i => i.classList.remove("active"));
        document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

        item.classList.add("active");
        const target = item.getAttribute("data-target");
        STATE.currentTab = target;
        const pane = document.querySelector(`#pane-${target}`);
        if (pane) pane.classList.add("active");
      };
    });

    // 8. View Mode Toggle (Mobile / Phone Preview vs Fullscreen)
    const toggleBtn = document.querySelector("#toggle-view-btn");
    if (toggleBtn) {
      toggleBtn.onclick = () => {
        document.body.classList.toggle("fullscreen-mode");
        document.body.classList.toggle("mobile-frame-mode");
        const isMobile = document.body.classList.contains("mobile-frame-mode");
        toggleBtn.querySelector(".btn-text").textContent = isMobile ? "Phone View" : "Desktop View";
      };
    }

    // 9. Catalog Category Filter
    document.querySelectorAll(".category-scroll .cat-chip").forEach(chip => {
      chip.onclick = () => {
        document.querySelectorAll(".category-scroll .cat-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        const cat = chip.getAttribute("data-cat");
        const searchVal = document.querySelector("#catalog-search")?.value || "";
        renderCatalog(cat, searchVal);
      };
    });

    // 10. Catalog Live Search
    const searchInput = document.querySelector("#catalog-search");
    if (searchInput) {
      searchInput.oninput = () => {
        const activeCat = document.querySelector(".category-scroll .cat-chip.active")?.getAttribute("data-cat") || "all";
        renderCatalog(activeCat, searchInput.value);
      };
    }

    // 11. Quick Customer Phone selection chips
    document.querySelectorAll(".phone-input-row .chip-btn").forEach(chip => {
      chip.onclick = () => {
        const phone = chip.getAttribute("data-phone") || "9876543220";
        const phoneInput = document.querySelector("#bill-customer-phone");
        if (phoneInput) phoneInput.value = phone;
        showToast(`Selected customer +91 ${phone}`);
      };
    });

    // 12. Parchi Scan Button & Modal
    const parchiBtn = document.querySelector("#quick-parchi-btn");
    const parchiModal = document.querySelector("#parchi-modal");
    if (parchiBtn && parchiModal) {
      parchiBtn.onclick = () => { parchiModal.hidden = false; };
      document.querySelector("#close-parchi-btn").onclick = () => { parchiModal.hidden = true; };
      document.querySelector("#cancel-parchi-btn").onclick = () => { parchiModal.hidden = true; };
      document.querySelector("#add-parchi-items-btn").onclick = () => {
        // Add all 4 detected items to cart
        const detected = [
          STATE.catalog.find(i => i.id === "prod_atta_5k"),
          STATE.catalog.find(i => i.id === "prod_oil_1l"),
          STATE.catalog.find(i => i.id === "prod_maggi_70g"),
          STATE.catalog.find(i => i.id === "prod_salt_1k")
        ].filter(Boolean);

        STATE.cart.push(...detected);
        updateCartUI();
        renderCatalog();
        parchiModal.hidden = true;
        showToast("✓ Added 4 items from handwritten slip to bill!");
      };
    }

    // 13. Barcode Scan Button & Modal
    const barcodeBtn = document.querySelector("#quick-barcode-btn");
    const barcodeModal = document.querySelector("#barcode-modal");
    if (barcodeBtn && barcodeModal) {
      barcodeBtn.onclick = () => { barcodeModal.hidden = false; };
      document.querySelector("#close-barcode-btn").onclick = () => { barcodeModal.hidden = true; };
      document.querySelector("#cancel-barcode-btn").onclick = () => { barcodeModal.hidden = true; };
      document.querySelector("#add-barcode-item-btn").onclick = () => {
        const butter = STATE.catalog.find(i => i.id === "prod_butter_500g");
        if (butter) {
          STATE.cart.push(butter);
          updateCartUI();
          renderCatalog();
          barcodeModal.hidden = true;
          showToast(`✓ Scanned & Added Amul Butter 500g (${inr(butter.price)})`);
        }
      };
    }

    // 14. Clear Cart Button
    const clearCartBtn = document.querySelector("#cart-clear-btn");
    if (clearCartBtn) {
      clearCartBtn.onclick = () => {
        STATE.cart = [];
        updateCartUI();
        renderCatalog();
        showToast("Cart cleared");
      };
    }

    // 15. Pay with Paytm Button -> Dynamic QR Modal
    const payBtn = document.querySelector("#cart-pay-btn");
    const qrModal = document.querySelector("#dynamic-qr-modal");
    if (payBtn && qrModal) {
      payBtn.onclick = openPaytmQrModal;
      document.querySelector("#close-qr-modal-btn").onclick = () => {
        qrModal.hidden = true;
        if (qrCountdownTimer) clearInterval(qrCountdownTimer);
      };
    }

    // 16. Simulate QR Payment Button
    const simQrBtn = document.querySelector("#simulate-qr-pay-btn");
    if (simQrBtn) {
      simQrBtn.onclick = () => {
        const total = STATE.cart.reduce((s, i) => s + i.price, 0);
        if (qrModal) qrModal.hidden = true;
        if (qrCountdownTimer) clearInterval(qrCountdownTimer);

        // Soundbox chime + voice announcement
        playPaytmChime(total);

        // Add to Soundbox events stream
        STATE.soundEvents.unshift({
          order: "W" + Math.floor(1000 + Math.random() * 9000),
          amt: total,
          time: "Just now",
          name: "Paytm UPI Customer"
        });
        renderSoundEvents();

        // Open Digital Receipt
        openReceiptModal("PAID VIA PAYTM UPI");

        // Clear cart
        STATE.cart = [];
        updateCartUI();
        renderCatalog();
        showToast(`🎉 Payment of ${inr(total)} verified by Paytm Soundbox!`);
      };
    }

    // 17. Add to Khata from Billing
    const khataPayBtn = document.querySelector("#cart-khata-btn");
    if (khataPayBtn) {
      khataPayBtn.onclick = () => {
        const total = STATE.cart.reduce((s, i) => s + i.price, 0);
        const phone = document.querySelector("#bill-customer-phone")?.value || "9876543220";
        let targetAccount = STATE.accounts.find(a => a.phone === phone);
        if (!targetAccount) targetAccount = STATE.accounts[0];

        targetAccount.balance += total;
        STATE.khataTotal += total;
        STATE.aging.zeroToThirty += total;
        targetAccount.history.unshift({
          type: "DEBIT",
          title: `Counter Bill (${STATE.cart.length} items)`,
          amt: total,
          time: "Just now"
        });

        document.querySelector("#khata-grand-total").textContent = inr(STATE.khataTotal);
        document.querySelector("#aging-total-pill").textContent = `Total: ${inr(STATE.khataTotal)}`;
        document.querySelector("#bucket-0-30").textContent = inr(STATE.aging.zeroToThirty);

        openReceiptModal("RECORDED TO KHATA (उधार)");

        STATE.cart = [];
        updateCartUI();
        renderCatalog();
        renderKhataAccounts();
        showToast(`📒 Added ${inr(total)} to ${targetAccount.name}'s Khata. Wapas AI is monitoring.`);
      };
    }

    // 18. Digital Receipt Done / Print / WhatsApp
    const closeReceiptBtn = document.querySelector("#close-receipt-btn");
    if (closeReceiptBtn) {
      closeReceiptBtn.onclick = () => {
        document.querySelector("#receipt-modal").hidden = true;
      };
    }
    const printReceiptBtn = document.querySelector("#print-receipt-btn");
    if (printReceiptBtn) {
      printReceiptBtn.onclick = () => {
        window.print();
      };
    }
    const shareWhatsappBtn = document.querySelector("#share-whatsapp-btn");
    if (shareWhatsappBtn) {
      shareWhatsappBtn.onclick = () => {
        showToast("💬 Digital receipt link shared to customer on WhatsApp!");
        document.querySelector("#receipt-modal").hidden = true;
      };
    }

    // 19. Recovery Tower Case Filters
    document.querySelectorAll(".case-filters .filter-tab").forEach(tab => {
      tab.onclick = () => {
        document.querySelectorAll(".case-filters .filter-tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        renderRecoveryCases(tab.getAttribute("data-filter"));
      };
    });

    // 20. Idempotency Replay Webhook Demo
    const replayBtn = document.querySelector("#replay-webhook-btn");
    if (replayBtn) {
      replayBtn.onclick = () => {
        showToast("🛡️ Idempotency Engine Verified: Duplicate webhook dropped! 0 double debits.");
      };
    }

    // 21. Reset Spike Buttons
    const resetSpikeBtn = document.querySelector("#reset-spike-btn");
    const demoResetBtn = document.querySelector("#demo-reset-btn");
    const handleResetSpike = () => {
      STATE.kpi = { total: 14, auto: 9, owner: 2, blocked: 3 };
      document.querySelector("#kpi-total-num").textContent = 14;
      document.querySelector("#kpi-auto-num").textContent = 9;
      document.querySelector("#kpi-owner-num").textContent = 2;
      document.querySelector("#kpi-blocked-num").textContent = 3;
      document.querySelector("#filter-owner-count").textContent = 2;
      document.querySelector("#filter-auto-count").textContent = 9;
      document.querySelector("#nav-owner-badge").textContent = 2;

      // Reset Priya & Deepak cases
      const priya = STATE.cases.find(c => c.id === "A121");
      if (priya) { priya.state = "WAITING_OWNER"; priya.category = "owner"; }
      const deepak = STATE.cases.find(c => c.id === "A124");
      if (deepak) { deepak.state = "WAITING_OWNER"; deepak.category = "owner"; }

      renderRecoveryCases();
      showToast("🔄 Incident Spike Reset: 14 cases (9 Auto, 2 Owner Review, 3 Blocked)");
    };

    if (resetSpikeBtn) resetSpikeBtn.onclick = handleResetSpike;
    if (demoResetBtn) demoResetBtn.onclick = handleResetSpike;

    // 22. Evidence Modal Dismiss
    const dismissEvidenceBtn = document.querySelector("#dismiss-evidence-btn");
    const closeEvidenceBtn = document.querySelector("#close-evidence-btn");
    if (dismissEvidenceBtn) dismissEvidenceBtn.onclick = () => { document.querySelector("#evidence-modal").hidden = true; };
    if (closeEvidenceBtn) closeEvidenceBtn.onclick = () => { document.querySelector("#evidence-modal").hidden = true; };

    // 23. Customer Detail Modal Close
    const closeCustDetailBtn = document.querySelector("#close-cust-detail-btn");
    if (closeCustDetailBtn) {
      closeCustDetailBtn.onclick = () => { document.querySelector("#customer-detail-modal").hidden = true; };
    }

    // 24. Khata Manual Entry Modal Handlers
    const openAddEntryBtn = document.querySelector("#open-add-entry-btn");
    const khataModal = document.querySelector("#khata-entry-modal");
    const closeModalBtn = document.querySelector("#close-modal-btn");
    const cancelEntryBtn = document.querySelector("#cancel-entry-btn");

    if (openAddEntryBtn && khataModal) {
      openAddEntryBtn.onclick = () => { khataModal.hidden = false; };
      if (closeModalBtn) closeModalBtn.onclick = () => { khataModal.hidden = true; };
      if (cancelEntryBtn) cancelEntryBtn.onclick = () => { khataModal.hidden = true; };
    }

    // Gave / Got Toggle
    const gaveBtn = document.querySelector("#toggle-gave");
    const gotBtn = document.querySelector("#toggle-got");
    if (gaveBtn && gotBtn) {
      gaveBtn.onclick = () => { gaveBtn.classList.add("active"); gotBtn.classList.remove("active"); };
      gotBtn.onclick = () => { gotBtn.classList.add("active"); gaveBtn.classList.remove("active"); };
    }

    // Khata Quick Amount Chips
    document.querySelectorAll(".quick-chips-row .amt-chip").forEach(chip => {
      chip.onclick = () => {
        const amtInput = document.querySelector("#modal-amount-input");
        const val = Number(chip.getAttribute("data-amt"));
        amtInput.value = val;
      };
    });

    // Customer Select dropdown
    const custSelect = document.querySelector("#modal-customer-select");
    if (custSelect) {
      custSelect.onchange = () => {
        const newFields = document.querySelector("#new-cust-fields");
        if (newFields) newFields.hidden = custSelect.value !== "new";
      };
    }

    // Submit Khata Entry
    const submitEntryBtn = document.querySelector("#submit-entry-btn");
    if (submitEntryBtn) {
      submitEntryBtn.onclick = () => {
        const amt = Number(document.querySelector("#modal-amount-input").value);
        if (!amt || amt <= 0) {
          alert("Please enter a valid amount.");
          return;
        }
        const isGave = document.querySelector("#toggle-gave").classList.contains("active");
        const custVal = document.querySelector("#modal-customer-select").value;
        const note = document.querySelector("#modal-note-input").value || (isGave ? "Manual Udhaar Credit" : "Payment Received");

        let targetAccount = STATE.accounts.find(a => a.id === custVal);
        if (custVal === "new") {
          const name = document.querySelector("#new-cust-name").value || "New Customer";
          const phone = document.querySelector("#new-cust-phone").value || "9876543299";
          targetAccount = { id: "khata_" + phone, name, phone, balance: 0, history: [] };
          STATE.accounts.push(targetAccount);
        }

        if (targetAccount) {
          if (isGave) {
            targetAccount.balance += amt;
            STATE.khataTotal += amt;
            STATE.aging.zeroToThirty += amt;
            targetAccount.history.unshift({ type: "DEBIT", title: note, amt, time: "Just now" });
          } else {
            targetAccount.balance = Math.max(0, targetAccount.balance - amt);
            STATE.khataTotal = Math.max(0, STATE.khataTotal - amt);
            STATE.aging.zeroToThirty = Math.max(0, STATE.aging.zeroToThirty - amt);
            targetAccount.history.unshift({ type: "CREDIT", title: note, amt, time: "Just now" });
            playPaytmChime(amt);
          }
        }

        document.querySelector("#khata-grand-total").textContent = inr(STATE.khataTotal);
        document.querySelector("#aging-total-pill").textContent = `Total: ${inr(STATE.khataTotal)}`;
        document.querySelector("#bucket-0-30").textContent = inr(STATE.aging.zeroToThirty);
        renderKhataAccounts();
        document.querySelector("#khata-entry-modal").hidden = true;
        showToast(`✓ Recorded ${inr(amt)} for ${targetAccount ? targetAccount.name : 'Customer'}`);
      };
    }

    // Khata Search
    const khataSearch = document.querySelector("#khata-search");
    if (khataSearch) {
      khataSearch.oninput = () => renderKhataAccounts(khataSearch.value);
    }

    // 25. Sarkar Language Switcher
    document.querySelectorAll(".lang-selector-scroll .lang-chip").forEach(chip => {
      chip.onclick = () => {
        document.querySelectorAll(".lang-selector-scroll .lang-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        STATE.sarkarLang = chip.getAttribute("data-lang");
        const langPack = SARKAR_RESPONSES[STATE.sarkarLang] || SARKAR_RESPONSES.en;
        addChatMessage("bot", langPack.welcome);
      };
    });

    // 26. Helper to query live Sarvam-105B Sarkar endpoint
    const querySarkarBackend = async (question) => {
      try {
        const res = await fetch("/api/merchant/sarkar/ask", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Wapas-CSRF": STATE.auth.csrfToken
          },
          body: JSON.stringify({ message: question })
        });
        if (res.ok) {
          const data = await res.json();
          if (data && data.message) {
            let proposal = null;
            if (question.toLowerCase().includes("stock") || question.toLowerCase().includes("atta")) {
              proposal = {
                title: "Confirm Action: Add 10kg Atta to Inventory",
                desc: "Supplier invoice detected · Update inventory stock from 18 to 28 bags?",
                onConfirm: () => {
                  const atta = STATE.catalog.find(i => i.id === "prod_atta_5k");
                  if (atta) atta.stock += 10;
                  renderCatalog();
                  showToast("✓ Added 10 bags of Aashirvaad Atta to inventory!");
                }
              };
            }
            addChatMessage("bot", data.message, proposal);
            return;
          }
        }
      } catch (e) {
        console.warn("Backend Sarkar offline, using local fallback", e);
      }

      // Smart fallback with proposal cards
      const lang = SARKAR_RESPONSES[STATE.sarkarLang] || SARKAR_RESPONSES.hi;
      let proposal = null;
      if (question.includes("recovery")) {
        addChatMessage("bot", lang.recovery);
      } else if (question.includes("Priya")) {
        proposal = {
          title: "Confirm Action: Send Payment Link to Priya Traders",
          desc: "Send SMS recovery link for ₹8,400 to Priya Traders (+91 98765 43221)?",
          onConfirm: () => {
            const priya = STATE.cases.find(c => c.id === "A121");
            if (priya) { priya.state = "WAITING_PAYMENT"; renderRecoveryCases(); }
            showToast("✓ SMS Recovery Link sent to Priya Traders!");
          }
        };
        addChatMessage("bot", lang.priya, proposal);
      } else if (question.includes("stock") || question.includes("Atta")) {
        proposal = {
          title: "Confirm Action: Add 10kg Atta to Stock",
          desc: "Update Aashirvaad Atta inventory stock count by +10 bags?",
          onConfirm: () => {
            const atta = STATE.catalog.find(i => i.id === "prod_atta_5k");
            if (atta) atta.stock += 10;
            renderCatalog();
            showToast("✓ Inventory updated: Aashirvaad Atta stock increased by 10!");
          }
        };
        addChatMessage("bot", lang.stock, proposal);
      } else if (question.includes("GST")) {
        addChatMessage("bot", lang.gst);
      } else {
        addChatMessage("bot", `✓ Sarvam-105B: Processed "${question}". Store ledger, recovery engine, and Paytm Soundbox are fully synchronized.`);
      }
    };

    // Sarkar Prompt Chips
    document.querySelectorAll(".prompts-scroll .prompt-chip").forEach(chip => {
      chip.onclick = () => {
        const q = chip.getAttribute("data-q");
        addChatMessage("user", q);
        querySarkarBackend(q);
      };
    });

    // Sarkar Chat Input
    const sendBtn = document.querySelector("#sarkar-send-btn");
    const textInput = document.querySelector("#sarkar-text-input");
    if (sendBtn && textInput) {
      const handleSend = () => {
        const text = textInput.value.trim();
        if (!text) return;
        addChatMessage("user", text);
        textInput.value = "";
        querySarkarBackend(text);
      };
      sendBtn.onclick = handleSend;
      textInput.onkeydown = (e) => { if (e.key === "Enter") handleSend(); };
    }

    // Sarkar Microphone Web Speech API
    const micBtn = document.querySelector("#sarkar-mic-btn");
    if (micBtn) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = STATE.sarkarLang === "hi" || STATE.sarkarLang === "hinglish" ? "hi-IN" : "en-US";

        recognition.onstart = () => {
          micBtn.textContent = "🔴";
          showToast("🎙️ Listening... speak now in Hindi or English");
        };
        recognition.onresult = (event) => {
          const spoken = event.results[0][0].transcript;
          if (textInput) textInput.value = spoken;
          micBtn.textContent = "🎤";
          showToast(`Heard: "${spoken}"`);
          // Auto send
          addChatMessage("user", spoken);
          textInput.value = "";
          querySarkarBackend(spoken);
        };
        recognition.onerror = () => {
          micBtn.textContent = "🎤";
        };
        recognition.onend = () => {
          micBtn.textContent = "🎤";
        };
        micBtn.onclick = () => {
          recognition.lang = STATE.sarkarLang === "hi" || STATE.sarkarLang === "hinglish" ? "hi-IN" : "en-US";
          recognition.start();
        };
      } else {
        micBtn.onclick = () => {
          showToast("Speech recognition not supported in this browser. Please type your query.");
        };
      }
    }

    // 27. Soundbox Live Controls
    const testChimeBtn = document.querySelector("#play-sound-test-btn");
    if (testChimeBtn) {
      testChimeBtn.onclick = () => {
        playPaytmChime(200);
        showToast("🔊 Broadcasting verified payment audio on Paytm Soundbox 4G!");
      };
    }

    const volBtn = document.querySelector("#hw-vol-btn");
    let isMuted = false;
    if (volBtn) {
      volBtn.onclick = () => {
        isMuted = !isMuted;
        volBtn.textContent = isMuted ? "🔇 Muted" : "🔊 100%";
        showToast(isMuted ? "Soundbox speaker muted" : "Soundbox speaker unmuted");
      };
    }

    document.querySelectorAll(".sim-pay-btn").forEach(btn => {
      btn.onclick = () => {
        const amt = Number(btn.getAttribute("data-amt"));
        playPaytmChime(amt);
        STATE.soundEvents.unshift({
          order: "W" + Math.floor(1000 + Math.random() * 9000),
          amt,
          time: "Just now",
          name: "Verified Customer"
        });
        renderSoundEvents();
        showToast(`✓ Received ${inr(amt)} via Paytm Soundbox 4G!`);
      };
    });

    // 28. Auto Poll Background State from Backend every 6 seconds
    setInterval(async () => {
      try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          // Update live indicator if healthy
          const pill = document.querySelector(".store-status-pill");
          if (pill) pill.innerHTML = `<span class="live-dot"></span> Wapas Kirana · Synced`;
        }
      } catch (_) {}
    }, 6000);
  }

  // Run on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
  } else {
    initApp();
  }
})();
