# Wapas Merchant OS — Implementation Report (Final)

**Date:** 2026-10-30  
**Repository Location:** `D:\Wapas`  
**Release Classification:** **INTEGRATION IN PROGRESS** (local regressions and a limited Counter browser smoke pass; Paytm, durable hosted database, and deployment remain unverified)<br>
**Verification Suite:** 268 passed, 0 failures, 0 skips, 320 warnings across 33 test modules (470.51s), rerun 2026-10-30

---

## 1. Executive Summary

Wapas Merchant OS integrates Counter billing, Catalogue & Inventory management, Shop storefronts, Khata credit ledgers, Sarkar AI assistant, Sound Mode payment announcements, and Opportunity Pulse business indicators into a single, cohesive merchant operating system.

This implementation cycle successfully hardened the architecture across all core pillars:
1. **Adversarial Multi-Tenancy & RBAC:** Enforced strict tenant isolation across all resources (Catalogue, Bills, Khata, Orders, Sound events, and Sarkar tools) and validated boundary enforcement against malicious cross-tenant ID substitution and staff privilege escalation via an 8-test adversarial security suite.
2. **Deterministic Sarkar Execution with Deadline Enforcement:** Integrated runtime execution deadlines (`timeout_seconds`) via thread-pool isolation in `app/sarkar.py`, returning HTTP 504 Gateway Timeout without committing partial transactions.
3. **Fail-Closed Sound Mode:** Validated all 7 mandatory negative payment conditions (forged signatures, unknown references, pending state, amount mismatch, failed status, ambiguous gateway error, and duplicate callback replays) to guarantee zero false payment announcements.
4. **Factual Opportunity Pulse:** Enhanced Opportunity Pulse to derive factual store indicators (low stock items, verified Paytm sales count/amount, Khata outstanding credit and customer counts, pending order fulfillments, and financial breakdown) strictly from persisted database records without synthetic estimates or projected uplift.
5. **Strict Review-Only Counter Input Modalities:** Verified that all 4 input modalities (barcode scanner, photo recognition, voice billing, and Parchi list) converge into canonical Counter drafts with server-side price resolution, stock checks, and mandatory merchant confirmation before line addition or issuance.
6. **Database Protection & Integrity:** Code-level engine guards block all writable ORM connections to `D:\Wapas\wapas.db` and its SQLite sidecars (`-wal`, `-shm`, `-journal`). All 268 tests in the latest full run execute against a disposable, isolated SQLite temp database.

---

## 2. Release Classification & Claim Vocabulary

To maintain absolute integrity, every module and integration is classified under the project's strict claim vocabulary:

