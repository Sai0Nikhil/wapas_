# Wapas Merchant OS — implementation report

> Interim report. Superseded by [the final 2026-10-30 report](implementation-report-2026-10-30-final.md), which includes the latest 268-test rerun and GitHub publication evidence.

Date: 2026-10-30 (Asia/Kolkata)  
Release state: **INTEGRATION IN PROGRESS — NOT PRODUCTION READY**

## Blocker-busting follow-up (2026-10-30)

- Paytm status responses now require a valid provider checksum before status mapping. A successful status also requires an exact positive INR paise amount and a non-empty transaction ID; malformed response shapes remain unresolved.
- Paytm endpoint validation now uses exact official HTTPS hosts. Staging payment actions require `PAYTM_TEST_ENABLED=true` in `development` or `test`, and are blocked in production. Production-host actions require `WAPAS_ENV=production` and `PAYTM_LIVE_ENABLED=true`; both flags default off. The local `.env` was not edited.
- The protected-database guard now also rejects the protected `-wal`, `-shm`, and `-journal` files and recognized SQLite `file:` URI aliases. These regression tests compare configured paths without opening the protected installation.
- Counter candidate confidence rejects NaN/infinite model values as unknown. Paytm response handlers fail closed on malformed response shapes.
- A read-only Paytm query for a fresh random reference returned `NOT_FOUND`; the response checksum validated. No checkout, Payment Link, or payment transaction was created.

## What changed

- Added a protected-database write guard. Normal ORM startup, tests, and doctor diagnostics refuse writes or use read-only access to `D:\Wapas\wapas.db`; only an explicit maintenance override can bypass the guard. Production fake-gateway configuration now fails closed before database initialization, and an unknown gateway name no longer falls back to fake.
- Changed the doctor database check to read SQLite in read-only mode and removed schema initialization from the doctor command.
- Made storefront QR verification pin its validated public DNS answers to the HTTPS connection, retain TLS hostname checking, avoid proxies and redirects, cap the JSON response, and verify the expected store slug and public product contract. DNS failure, non-public targets, timeouts, connection refusal, redirects, and invalid responses leave the QR unavailable.
- Persisted compact tenant-scoped Sarkar execution audit traces for successful tool calls. Traces contain tool/version, correlation ID, validated-input digest and field names, response field/count summary, and provenance; raw customer/payment output and confirmation tokens are not copied. The stock receipt proposal/confirmation remains the only mutation. The declared three-second timeout remains metadata and is not yet an enforced deadline.
- Corrected the disposable browser harness to force the protected-database override off in both parent and child processes before importing application settings.
- Updated release evidence, API contracts, security review, architecture, demo instructions, claims, and implementation status. No feature was rebuilt or duplicated.

## Database incident containment

The 2026-10-29 setup incident and its effects are documented in [incident-containment-2026-10-30.md](incident-containment-2026-10-30.md). This sprint did not initialize, migrate, seed, or test against the protected database. A new read-only post-check found:

- Source and backup both pass SQLite `PRAGMA integrity_check` (`ok`) and have matching counts: 630 payments, one user, one membership, and one session.
- The current payment-row-value SHA-256 digest matches the verified online backup.
- The harness account and membership remain inactive, and its only session remains revoked.
- The original provider and currency for the 630 historical Payment rows remain unknown. Their current defaults are not evidence of past payment state.

The backup has not been restored or used for a migration rehearsal. The database is contained against routine ORM access, but it remains modified and historical payment metadata remains uncertain.

## Verification results

- Full backend suite: **233 passed, 274 warnings, 0 failures, 0 skips** in 155.41 seconds. Warnings are Python 3.14 SQLite datetime-adapter deprecations surfaced by SQLAlchemy.
- Focused blocker suite: **70 passed, 16 warnings** in 23.76 seconds across Paytm adapter/link retry, database safety, Counter input, and gateway-mode tests. It includes signed/malformed status, exact amount and transaction ID, staging/live gates, protected SQLite sidecars/URI aliases, and non-finite confidence coverage.
- Focused Sarkar and storefront security suite: **25 passed, 48 warnings** in 18.41 seconds. It includes persisted Sarkar trace checks and QR behavior for unsafe URL forms, private DNS, redirects, wrong identity, invalid products, DNS failures, timeouts, and refused connections.
- Python compilation: `python -m compileall -q app tests scripts` passed.
- JavaScript syntax: `node --check app/static/app.js` passed.
- Isolated headless Chromium Counter smoke passed against a disposable SQLite database. It covered console startup, keyboard-emulating barcode input, quantity aggregation, duplicate suppression, Parchi `NOT CONFIGURED` fallback, manual catalogue review, 390 px one-column layout and overflow, bill issuance, and `NOT_RECORDED` payment state. Physical scanner, camera, microphone, and audio playback were not exercised.
- A high-confidence credential-pattern scan found no matches in 133 eligible project files, including source, tests, documentation, and configuration templates. `.env`, database files, backups, attachments, and generated caches were excluded. This is not a full secret scan. There is no `.git` metadata in this workspace, so there is no branch, staged diff, or commit to inspect.
- No separate frontend build system or production build is present.

