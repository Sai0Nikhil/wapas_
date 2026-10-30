# Wapas Merchant OS — implementation report

> Historical report for the 2026-10-29 sprint. Superseded by the [2026-10-30 implementation report](implementation-report-2026-10-30.md), which contains the latest test results and incident containment status.

Date: 2026-10-29  
Release status: **INTEGRATION IN PROGRESS**

This is a continuation sprint against the existing Wapas domain models and services. The pre-implementation `current-state-audit.md` is historical; it predates the shared payment pipeline, authenticated merchant sessions, Sound Mode, and initial Sarkar router now present in this workspace.

## 1. Baseline and repository evidence

- The verified starting point already had a shared `Payment` model/lifecycle, Counter bills, Shop orders, Khata ledger, per-device SoundEvent cursors, authenticated merchant sessions, and a limited deterministic Sarkar router. The increment extends those paths rather than creating parallel models.
- The baseline backend suite, run before this sprint against an isolated SQLite file, was **159 passed, 215 warnings** in 130.23 seconds.
- `D:\Wapas` has no `.git` directory. Local branch, commit history, and working-tree status are not available to inspect.
- Tests and the browser smoke use disposable SQLite files. The protected database incident during harness setup is disclosed in section 9; it must not be described as unchanged.

## 2. Counter input methods

Added review-only input paths that converge on the existing Counter draft and issue services:

- Scanner-keyboard barcode/SKU entry suppresses rapid duplicate events, serializes lookups, aggregates later scans into the current line, and falls back to filtered catalogue search. Camera scanning is exposed only when the browser has `BarcodeDetector`, `getUserMedia`, and a secure context.
- Photo recognition accepts bounded, decoded JPEG/PNG/WebP images and uses a separate vision-provider configuration. In this installation vision is **NOT CONFIGURED**; the UI returns a manual catalogue-search fallback.
- Voice billing uses turn-based Sarvam STT, explicit external-processing consent, transcript review, quantity parsing, and saved-catalogue candidates. Sarvam credentials are present in local settings, but no Counter transcription request was made; provider behavior is **CONFIGURED BUT UNVERIFIED**.
- Parchi upload uses the vision path when configured; typed transcription is available without a provider. Both return candidate matches that require review.
- Uploads are suggestions only: the server resolves product IDs, prices, and availability from the signed-in merchant catalogue. The user reviews the candidate and quantity, then the existing `PUT /lines/{product_id}` and bill issue service handle all draft and inventory mutations.

No modality can set prices, stock, Khata credit, or payment status. Issued bills remain immutable and payment remains `NOT_RECORDED` until the existing shared payment lifecycle verifies settlement.

## 3. Sarkar registry

Added a typed registry that migrates existing Sarkar readers and stock receipt operations into declared input/output schemas with role and permission metadata, tenant ownership, read/mutation classification, approval and idempotency metadata, timeout/retry values, correlation IDs, and post-execution verification descriptions. Current tools declare a three-second timeout and zero automatic retries, but synchronous invocation does not enforce a runtime deadline. Read-only trace/correlation results are returned but not persisted; the durable action and approval evidence are limited to the existing stock receipt.

Read tools cover saved stock, Khata and ledger history, orders, recent bills and payment states, low-stock items, verified-payment summaries, persisted pending-payment evidence, business summary, and Opportunity Pulse events. Responses describe saved records and narrow search evidence; they do not infer sales from searches.

Stock receipt preparation and confirmation remain the only Sarkar mutation. The existing one-time token stays bound to the owner session, exact payload, expiry, and current stock state. There is no generic SQL/write tool, shared multi-module approval queue, Counter/Khata/order mutation tool, general LLM planner, or TTS.

## 4. Payment-to-Sound and Khata verification

The shared source-bound Payment lifecycle remains the only payment path for Counter, Shop, and Khata. Tests cover exact Paytm MID/order-or-link/currency/amount/transaction checks; committed source updates; duplicate callback/reconciliation idempotency; Shop fulfillment after verified payment only; Counter payment versus Khata credit; exactly-once Khata repayment; and silent pending, failed, mismatched, unknown, simulated, or missing-source results.

Verified Paytm SoundEvents are written in the same transaction as settlement and carry a source and amount. Device polling and acknowledgement are scoped to the signed-in merchant/store and device cursor. The Sound Mode UI shows amount, source, timestamp, delivery, acknowledgement, and playback state; it starts muted and exposes explicit enable/mute controls. The UI does not equate a committed or delivered event with audio playback.

The fake gateway remains **SIMULATED**. No actual Paytm checkout, Payment Link, callback, test payment, or live payment was initiated or reconciled. Current local settings show `gateway=paytm`, complete credential fields, `PAYTM_LIVE_ENABLED=false`; therefore Paytm is **CONFIGURED BUT UNVERIFIED**, not `PAYTM TEST VERIFIED` or `LIVE VERIFIED` for payment. A historical narrow status-authentication check in `current-state-audit.md` does not prove checkout or settlement.

## 5. Storefront QR protections

QR verification now requires HTTPS and rejects userinfo, query/fragment, nonstandard ports, localhost, private/reserved/link-local IPs, and non-global DNS answers. It disables redirects and environment proxy use, validates the expected product response shape and exact store slug, and serves a QR only after successful verification.

