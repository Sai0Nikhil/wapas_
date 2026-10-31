# Wapas Mobile App (`wapas_app`)

The official mobile client for **Wapas Merchant OS**, built for the **Paytm Build for India AI Hackathon (Bengaluru) — Track 3: Autonomous AI Teammates: "AI that doesn't just respond, it gets the job done."**

The application has been transformed from a hardcoded UI prototype into a production-grade, reactive, and live client communicating directly with the `wapas-merchant-os` FastAPI backend.

---

## What Was Done in the Mobile App (Architecture & Features)

### 1. Layered Networking & Security Foundation
- **Layered Architecture:** Replaced the legacy prototype API service with a clean, layered structure:
  - **`lib/core/network/api_client.dart`**: Unified HTTP client supporting multi-tenant session cookie persistence (`wapas_session`), automatic double-submit CSRF header/cookie management (`wapas_csrf` / `x-wapas-csrf`), same-origin header attachment, and UUID-based idempotency keys on all mutating actions.
  - **`lib/core/network/api_exceptions.dart`**: Typed bilingual error mapping presenting user-friendly messages in both English and Hindi.
  - **Android Network Security Config**: Enforced cleartext HTTP exclusively for debug builds (`android/app/src/debug/res/xml/network_security_config.xml`); release builds are strictly HTTPS-only.
  - **State Management with Riverpod 3.x**: Migrated 100% of app state to Riverpod `Notifier` and `NotifierProvider`s, enabling dependency injection for repositories and test mockability.
  - **Runtime Configurable Base URL**: The backend server URL can be configured at runtime via the Settings screen or passed during build via `--dart-define=API_BASE_URL=...`.

---

### 2. POS Counter Billing & Paytm Dynamic UPI QR (`PosBillingScreen`)
- **Real Catalogue Integration:** Live product search and categorization powered by `CatalogRepo` (`/api/merchant/catalog/products`) with real-time stock balances and low-stock alerts.
- **Barcode & Camera Quick Scan:** Native camera capture with Google ML Kit OCR to identify barcode numbers or product labels and match them directly against the store inventory.
- **Handwritten Parchi Fast-Billing:** On-device OCR reads paper slips written by shopkeepers or customers, automatically extracting quantities, product names, and prices into an editable review sheet.
- **Full Backend Bill Lifecycle:**
  - `POST /api/merchant/bills` creates draft bills with UUID idempotency.
  - `PUT /api/merchant/bills/{id}/lines/{product_id}` updates line quantities in real time.
  - `POST /api/merchant/bills/{id}/issue` transitions the bill to `ISSUED`.
- **Payment Collection Options:**
  - **Paytm Dynamic UPI QR**: Initiates payment via `POST /api/merchant/bills/{id}/payments`, dynamically rendering a scannable QR code on screen using `qr_flutter`. Background timer polls payment status until verified.
  - **Cash Payment**: Issues thermal printable receipt with itemized breakdown.
  - **Add to Khata**: Directly charges the bill to the customer's ledger account via `POST /api/merchant/bills/{id}/khata`.
- **HTML Receipt Viewer:** Fetches server-generated printable receipts from `/api/merchant/bills/{id}/receipt`.

---

### 3. Recovery Control Tower on Live Data (`RecoveryTowerScreen`)
- **Autonomous Recovery Monitoring:** Real-time polling against `/api/state`, retrieving flagged failed UPI transactions, active cases, and recovered revenue totals.
- **Visual Gateway Badges:** Distinct chips indicating whether actions are executed via `PAYTM LIVE` or `SIMULATED` (Fake Gateway twin).
- **1-Tap Owner Approve & Skip:** Optimistic UI updates with instant rollback on network errors for owner approvals (`/api/owner/approve/{id}`) and skips (`/api/owner/skip/{id}`).
- **Case Evidence Sheet:** Inspects telemetry risk scores, root-cause diagnoses (e.g. SBI core banking timeout), decision policy traces (`ALLOW`, `ASK_OWNER`, `BLOCK`), and customer conversation threads.

---

### 4. Digital Khata Ledger & Modularization (`KhataLedgerScreen`)
- **Modular Architecture:** Split the monolithic 1,418-line screen into modular subwidgets under `lib/screens/khata/`:
  - `khata_aging_card.dart`: Credit aging risk summary displaying 0–30, 31–60, 61–90, and 90+ day brackets from `/api/merchant/khata/aging`.
  - `khata_account_detail_sheet.dart`: Customer ledger history with running balances and debit/credit breakdown.
  - `khata_repayment_dialog.dart`: Records cash/UPI repayments via `/api/merchant/khata/accounts/{id}/repayments` with idempotency.
  - `khata_voice_record_modal.dart`: Retains natural voice parsing for spoken Khata transactions in Hindi/Telugu/English.
- **Entry Reversals:** Implemented immutable entry reversals via `/api/merchant/khata/entries/{id}/reverse` with reason logging.
- **1-Tap Payment Link Sharing:** Generates instant collection links via `/api/merchant/khata/accounts/{id}/payment-links` with pre-filled WhatsApp payment reminder text.
- **Statement CSV Export:** Downloads account transaction statements from `/api/merchant/khata/accounts/{id}/statement.csv`.

---