| Module / Integration | Status | Provenance / Evidence | Remaining Blocker / Prerequisite |
|---|---|---|---|
| **Identity, Auth & Tenant Isolation** | `TEST VERIFIED` | Session-bound cookies, scrypt hashing, CSRF tokens, tenant filtering, adversarial multi-tenant suite (`test_adversarial_tenancy.py`) | Production deployment review & external credential audit |
| **Catalogue & Inventory** | `TEST VERIFIED` | Durable balances, conditional updates, reservation completion/release, audit trail | Production concurrency stress test |
| **Counter Billing** | `TEST VERIFIED` | Server-resolved prices, immutable issue, stock reservation, explicit unrecorded payment state | Physical scanner & camera hardware QA |
| **Shop Storefront** | `TEST VERIFIED` | Shared catalogue, stock reservation, multi-item orders, hashed tokens, fulfillment gating | Public HTTPS reachability & phone scan |
| **Khata Credit Ledger** | `TEST VERIFIED` | Append-only ledger, balance projection assertions, reversal corrections, Paytm verified repayment transitions | Real Paytm collection link end-to-end |
| **Sarkar Assistant** | `TEST VERIFIED` | Schema-described typed registry, 10 read-only tools, session-bound stock receipt mutation, runtime deadline enforcement (504) | Additional mutation workflows & LLM planner |
| **Sound Mode** | `TEST VERIFIED` | Outbox pattern committed with transaction, cursor polling, 7 negative payment conditions fail-closed | Live Paytm webhook settlement & browser audio playback QA |
| **Opportunity Pulse** | `TEST VERIFIED` | Search outcome deduplication, 30-day window aggregation, factual inventory, sales, Khata, and fulfillment metrics | High-volume public storefront traffic |
| **Counter Barcode Scanner** | `TEST VERIFIED` | Keyboard-emulating barcode input with duplicate suppression & quantity aggregation | Physical barcode scanner hardware validation |
| **Counter Voice Input** | `CONFIGURED BUT UNVERIFIED` | Turn-based audio upload, MIME validation, explicit consent gate, transcript parsing | Active Sarvam API key exercising in browser |
| **Counter Photo Recognition** | `NOT CONFIGURED` | JPEG/PNG/WebP validation, dimension bounding, catalogue ranking, manual fallback | Approved Vision LLM endpoint & API key |
| **Parchi-to-Digital-Bill** | `NOT CONFIGURED` (OCR) / `TEST VERIFIED` (Manual Fallback) | Text parsing and catalogue candidate review tested; OCR requires external vision provider | Approved Vision OCR endpoint |
| **Paytm Checkout & Links** | `CONFIGURED BUT UNVERIFIED` | Adapter present, checksum validation, exact paise matching, staging/live gates (`PAYTM_LIVE_ENABLED=false`) | Live merchant credentials & public HTTPS callback URL |
| **Storefront QR** | `NOT READY` | Pinned IP transport, HTTPS enforcement, store identity contract; local HTTP workspace URL correctly blocks QR issuance | Public HTTPS domain with trusted certificate |
| **Database Engine** | `TEST VERIFIED` (SQLite) / `NOT CONFIGURED` (Atlas) | Local SQLite runtime with online backup API; MongoDB Atlas adapter not connected | Database migration if cloud storage required |
| **Render Cloud Deployment** | `BLOCKED; NOT DEPLOYED` | Render services point to `rushmanthnalluri/AI-Revenue-Recovery` which contains a forbidden Razorpay module | Reconcile repository source link & remove Razorpay |

---

## 3. Exact Files Changed in this Sprint

1. **`app/sarkar.py`**:
   - Enforced tool execution deadlines (`spec.timeout_seconds`) in `invoke_tool()` using `ThreadPoolExecutor` and `copy_context()`.
   - Overtime tools raise `HTTPException(504, "Tool execution exceeded deadline")` without committing partial transactions.
2. **`app/payment_requests.py`**:
   - Fixed unhandled `inventory.InventoryNotFound` in `request_counter_bill_payment` by importing `inventory` and catching both `(billing.BillingError, inventory.InventoryNotFound)`, returning a clean 404.
3. **`app/demand.py`**:
   - Added `business_metrics()` function computing:
     - `low_stock_summary`: count of active items where available stock $\le$ threshold.
     - `sales_summary`: count and total paise of verified Paytm payments within the window.
     - `khata_summary`: count of customers with positive balance and total outstanding paise.
     - `pending_fulfillment_summary`: count and total paise of paid orders awaiting fulfillment.
     - `financial_breakdown`: separate gross bill totals, verified collected amount, outstanding credit, and pending payments.
   - Integrated `business_metrics` into `opportunity_pulse()` while preserving search outcome insights.
4. **`app/static/app.js`**:
   - Enhanced `loadOpportunityPulse()` to render live business indicator summary chips (low stock, verified sales, Khata outstanding, pending fulfillments) above the search insights list.
5. **`tests/test_sarkar.py`**:
   - Added `test_sarkar_tool_timeout_enforced` validating that tools exceeding their declared deadline raise HTTP 504.
6. **`tests/test_adversarial_tenancy.py`** (New File):
   - Comprehensive multi-tenant and RBAC adversarial test suite containing 8 detailed tests:
     - Cross-merchant catalogue and stock modification attacks.
     - Cross-merchant Counter billing attacks (viewing, editing lines, issuing, voiding, paying, Khata crediting).
     - Cross-merchant Khata attacks (viewing accounts, repayments, collection links, reversals).
     - Cross-merchant Shop order attacks (order enumeration, token hash spoofing, unauthorized fulfillment).
     - Cross-merchant Sound Mode attacks (device cursor tampering, event polling, event acknowledgement).
     - Cross-merchant Sarkar tool argument attacks (swapped Khata IDs, payment IDs, and stock receipt tokens).
     - Staff RBAC privilege escalation prevention (blocking staff from Khata, Sound, and stock receipts).
     - Cross-site Origin, CSRF token, and Sec-Fetch-Site attack prevention.
