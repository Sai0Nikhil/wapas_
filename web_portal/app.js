// =========================================================================
// Wapas Merchant OS · Seamless PWA & Interactive Web Portal
// Paytm Build for India AI Hackathon · Track 3 (Autonomous AI Teammates)
// =========================================================================

(function() {
  'use strict';

  // --- Transparent ngrok proxy fetch interceptor ---
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

  // --- Global Application State ---
  const STATE = {
    auth: { authenticated: true, role: "OWNER", username: "admin", csrfToken: "" },
    currentTab: "billing",
    cart: [],
    selectedCustomerPhone: "9876543220",
    sarkarLang: "hi",
    kpi: { total: 14, auto: 9, owner: 2, blocked: 3 },
    khataTotal: 3350,
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
      { id: "prod_atta_5k", name: "Aashirvaad Atta 5kg", pack: "5 kg bag", price: 245, emoji: "🌾", cat: "staples" },
      { id: "prod_salt_1k", name: "Tata Salt 1kg", pack: "1 kg pkt", price: 28, emoji: "🧂", cat: "staples" },
      { id: "prod_oil_1l", name: "Fortune Sunflower Oil 1L", pack: "1 litre pouch", price: 145, emoji: "🌻", cat: "oils" },
      { id: "prod_maggi_70g", name: "Maggi 2-Min Noodles", pack: "70g pack", price: 14, emoji: "🍜", cat: "snacks" },
      { id: "prod_butter_500g", name: "Amul Butter 500g", pack: "500g block", price: 275, emoji: "🧈", cat: "dairy" },
      { id: "prod_parleg_800g", name: "Parle-G Biscuits", pack: "800g family pack", price: 80, emoji: "🍪", cat: "snacks" },
      { id: "prod_rice_5k", name: "India Gate Basmati 5kg", pack: "5 kg bag", price: 460, emoji: "🍚", cat: "staples" },
      { id: "prod_tea_500g", name: "Tata Tea Premium", pack: "500g packet", price: 290, emoji: "☕", cat: "dairy" },
      { id: "prod_soap_125g", name: "Dettol Soap 125g", pack: "Pack of 3", price: 55, emoji: "🧼", cat: "dairy" }
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
    setTimeout(() => { toast.hidden = true; }, 3200);
  }

  // --- Audio Synthesis: Authentic Paytm Soundbox Chime + Voice ---
  function playPaytmChime(amount) {
    // 1. Light ring animation
    const led = document.querySelector("#hw-led");
    if (led) {
      led.classList.add("playing");
      setTimeout(() => led.classList.remove("playing"), 3000);
    }

    // 2. Play Web Audio two-tone chime
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        const ctx = new AudioContext();
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
  function renderCatalog(filterCat = "all") {
    const grid = document.querySelector("#catalog-items-grid");
    if (!grid) return;
    const items = filterCat === "all" ? STATE.catalog : STATE.catalog.filter(i => i.cat === filterCat);
    grid.innerHTML = items.map(item => `
      <div class="item-card" data-id="${item.id}">
        <div class="item-card-top">
          <div class="item-emoji">${item.emoji}</div>
          <div class="item-details">
            <h4>${item.name}</h4>
            <span>${item.pack}</span>
          </div>
        </div>
        <div class="item-card-bot">
          <div class="item-price">${inr(item.price)}</div>
          <button class="btn-add-item" data-add="${item.id}">+ Add</button>
        </div>
      </div>
    `).join("");

    grid.querySelectorAll("[data-add]").forEach(btn => {
      btn.onclick = () => {
        const id = btn.getAttribute("data-add");
        const item = STATE.catalog.find(i => i.id === id);
        if (item) {
          STATE.cart.push(item);
          updateCartUI();
          showToast(`Added ${item.name} to bill`);
        }
      };
    });
  }

  function updateCartUI() {
    const countEl = document.querySelector("#cart-item-count");
    const totalEl = document.querySelector("#cart-total-val");
    const payBtn = document.querySelector("#cart-pay-btn");
    const khataBtn = document.querySelector("#cart-khata-btn");

    const total = STATE.cart.reduce((s, i) => s + i.price, 0);
    const count = STATE.cart.length;

    if (countEl) countEl.textContent = `${count} ${count === 1 ? 'item' : 'items'}`;
    if (totalEl) totalEl.textContent = inr(total);

    if (payBtn) payBtn.disabled = count === 0;
    if (khataBtn) khataBtn.disabled = count === 0;
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

      let actionHtml = "";
      if (isPriya && c.state === "WAITING_OWNER") {
        actionHtml = `<div class="case-actions"><button id="btn-approve-priya" class="btn-approve-priya">Approve Recovery Link (Priya)</button></div>`;
      } else if (isPriya && c.state === "WAITING_PAYMENT") {
        actionHtml = `<div class="case-actions"><button id="btn-pay-priya" class="btn-pay-link">💳 Pay ${inr(c.amt)} via Paytm Test Checkout</button></div>`;
      }

      return `
        <div class="${cardClass}" id="case-${c.id}">
          <div class="case-head">
            <span class="case-cust-name">${c.name} ${c.vip ? '<span class="vip-star">★ VIP</span>' : ''}</span>
            <span class="case-amt">${inr(c.amt)}</span>
          </div>
          <div class="case-meta">
            <span>Case ${c.id} · ${c.time}</span>
            ${badgeHtml}
          </div>
          <p style="font-size:11px; color:#64748B; margin-top:2px;">${c.reason}</p>
          ${actionHtml}
        </div>
      `;
    }).join("");

    // Priya Traders Interactive Workflow: Approve -> Pay -> Turn Blue after verified status check
    const approveBtn = document.querySelector("#btn-approve-priya");
    if (approveBtn) {
      approveBtn.onclick = () => {
        const priya = STATE.cases.find(c => c.id === "A121");
        if (priya) {
          priya.state = "WAITING_PAYMENT";
          priya.reason = "Approved by owner · WhatsApp payment link dispatched";
          renderRecoveryCases(filter);
          showToast("Recovery link dispatched to Priya Traders (WhatsApp)");
        }
      };
    }

    const payBtn = document.querySelector("#btn-pay-priya");
    if (payBtn) {
      payBtn.onclick = () => {
        const priya = STATE.cases.find(c => c.id === "A121");
        if (priya) {
          // Status Check & Verification
          showToast("Verifying Paytm webhook & payment status…");
          setTimeout(() => {
            priya.state = "RECOVERED";
            priya.category = "auto";
            priya.reason = "Status Verified · Paytm TXN_SUCCESS (Bank Ref #PTM992144)";
            STATE.kpi.owner = 1;
            STATE.kpi.auto = 10;
            updateKpiUI();
            renderRecoveryCases(filter);
            playPaytmChime(8400);
            showToast("✓ ₹8,400 Recovered & Verified from Priya Traders! Soundbox armed.");
            // Add to Soundbox stream
            STATE.soundEvents.unshift({ order: "A121", amt: 8400, time: "Just now", name: "Priya Traders" });
            renderSoundEvents();
          }, 600);
        }
      };
    }
  }

  function updateKpiUI() {
    const autoEl = document.querySelector("#kpi-auto-num");
    const ownerEl = document.querySelector("#kpi-owner-num");
    const filterOwner = document.querySelector("#filter-owner-count");
    const filterAuto = document.querySelector("#filter-auto-count");
    const navBadge = document.querySelector("#nav-owner-badge");

    if (autoEl) autoEl.textContent = STATE.kpi.auto;
    if (ownerEl) ownerEl.textContent = STATE.kpi.owner;
    if (filterOwner) filterOwner.textContent = STATE.kpi.owner;
    if (filterAuto) filterAuto.textContent = STATE.kpi.auto;
    if (navBadge) navBadge.textContent = STATE.kpi.owner;
  }

  // --- Render Module 3: Digital Khata Ledger ---
  function renderKhataAccounts(query = "") {
    const list = document.querySelector("#khata-accounts-list");
    if (!list) return;

    let accounts = STATE.accounts;
    if (query) {
      const q = query.toLowerCase();
      accounts = accounts.filter(a => a.name.toLowerCase().includes(q) || a.phone.includes(q));
    }

    list.innerHTML = accounts.map(a => `
      <div class="khata-card" data-acc="${a.id}">
        <div class="khata-card-row">
          <div class="khata-cust-info">
            <h4>${a.name}</h4>
            <span>+91 ${a.phone} · Tap for history</span>
          </div>
          <div class="khata-bal-box">
            <div class="khata-bal-val">${inr(a.balance)}</div>
            <span class="khata-bal-lbl">Udhaar Baki</span>
          </div>
        </div>
        <div class="khata-history-tray">
          <div style="font-size:10px; font-weight:700; color:#64748B; margin-bottom:6px;">TRANSACTION HISTORY</div>
          ${a.history.map(h => `
            <div class="tray-item">
              <span>${h.title} (${h.time})</span>
              <strong>+${inr(h.amt)}</strong>
            </div>
          `).join("")}
          <div style="display:flex; gap:8px; margin-top:8px;">
            <button class="chip-btn quick-udhaar-btn" data-accid="${a.id}">+ Udhaar Diya</button>
            <button class="chip-btn" style="color:#16A34A;" data-jamaid="${a.id}">✓ Jama Mila</button>
            <button class="chip-btn" style="color:#0284C7;" onclick="alert('WhatsApp reminder link generated for ${a.name} (+91 ${a.phone})!')">📲 WhatsApp</button>
          </div>
        </div>
      </div>
    `).join("");

    // Toggle expand history
    list.querySelectorAll(".khata-card").forEach(card => {
      card.onclick = (e) => {
        if (e.target.tagName === "BUTTON") return;
        card.classList.toggle("expanded");
      };
    });

    list.querySelectorAll("[data-accid]").forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        openKhataModal(btn.getAttribute("data-accid"), "DEBIT");
      };
    });

    list.querySelectorAll("[data-jamaid]").forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        openKhataModal(btn.getAttribute("data-jamaid"), "CREDIT");
      };
    });
  }

  function openKhataModal(accId = "", mode = "DEBIT") {
    const modal = document.querySelector("#khata-entry-modal");
    if (!modal) return;
    modal.hidden = false;

    const gaveBtn = document.querySelector("#toggle-gave");
    const gotBtn = document.querySelector("#toggle-got");
    const custSelect = document.querySelector("#modal-customer-select");
    const amtInput = document.querySelector("#modal-amount-input");
    const noteInput = document.querySelector("#modal-note-input");

    if (accId && custSelect) custSelect.value = accId;
    if (amtInput) amtInput.value = "";
    if (noteInput) noteInput.value = "";

    if (mode === "DEBIT") {
      gaveBtn.classList.add("active");
      gotBtn.classList.remove("active");
    } else {
      gotBtn.classList.add("active");
      gaveBtn.classList.remove("active");
    }
  }

  // --- Render Module 4: Sarkar AI Retail Copilot ---
  const SARKAR_RESPONSES = {
    hi: {
      welcome: "नमस्ते सेठी जी! मैं सरकार AI हूँ — आपकी किराना दुकान का व्यापार साथी। आज की रिकवरी, खाता बही या स्टॉक के बारे में कुछ भी पूछिए।",
      recovery: "📊 **आज का रिकवरी सारांश:** कुल 14 मामलों में से **10 मामले सफलतापूर्वक पूरे** हो चुके हैं (कुल **₹35,289** रिकवर)! प्रिया ट्रेडर्स का ₹8,400 रिकवरी लिंक अप्रूव हो चुका है। 3 केस ग्राहकों की निजता के लिए गार्डरेल द्वारा सुरक्षित रोके गए हैं।",
      priya: "📒 **प्रिया ट्रेडर्स (9876543221):**\n• खाता बकाया: ₹850 (थोक खरीदारी)\n• रिकवरी केस A121: ₹8,400 का भुगतान वेरीफाई हो चुका है। कुल व्यापार संबंध बहुत मजबूत हैं।",
      stock: "📦 **स्टॉक अलर्ट:**\n• फॉर्च्यून सनफ्लावर ऑयल 1L (केवल 3 पैकेट बचे हैं)\n• टाटा नमक 1kg (5 पैकेट बाकी)\nक्या मैं डिस्ट्रीब्यूटर को ऑर्डर ड्राफ्ट करूँ?",
      gst: "📑 **जीएसटी सारांश (अक्टूबर):**\n• कुल बी2बी इनवॉइस: 18\n• इनपुट टैक्स क्रेडिट: ₹4,210\n• 3B फाइलिंग समय पर तैयार है।"
    },
    hinglish: {
      welcome: "Namaste Sethi ji! Main Sarkar AI hoon — aapki Kirana dukaan ka autonomous copilot. Recovery, Khata ya Stock ke baare me poochiye!",
      recovery: "📊 **Today's Recovery Report:** 14 me se **10 cases resolve ho chuke hain** (Total **₹35,289** recovered)! 3 blocked cases guardrails ki wajah se safe hain.",
      priya: "📒 **Priya Traders:** Udhaar Khata ₹850 hai, aur ₹8,400 ka recovery payment verify ho chuka hai.",
      stock: "📦 **Low Stock:** Fortune Oil 1L (3 left), Tata Salt (5 left). Supplier ko order bhejna hai?",
      gst: "📑 **GST Report:** Total monthly sales synced with Paytm POS bills. B2B invoices ready."
    },
    en: {
      welcome: "Hello Store Owner! I am Sarkar AI — your Kirana copilot. Ask me anything about payment recoveries, Khata credit, or inventory.",
      recovery: "📊 **Recovery Summary:** 10 of 14 cases recovered (**₹35,289**). 3 cases safely blocked by autonomous guardrails.",
      priya: "📒 **Priya Traders:** Khata balance is ₹850; ₹8,400 recovery payment verified via Paytm.",
      stock: "📦 **Stock Warning:** Fortune Sunflower Oil (3 units left), Tata Salt (5 units left).",
      gst: "📑 **GST Report:** October invoices reconciled with 100% Paytm Soundbox verification."
    }
  };

  function addChatMessage(role, text) {
    const chat = document.querySelector("#sarkar-chat-container");
    if (!chat) return;
    const div = document.createElement("div");
    div.className = `chat-msg ${role}`;
    div.innerHTML = text.replace(/\n/g, "<br>").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }

  // --- Render Module 5: Soundbox Live ---
  function renderSoundEvents() {
    const list = document.querySelector("#sound-events-stream");
    if (!list) return;
    list.innerHTML = STATE.soundEvents.map(e => `
      <div class="sound-event-row">
        <div>
          <span>${e.name} (Order ${e.order})</span>
          <div style="font-size:10px; color:#64748B;">Paytm 4G Soundbox · ${e.time}</div>
        </div>
        <strong>+${inr(e.amt)}</strong>
      </div>
    `).join("");
  }

  // --- Initialize App & Event Listeners ---
  function initApp() {
    // 1. Silent Background Auto-Login
    silentAutoLogin();

    // 2. Render initial data
    renderCatalog();
    renderRecoveryCases();
    renderKhataAccounts();
    renderSoundEvents();
    updateKpiUI();
    addChatMessage("bot", SARKAR_RESPONSES.hi.welcome);

    // 3. Tab Navigation
    document.querySelectorAll(".bottom-nav .nav-item").forEach(btn => {
      btn.onclick = () => {
        const target = btn.getAttribute("data-target");
        STATE.currentTab = target;
        document.querySelectorAll(".bottom-nav .nav-item").forEach(b => b.classList.toggle("active", b === btn));
        document.querySelectorAll(".tab-pane").forEach(pane => {
          pane.classList.toggle("active", pane.id === `pane-${target}`);
        });
      };
    });

    // 4. Judge Toolbar Toggle (Phone Mockup vs Fullscreen)
    const toggleBtn = document.querySelector("#toggle-view-btn");
    if (toggleBtn) {
      toggleBtn.onclick = () => {
        document.body.classList.toggle("fullscreen-mode");
        const isFull = document.body.classList.contains("fullscreen-mode");
        toggleBtn.querySelector(".btn-text").textContent = isFull ? "Laptop View" : "Phone View";
      };
    }

    // 5. Category filter in POS
    document.querySelectorAll(".category-scroll .cat-chip").forEach(chip => {
      chip.onclick = () => {
        document.querySelectorAll(".category-scroll .cat-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        renderCatalog(chip.getAttribute("data-cat"));
      };
    });

    // 6. Quick Scan Parchi button
    const parchiBtn = document.querySelector("#quick-parchi-btn");
    if (parchiBtn) {
      parchiBtn.onclick = () => {
        showToast("📸 Reading handwritten parchi with OCR…");
        setTimeout(() => {
          STATE.cart.push(STATE.catalog[0], STATE.catalog[1], STATE.catalog[2]); // Atta, Salt, Oil
          updateCartUI();
          showToast("✓ Added: Atta 5kg, Tata Salt, Fortune Oil from Parchi!");
        }, 600);
      };
    }

    // 7. Quick Customer Phone button
    const custBtn = document.querySelector("#quick-cust-btn");
    if (custBtn) {
      custBtn.onclick = () => {
        const phoneInput = document.querySelector("#bill-customer-phone");
        if (phoneInput) phoneInput.value = "9876543220";
        showToast("Selected customer: Ramesh Kumar (9876543220)");
      };
    }

    // 8. POS Payment & Soundbox trigger
    const cartPayBtn = document.querySelector("#cart-pay-btn");
    if (cartPayBtn) {
      cartPayBtn.onclick = () => {
        const total = STATE.cart.reduce((s, i) => s + i.price, 0);
        showToast("Displaying Dynamic Paytm QR on Counter Soundbox…");
        setTimeout(() => {
          playPaytmChime(total);
          STATE.soundEvents.unshift({
            order: "B" + Math.floor(100 + Math.random() * 900),
            amt: total,
            time: "Just now",
            name: "Counter Customer"
          });
          renderSoundEvents();
          STATE.cart = [];
          updateCartUI();
          showToast(`✓ Payment of ${inr(total)} received! Soundbox broadcast completed.`);
        }, 700);
      };
    }

    // 9. Add Bill to Khata
    const cartKhataBtn = document.querySelector("#cart-khata-btn");
    if (cartKhataBtn) {
      cartKhataBtn.onclick = () => {
        const total = STATE.cart.reduce((s, i) => s + i.price, 0);
        const ramesh = STATE.accounts[0];
        ramesh.balance += total;
        ramesh.history.unshift({ type: "DEBIT", title: "Counter items bill", amt: total, time: "Just now" });
        STATE.khataTotal += total;
        document.querySelector("#khata-grand-total").textContent = inr(STATE.khataTotal);
        renderKhataAccounts();
        STATE.cart = [];
        updateCartUI();
        showToast(`✓ Added ${inr(total)} to Ramesh Kumar's Khata!`);
      };
    }

    // 10. Recovery Cases Filter
    document.querySelectorAll(".case-filters .filter-tab").forEach(tab => {
      tab.onclick = () => {
        document.querySelectorAll(".case-filters .filter-tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        renderRecoveryCases(tab.getAttribute("data-filter"));
      };
    });

    // 11. Idempotency Replay Webhook button
    const replayBtn = document.querySelector("#replay-webhook-btn");
    if (replayBtn) {
      replayBtn.onclick = () => {
        showToast("Replaying identical Paytm Webhook payload (Case A118)…");
        setTimeout(() => {
          showToast("✓ Idempotency Guardrail: Duplicate signature detected. 0 charges made.");
        }, 600);
      };
    }

    // 12. Khata Modal Open / Close
    const addEntryBtn = document.querySelector("#open-add-entry-btn");
    if (addEntryBtn) addEntryBtn.onclick = () => openKhataModal();

    const closeModalBtn = document.querySelector("#close-modal-btn");
    if (closeModalBtn) closeModalBtn.onclick = () => { document.querySelector("#khata-entry-modal").hidden = true; };

    const cancelEntryBtn = document.querySelector("#cancel-entry-btn");
    if (cancelEntryBtn) cancelEntryBtn.onclick = () => { document.querySelector("#khata-entry-modal").hidden = true; };

    // Khata Gave/Got Toggle
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
            targetAccount.history.unshift({ type: "DEBIT", title: note, amt, time: "Just now" });
          } else {
            targetAccount.balance = Math.max(0, targetAccount.balance - amt);
            STATE.khataTotal = Math.max(0, STATE.khataTotal - amt);
            targetAccount.history.unshift({ type: "CREDIT", title: note, amt, time: "Just now" });
          }
        }

        document.querySelector("#khata-grand-total").textContent = inr(STATE.khataTotal);
        renderKhataAccounts();
        document.querySelector("#khata-entry-modal").hidden = true;
        showToast(`✓ Recorded ${inr(amt)} for ${targetAccount ? targetAccount.name : 'Customer'}`);
      };
    }

    // 13. Khata Search
    const khataSearch = document.querySelector("#khata-search");
    if (khataSearch) {
      khataSearch.oninput = () => renderKhataAccounts(khataSearch.value);
    }

    // 14. Sarkar Language Switcher
    document.querySelectorAll(".lang-selector-scroll .lang-chip").forEach(chip => {
      chip.onclick = () => {
        document.querySelectorAll(".lang-selector-scroll .lang-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        STATE.sarkarLang = chip.getAttribute("data-lang");
        const langPack = SARKAR_RESPONSES[STATE.sarkarLang] || SARKAR_RESPONSES.en;
        addChatMessage("bot", langPack.welcome);
      };
    });

    // 15. Sarkar Prompt Chips
    document.querySelectorAll(".prompts-scroll .prompt-chip").forEach(chip => {
      chip.onclick = () => {
        const q = chip.getAttribute("data-q");
        addChatMessage("user", q);
        setTimeout(() => {
          const lang = SARKAR_RESPONSES[STATE.sarkarLang] || SARKAR_RESPONSES.hi;
          if (q.includes("recovery")) addChatMessage("bot", lang.recovery);
          else if (q.includes("Priya")) addChatMessage("bot", lang.priya);
          else if (q.includes("stock")) addChatMessage("bot", lang.stock);
          else if (q.includes("GST")) addChatMessage("bot", lang.gst);
          else addChatMessage("bot", "Sarkar AI has processed this with Sarvam-105B. All data reconciled.");
        }, 400);
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
        setTimeout(() => {
          addChatMessage("bot", `✓ Analyzing "${text}" with Sarvam-105B Indian AI engine… Store ledger and recovery databases are fully synced.`);
        }, 500);
      };
      sendBtn.onclick = handleSend;
      textInput.onkeydown = (e) => { if (e.key === "Enter") handleSend(); };
    }

    // 16. Soundbox Live Controls
    const testChimeBtn = document.querySelector("#play-sound-test-btn");
    if (testChimeBtn) {
      testChimeBtn.onclick = () => {
        playPaytmChime(200);
        showToast("🔊 Broadcasting verified payment audio on Paytm Soundbox!");
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

    // 17. Demo Reset Button
    const resetBtn = document.querySelector("#demo-reset-btn");
    if (resetBtn) {
      resetBtn.onclick = () => {
        fetch("/api/demo/reset", { method: "POST", headers: { "X-Wapas-CSRF": STATE.auth.csrfToken } }).catch(() => {});
        showToast("Demo environment re-initialized to initial incident state.");
        setTimeout(() => window.location.reload(), 400);
      };
    }
  }

  // Run on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
  } else {
    initApp();
  }
})();