### 5. Sarkar AI Retail Copilot on Sarvam 105B (`SarkarCopilotScreen`)
- **Real Backend AI Integration:** Connected directly to `POST /api/merchant/sarkar/ask` powered by **Sarvam-105B LLM** and **Saaras v3 STT**.
- **Voice & Text Input:** Speak or type Kirana queries in Hindi, Hinglish, Telugu, Tamil, or English.
- **Provider Trace Transparency:** Displays execution chips showing LLM engine, model version, and response latency.
- **Interactive Action Cards:** Renders confirmation cards for mutating stock adjustments or refunds with `confirmation_token` protection.

---

### 6. Paytm Soundbox Live Feed (`SoundboxFeedScreen`)
- **Hardware Twin Registration:** Automatically registers a hardware device UUID via `POST /api/merchant/sound/device`.
- **4-Second Event Polling:** Polls `/api/merchant/sound/events` with cursor tracking, deduplicating incoming payment events.
- **Server Cursor Acknowledgement:** Acknowledges processed events via `POST /api/merchant/sound/events/ack` to advance the server cursor.
- **Native Hindi Voice Announcements:** Plays real-time audio announcements (*"Paytm par [Amount] rupaye praapt hue"*) via `flutter_tts`.
- **Audio Controls:** Live mute toggle, 4G connection indicator, and test broadcast trigger.

---

### 7. Operations & Autonomous Teammates
Accessible via the Navigation Drawer in `MainNavigationShell`:
- **Catalogue & Stock Management (`CatalogManagementScreen`):**
  - Live inventory tracking with low-stock warnings.
  - Audited stock adjustments (`POST /api/merchant/catalog/products/{id}/stock-adjustments`) with positive/negative deltas and audit reasons.
  - Inventory movement audit log (`GET /api/merchant/catalog/movements`).
- **Online Storefront Orders (`OrdersScreen`):**
  - Online customer orders from `/api/merchant/orders`.
  - 1-tap fulfillment action via `/api/merchant/orders/{id}/fulfill`.
  - Storefront QR code generator (`/api/merchant/storefront/qr`) displaying the customer shopping link.
- **Autonomous Teammates Activity (`AgentActivityScreen`):**
  - Showcases the Track 3 autonomous agent actions: Morning Brief, Restock Drafts, and Autonomous Recovery Audit Trail.
- **Multi-Tenant Context & Settings (`SettingsScreen`):**
  - Store switcher via `/api/auth/memberships` and `/api/auth/switch-membership`.
  - Live server connection latency probe (`/healthz`).
  - Session logout with cookie invalidation.

---

### 8. Zero Mock Data Policy & Code Cleanliness
- **Eliminated Hardcoded Data:** Deleted all seeded mock lists from `lib/services/store_state.dart`. Screens contain zero hardcoded data.
- **Typed Models:** Replaced raw untyped maps with strongly typed models:
  - `auth_models.dart`, `billing_models.dart`, `catalog_models.dart`, `khata_models.dart`, `recovery_models.dart`, `sarkar_models.dart`, `sound_models.dart`, `order_models.dart`.
- **CI / CD Pipeline:** Added GitHub Actions CI workflow in `.github/workflows/flutter.yml`.

---

## Test Suite & Verification

The application includes a comprehensive test suite covering repositories, models, network clients, and screens with fake repositories:

```bash
$ flutter analyze
Analyzing wapas_app...
No issues found! (ran in 1.7s)

$ flutter test
00:04 +22: All tests passed!
```

### Test Breakdown
- **`test/unit/api_client_test.dart`**: Auth session parsing, bilingual exception mappings, idempotency key generation, and CSRF token handling.
- **`test/unit/billing_repo_test.dart`**: Draft bill creation, line quantity updates, bill issuance, and collection link requests.
- **`test/unit/khata_repo_test.dart`**: Account listing, aging buckets parsing, repayments, and reversal calls.
- **`test/unit/recovery_repo_test.dart`**: Live recovery state parsing and 1-tap approve/skip mutations.
- **`test/unit/sarkar_repo_test.dart`**: Sarvam-105B copilot interactions, tool trace extraction, and confirmation cards.
- **`test/unit/sound_repo_test.dart`**: Soundbox device registration and event stream processing.
- **`test/widget/screens_test.dart`**: Widget tests verifying `PosBillingScreen`, `KhataLedgerScreen`, and `SoundboxFeedScreen` with fake repositories.

---

## How to Run the App

### 1. Launch the Backend
From the root repository:
```bash
./scripts/run_local_demo.sh
```
This initializes the disposable development database, seeds Kirana products, users, Khata accounts, and recovery cases, and starts the FastAPI server on `http://0.0.0.0:8000`.

### 2. Launch the Flutter App
```bash
cd wapas_app
flutter pub get
flutter run
```

### Demo Credentials
- **Owner Role:** `admin` / `password12345678` or `demo_owner` / `WapasSecure1234!`
- **Staff Role:** `staff` / `password12345678`
- **Demo Walkthrough Guide:** See [docs/demo-script.md](file:///home/sai-nikhil/wapas/docs/demo-script.md).

### Physical Android Device Setup (over USB)
If running on a physical Android phone via USB debugging:
```bash
adb reverse tcp:8000 tcp:8000
```
This routes `http://127.0.0.1:8000` from the mobile device to the host workstation's Uvicorn backend server.