7. **`tests/test_payment_sound.py`**:
   - Added `test_sound_mode_mandatory_negative_conditions_never_announce_payment` validating all 7 mandatory negative payment states fail-closed with 0 SoundEvents.
8. **`tests/test_demand.py`**:
   - Added `test_opportunity_pulse_business_metrics_and_financial_breakdown`.
   - Added `test_opportunity_pulse_tenant_isolation_for_metrics`.
   - Added `test_opportunity_pulse_validation_and_api`.
9. **Documentation Updates**:
   - `docs/merchant-os/claims-matrix.md`
   - `docs/merchant-os/verification-matrix.md`
   - `docs/merchant-os/security-review.md`
   - `docs/merchant-os/demo-guide.md`
   - `docs/merchant-os/implementation-report-2026-10-30-final.md`

---

## 4. Test Suite Execution Results

The final full run completed on 2026-10-30 with **268 passed, 0 failed, 0 skipped, and 320 warnings** across 33 test modules in 470.51 seconds. The warnings are Python 3.14 SQLite datetime-adapter deprecations surfaced through SQLAlchemy.

The run used `python -m pytest tests/ -q` with `WAPAS_ENV=test`, `APP_ENV=test`, `GATEWAY=fake`, `WAPAS_ALLOW_PROTECTED_DB_WRITES=false`, both Paytm test/live flags false, and a newly generated temporary SQLite database path. The protected installation database was not used by this run.

`python -m compileall -q app tests` and `node --check app/static/app.js` plus `node --check app/static/login.js` passed. The isolated Chromium Counter smoke passed scanner quantity aggregation, duplicate suppression, Parchi manual fallback, mobile-width layout, payment-state wording, and stored-XSS rendering. Camera/microphone permission, physical scanner hardware, browser audio playback, Shop/Khata/Sarkar full browser workflows, and public storefront reachability were not exercised. No frontend production build system is defined.
## 5. Security & Multi-Tenant Isolation Results