## Service and provider evidence

| Service | Verified state |
|---|---|
| Paytm | **CONFIGURED BUT UNVERIFIED.** A non-destructive status query using a fresh random reference returned `NOT_FOUND`; the provider response checksum validated. This does not verify checkout, Payment Link capability, callbacks, or settlement. Official pages document multiple host variants; the configured `.com` host is shown for JS Checkout status, while another V3 page documents an `.in` variant. The merchant's enabled product and API variant remain unconfirmed. `PAYTM_TEST_ENABLED=false` and `PAYTM_LIVE_ENABLED=false`; no link, checkout, or transaction was initiated. |
| Telegram | **LIVE VERIFIED** only for the read-only bot identity check; no message was sent. |
| Sarvam STT | **CONFIGURED BUT UNVERIFIED** for Wapas Counter transcription; no provider request or microphone recording was made. |
| LLM provider | **CONFIGURED BUT UNVERIFIED** for this sprint; no model request was made. |
| Vision/OCR | **NOT CONFIGURED.** Manual review/transcription fallback remains available. |
| MongoDB Atlas | **NOT CONFIGURED** for the application runtime; the connected Atlas tool did not grant AI-client access, and no database was created or changed. |
| Render | **DEGRADED / SOURCE MISMATCH.** Previous read-only inspection found the connected API and web services source `rushmanthnalluri/AI-Revenue-Recovery` on `main`, not Wapas. That repository contains a forbidden Razorpay module. This pass could not refresh the service list because the connector required a workspace selection. No workspace was selected and no service settings or deployment were changed. |
| Fake gateway | **SIMULATED.** Production mode rejects fake gateway configuration. |

The effective local configuration is `WAPAS_ENV=production`, `GATEWAY=paytm`, `PAYTM_TEST_ENABLED=false`, `PAYTM_LIVE_ENABLED=false`, protected database target selected, and protected-database override disabled. The configured storefront base URL uses HTTP, vision is disabled, and Sarvam is configured. Secret values were not printed or copied.

An existing Python/Uvicorn process (PID 20784) still listens on port 8000. Its `/login` path returned 404, so it could not be verified as this Wapas build; it was left running. A local scan found no Razorpay references in Wapas application code, dependencies, or environment template. No Wapas `render.yaml`, Dockerfile, Procfile, or deployment workflow was found in the workspace. The workspace also has no `.git` directory, so branch and commit state cannot be established here.

Primary Paytm references reviewed: [Initiate Transaction API](https://www.paytmpayments.com/docs/api/initiate-transaction-api/), [Transaction Status API v3](https://www.paytmpayments.com/docs/api/v3/transaction-status-api/), [JS Checkout payment-status verification](https://www.paytmpayments.com/docs/jscheckout-verify-payment/), [Create Link API](https://www.paytmpayments.com/docs/api/create-link-api/), and [Callback and Webhook URL requirements](https://www.paytmpayments.com/docs/callback-and-webhook/). The merchant-specific Paytm product and API variant still require confirmation before an authorized test transaction.

## Release blockers and remaining work

- Resolve the Render repository/service mismatch and approve a precise deployment target before changing the production source or deploying. Do not deploy the repository containing Razorpay.
- Confirm the merchant's supported Paytm product, API host/version, test credentials, and HTTPS callback capability. Then obtain explicit authorization for an isolated end-to-end test transaction and reconcile its persisted source, Payment, idempotency, and SoundEvent evidence. Keep production money movement disabled.
- Provision the intended production database and storage/backups, rehearse schema changes on a verified copy, and document recovery before migration. Do not use the protected workspace database for this rehearsal.
- Enforce Sarkar runtime deadlines safely before adding slow or external tools. Additional mutations need durable exact-parameter approvals and stale-state/replay tests.
- Configure the separately approved vision provider if OCR/photo recognition is required. Verify provider-backed transcription only with consent and authorized test media.
- Set a public HTTPS storefront URL and verify it from the actual deployment environment; then perform an authorized phone QR scan.
- Complete browser/device validation for Shop, Khata, Sarkar, Sound Mode, camera, microphone, browser audio, and physical scanner hardware. No hosted worker health, public endpoint, production monitoring, or deployment was tested.
- Add operational controls for session recovery, provider health, log review, backup restore, and deployment rollback before release.

**Conclusion:** local regression and the limited Counter browser smoke pass. Wapas is not production ready. No production deployment, source-link change, real/test payment transaction, Payment Link creation, customer message, external account write, or public storefront exposure occurred.