The configured public URL is local HTTP, so the storefront QR remains **NOT READY**. DNS is checked before the request but is not pinned to the checked address; DNS rebinding remains a residual SSRF risk. No public scan or external scan was performed.

## 6. Browser and deployment validation

`scripts/counter_browser_smoke.py` starts FastAPI against a fresh temporary SQLite database and uses headless Chromium. It passed Counter navigation, scanner-keyboard quantity addition and rapid-duplicate suppression, Parchi `NOT CONFIGURED` fallback without draft mutation, manual catalogue review/addition, mobile one-column layout and horizontal-overflow check at 390 px, and bill issue with `NOT_RECORDED` payment state.

Camera, microphone, physical scanner hardware, browser audio playback, public storefront reachability, and Shop/Khata/Sarkar/Sound end-to-end UI flows were not exercised. No frontend package manifest or production build system exists. The connected Render services still point to `rushmanthnalluri/AI-Revenue-Recovery`, a different repository containing a forbidden Razorpay module. No deployment, repository switch, or external service mutation was performed. MongoDB Atlas is not connected to the local runtime.

## 7. Test and code-check results

- Final full backend suite: **186 passed, 264 warnings** in 143.51 seconds. Warnings were Python `sqlite3` datetime-adapter deprecations surfaced through SQLAlchemy; no skips or failures were reported.
- Focused authenticated cross-store SoundEvent cursor/acknowledgement test: **1 passed, 2 warnings**.
- Browser Counter smoke: **passed** in headless Chromium using a temporary database; device and provider limitations are listed above.
- `python -m compileall -q app tests scripts`: **passed**.
- `node --check app/static/app.js`: **passed**.
- Migration/backup tests ran against fixture-created temporary databases. No Paytm transaction, customer message, production deployment, Atlas write, or public QR scan was performed.

## 8. Remaining release gaps

- Complete an authorized Paytm test transaction end to end, including source reconciliation and browser polling, before claiming `PAYTM TEST VERIFIED`; keep production movement disabled until separately authorized.
- Configure and authorize the vision provider before photo/Parchi OCR can be demonstrated. Make a provider-backed Sarvam Counter transcription test only with explicit consent and safe sample audio.
- Verify supported camera, microphone, audio autoplay/mute, and physical scanner behavior on target browsers/devices.
- Close the DNS rebinding gap by pinning or controlling outbound resolution before public QR verification is treated as complete.
- Add shared approval-backed Sarkar mutations only after durable exact-parameter proposals, stale-source checks, replay/expiry checks, and post-execution record verification are implemented and tested.
- Enforce the declared Sarkar execution deadline and persist safe read-tool traces/correlation records before widening the tool surface.
- Reconcile the Render repository/source mismatch and deployment architecture before any deployment. The connected repository contains a forbidden Razorpay module and must not be deployed as Wapas Merchant OS.
- MongoDB Atlas remains **NOT CONFIGURED** for this runtime; SQLite remains the local system of record.

## 9. Protected database setup incident

During an earlier attempt to run the browser smoke, the child server was configured with a temporary database, but its parent process imported app settings before inheriting that temporary `DATABASE_URL`. The parent then called `db.init_db()` against the protected `D:\Wapas\wapas.db` and created a test owner/session.

Read-only inspection confirmed these effects:

- The newer `Payment` columns `store_id`, `currency`, `source_type`, `source_id`, `provider`, `provider_mid`, `provider_order_id`, `provider_link_id`, `provider_link_url`, `provider_transaction_id`, `idempotency_key`, and `verified_at` are present.
- The database currently contains 630 Payment rows. All 630 now read `store_id=store_default`, `provider=fake`, `source_type=RECOVERY`, and `currency=INR`; there are no null or other-store `store_id` values. `store_id` was explicitly backfilled by the initializer, and the other values are defaults on columns that were absent before the call. The former provider/currency values are unknown; do not treat `provider=fake` on these legacy rows as proof they were simulated payments.
- One `authuser` named `counter-browser-smoke`, one `OWNER` membership for `merchant_default` / `store_default`, and one session are present. A read-only check at 2026-10-29 18:08 UTC found the session unrevoked, expiring at 2026-10-30 05:49:24 UTC. At the time of the incident the harness used a fixed disposable password; the corrected harness now generates a random password for each temporary run. No user, membership, or session was deleted or revoked in the protected database.
- The WAL was modified. The existing `schema_migrations` row is version 1 with timestamp `2026-10-29T15:24:17.245142+00:00`; read-only inspection did not find a new migration version from this incident.
- The call also ran the normal table metadata and bill-trigger initialization; without a before-image, any trigger/index differences cannot be attributed precisely.
- The initializer's explicit data update assigned the new `store_id` across all 630 Payment rows. It did not explicitly update legacy amount/status/order fields, but there is no before-image to prove all historical values are unchanged. The provider/currency defaults create an unresolved historical-data integrity risk.

No rollback or cleanup was attempted because that would write to the protected database again. The harness now sets its temporary database path before app imports, asserts that the configured path is inside the temporary directory, and avoids a second `db.init_db()` call. All subsequent browser and test runs used disposable databases. The protected file must be treated as modified; the operator can decide whether any recovery action is appropriate.

## 10. Release status

**INTEGRATION IN PROGRESS.** Local tests and the bounded Counter browser flow pass. Live Paytm settlement, provider-backed photo/voice recognition, broader Sarkar mutation approvals, public QR readiness, full browser/device compatibility, and deployment are not verified.