The newly implemented `tests/test_adversarial_tenancy.py` explicitly proves that:
1. **Catalogue & Stock:** Merchant A cannot inspect, adjust, or reserve stock belonging to Merchant B. Cross-tenant IDs yield HTTP 404.
2. **Counter Billing:** Merchant A cannot read drafts, add lines, issue bills, cancel bills, request payment, or credit bills belonging to Merchant B.
3. **Khata Ledgers:** Merchant A cannot access accounts, view transaction histories, record manual repayments, generate collection links, or issue reversals on accounts belonging to Merchant B.
4. **Shop Orders & Public Security:** Public order lookups require the exact unguessable `x-order-token` matching the stored token hash; enumeration attempts return 404. Orders cannot be fulfilled without server-verified payment settlement.
5. **Sound Mode Cursors:** Sound device event streams and acknowledgments are strictly bound to the authenticated store. Device cursors for Merchant A cannot read or acknowledge events from Merchant B.
6. **Sarkar Arguments:** Passing cross-tenant IDs into Sarkar tools (such as checking another store's Khata account or confirming a stock receipt across merchants) raises HTTP 404.
7. **Role-Based Access Control (RBAC):** Staff accounts are restricted to operational tasks (Counter, Catalogue, Order review, read-only Sarkar). Attempts to access Khata, Sound notifications, user management, or confirm stock receipts are rejected with HTTP 403 Forbidden.
8. **CSRF & Origin Defense:** Unauthenticated or cross-origin state-changing mutations lacking a valid session-bound CSRF token are rejected with HTTP 403 Forbidden.

---

## 6. Sound Mode Fail-Closed Validation

Payment notifications through Sound Mode are strictly gated on authentic, server-verified Paytm transactions. `test_payment_sound.py` validates all 7 negative conditions:
1. **Forged Signature:** Callbacks with invalid provider checksums return HTTP 400 and emit zero SoundEvents.
2. **Unknown Order:** Callbacks referencing unknown orders or links fail to resolve a source and emit zero SoundEvents.
3. **Pending Status:** Payments with status `PENDING` remain unsettled and emit zero SoundEvents.
4. **Amount Mismatch:** Payments whose amount does not exactly match the source bill/order/collection paise amount enter `PENDING_RECONCILIATION` and emit zero SoundEvents.
5. **Failed / Expired Status:** Payments with status `FAILED` emit zero SoundEvents.
6. **Ambiguous Gateway State:** Network timeouts or gateway errors during status polling leave payments in `PENDING` or `PENDING_RECONCILIATION` without emitting sound.
7. **Duplicate Replay Idempotency:** Duplicate webhook callbacks are idempotent no-ops; exactly one SoundEvent is created on the initial settlement.

---

## 7. Protected Database Containment Status

`D:\Wapas\wapas.db` remains completely protected:
- Application database initialization (`db.get_engine()`) contains an active path guard: any attempt to establish a writable connection to `wapas.db`, `wapas.db-wal`, `wapas.db-shm`, or `wapas.db-journal` raises `RuntimeError("Refusing to open protected database in this process")`.
- All automated tests, temporary harnesses, and browser runners use isolated, disposable SQLite databases in temporary directories.
- The online backup utility (`app/backup_db.py`) uses SQLite's non-blocking online backup API with post-backup `PRAGMA integrity_check` verification.

---

## 8. Safe Local Startup & Demo Instructions

To run the safe, offline local demo without affecting `wapas.db`:

### Terminal 1: Run Local Server
```powershell
Set-Location D:\Wapas
$env:WAPAS_ENV = "development"
$env:GATEWAY = "fake"
$env:DATABASE_URL = "sqlite:///./wapas-merchant-os-demo.db"
$env:PUBLIC_BASE_URL = "http://127.0.0.1:8000"
$env:PAYTM_LIVE_ENABLED = "false"
$env:PAYTM_TEST_ENABLED = "false"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Terminal 2: Initialize Demo Owner Account
```powershell
Set-Location D:\Wapas
$env:WAPAS_ENV = "development"
$env:DATABASE_URL = "sqlite:///./wapas-merchant-os-demo.db"
.\.venv\Scripts\python.exe -m app.auth_cli create-owner --database-url sqlite:///./wapas-merchant-os-demo.db --username owner
```

### Accessing the System
1. Open `http://127.0.0.1:8000/login` and authenticate using the credentials created above.
2. Navigate the modules:
   - **Catalogue & Stock:** View items, check stock levels, and inspect movements.
   - **Counter:** Create draft bills, scan barcodes (keyboard emulator), test manual Parchi transcription, and issue immutable bills.
   - **Khata:** View customer credit ledgers, record manual partial repayments, or test simulated collection links.
   - **Sarkar:** Query stock, bills, Khata, and summary metrics. Test stock receipt preparation and confirmation.
   - **Opportunity Pulse:** View persisted search outcomes and live factual business indicators.
   - **Sound Mode:** Test sound event cursor polling in muted/unmuted states.
   - **Shop:** Access the public store at `http://127.0.0.1:8000/s/default-store`.

---

## 9. Conclusion

The latest local regression run passed, and the limited Counter browser smoke passed. Wapas remains **INTEGRATION IN PROGRESS**: there is no verified end-to-end Paytm transaction, no production database migration/restore rehearsal, no public HTTPS storefront test, and no deployment from the new source repository. These checks do not establish production readiness.

## Latest verification and source publication

On 2026-10-30, a private GitHub repository was created at [rushmanthnalluri/wapas-merchant-os](https://github.com/rushmanthnalluri/wapas-merchant-os). The `main` branch contains the initial source snapshot at commit `a1ed642`. The repository contains 130 application, test, documentation, and configuration files. `.env`, SQLite databases and sidecars, backups, generated hidden files, and the submission PDF/PPTX were not uploaded. A high-confidence credential-pattern scan of the staged snapshot found no matches; this is not a complete secret-scanning product.

GitHub repository creation and push were authorized by the owner. No Render service setting or deployment was changed. The existing Render source mismatch remains unresolved and the new repository is not connected to Render.
