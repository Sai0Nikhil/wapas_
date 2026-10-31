# Wapas Merchant OS — 3-Minute Hackathon Demo Script
**Paytm Build for India AI Hackathon (Bengaluru) — Track 3: Autonomous AI Teammates**
*"AI that doesn't just respond, it gets the job done."*

---

## Architecture Summary
- **Backend:** `wapas-merchant-os` (FastAPI + SQLModel + Sarvam 105B LLM + Saaras STT & Bulbul TTS).
- **Client:** `wapas_app` (Flutter 3.32+ on Android, iOS, Web). Layered `ApiClient`, Riverpod state, HTTPS-ready runtime configurable Base URL, Android Network Security Config.
- **Zero Mock Data:** All screens consume live backend endpoints with double-submit CSRF and UUID idempotency keys.

---

## 0:00 - 0:30 | The Hook: Failed Payment Autonomous Recovery
1. **Context:** Kirana stores lose ₹4,000–₹12,000 weekly to failed UPI transactions where the customer walks away thinking the payment went through.
2. **Open Tab 2: Recovery Control Tower (`RecoveryTowerScreen`)**:
   - Point out the **Live Header**: Recovered ₹, Flagged, Contacted, Waiting Owner.
   - Point out the Gateway status chip: `SIMULATED` (with Fake Gateway) or `PAYTM LIVE`.
   - Tap on case `REC-1092` (SBI Server Timeout, ₹1,420).
   - Show the **Evidence Sheet**: Root-cause diagnosis (`SBI Core Banking Gateway 504`), policy evaluation (`ALLOW`), telemetry risk score (0.94 confidence).
   - Tap **"1-TAP APPROVE"**:
     - Shows optimistic UI transition.
     - Backend fires automated WhatsApp recovery link in Hindi with a 15-minute hold on inventory.

---

## 0:30 - 1:00 | Real Hardware Feedback: Paytm Soundbox Live
1. **Switch to Tab 5: Soundbox Live (`SoundboxFeedScreen`)**:
   - Point to hardware status badge: `Paytm Soundbox 4G`, Online status, Battery level.
   - Tap **"Test Speaker Voice Broadcast"**:
     - Native TTS speaks aloud in Hindi: *"Paytm par 1,420 rupaye praapt hue"* (₹1,420 received on Paytm).
   - Show live event log updating from `/api/merchant/sound/events` with server cursor acknowledgement.

---

## 1:00 - 1:45 | POS Counter Billing & Dynamic Paytm UPI QR
1. **Switch to Tab 1: Billing (`PosBillingScreen`)**:
   - Search for `"Atta"`: Show live catalog products from `/api/merchant/catalog/products` with real inventory stock left.
   - Tap **"Scan Parchi"**:
     - Demonstrates on-device Google ML Kit OCR scanning a handwritten Kirana slip.
     - Extracted draft items review modal appears with editable quantities and confidence badges.
     - Tap **"CONFIRM & ADD TO BILL"**: Draft bill is created on the backend via `POST /api/merchant/bills`.
   - Tap **"COLLECT"**:
     - Tap **"Paytm Dynamic UPI QR"**:
     - Backend transitions bill to `ISSUED` and generates a dedicated collection link.
     - Dynamic QR renders on screen with `qr_flutter`.
     - Tap **"Simulate Verified"** or let the customer scan to pay.
     - Thermal receipt modal appears with bill number, paise breakdown, and print preview!

---

## 1:45 - 2:30 | Digital Khata Ledger & Voice Record
1. **Switch to Tab 3: Khata Ledger (`KhataLedgerScreen`)**:
   - Highlight the **Credit Aging & Risk Summary**: 0-30 days, 31-60 days, 61-90 days, 90+ days brackets from `/api/merchant/khata/aging`.
   - Tap on **Ramesh Kumar** (₹3,450 outstanding):
     - Opens the full Ledger Sheet from `/api/merchant/khata/accounts/{id}`.
     - Show immutable entries with balance after each transaction.
   - Tap **"Pay Link"**: Generates instant Paytm collection short URL with 1-tap WhatsApp reminder text.
   - Tap **"Repay"**: Record ₹500 cash repayment with idempotency key. Notice balance automatically drops to ₹2,950.
   - Tap **"CSV"**: Shows downloadable and exportable statement attachment from `/api/merchant/khata/accounts/{id}/statement.csv`.

---

## 2:30 - 3:00 | Sarkar AI: The Kirana Copilot on Sarvam 105B
1. **Switch to Tab 4: Sarkar AI (`SarkarCopilotScreen`)**:
   - Tap the microphone or type:
     *"Ramesh ka khata kitna baaki hai aur atta ka stock kitna hai?"*
   - Real backend endpoint `POST /api/merchant/sarkar/ask` responds powered by Sarvam-105B:
     - Shows provider trace chip: `sarvam-105b` / latency.
     - Structured data card renders current Khata balance and Atta stock.
   - For stock adjustments or refunds:
     - Sarkar AI presents an interactive **Confirmation Card** with `confirmation_token` ensuring safe merchant approval before any database write.

---

## Key Takeaway for Judges
Wapas is not a chat wrapper. It is a complete **Merchant Operating System** that connects Paytm payment rails, offline Kirana hardware (Soundbox, Camera OCR, thermal printers), and an autonomous AI teammate that tracks and recovers lost revenue around the clock.
