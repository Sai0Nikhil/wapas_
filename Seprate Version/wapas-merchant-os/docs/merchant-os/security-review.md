# Merchant OS — security review

Review date: 2026-10-30. This is an implementation review, not a production security certification.

## Implemented safeguards

- Private console access requires a revocable browser session resolved to a server-side merchant/store membership. Passwords are scrypt-hashed; raw session and CSRF tokens are not stored.
- State-changing console requests require same-origin checks and a session-bound CSRF token. Public console access does not use the legacy `ADMIN_TOKEN` mechanism. Response headers include CSP, frame denial, content-type protection, and browser feature policy.
- Staff access is limited to Counter, catalogue, orders, and read-only Sarkar requests. Khata, sound notifications, account operations, and stock-receipt confirmation are owner-only.
- ORM filters and service/API predicates scope tenant-bearing records by the active merchant. Public storefront reads resolve store slug and return only public product/order fields. Customer order status uses a random token whose hash is stored.
- Database-backed idempotency and checkout rate limits replace process-local counters for the covered operations. Inventory updates use conditional writes and reservation records to protect available stock.
- Counter bills are server-priced and immutable after issue. Issue reserves physical stock; verified Paytm settlement or accepted Khata credit consumes the reservation; an eligible unpaid void releases it.
- Paytm status responses require a valid provider checksum before any result is interpreted. A success also requires configured MID, source-bound order/link, exact positive INR paise amount, and a non-empty transaction ID. Malformed, unsigned, mismatched, and ambiguous results remain unresolved.
- Paytm endpoints are restricted to exact official HTTPS hosts. Test checkout/link creation requires explicit `PAYTM_TEST_ENABLED=true` in `WAPAS_ENV=development` or `test`; production mode rejects staging actions. A production host requires `WAPAS_ENV=production` and explicit `PAYTM_LIVE_ENABLED=true`. Both flags default off.
- The SQLite ORM guard rejects the protected installation database, its `-wal`, `-shm`, and `-journal` files, and recognized `file:` URI/path aliases. It also checks same-file aliases when the target exists. This pass ran regression checks against path strings only and did not open the protected database.
- Fake gateway successes are labelled `SIMULATED`. Counter fake settlement does not consume reserved inventory. Khata fake collection does not write a ledger repayment. Fake or mismatched status does not create a Paytm SoundEvent.
- Verified Paytm SoundEvents are written in the same database transaction as business settlement, with an idempotency key and per-device cursor.
- Khata is append-only. Repayments require explicit receipt confirmation or verified Paytm collection; corrections create reversal entries.
- Sarkar stock receipt previews are tied to owner ID, session hash, exact payload hash, expiry, and a one-time confirmation token. Inventory mutation and audit event are committed together. The model cannot run SQL or call a gateway.
- Sarkar operations use a declared typed registry with input/output schemas, role and permission metadata, tenant ownership, mutation classification, approval and idempotency flags, timeout/retry metadata, correlation IDs, and post-execution readback. Read-only tool calls append a compact audit trace containing the tool/version, input digest, output field/count summary, and provenance; customer and payment payloads are not copied into the trace. The existing stock-receipt action is still the only mutation; its token additionally binds current stock state and expiry. Synchronous handler execution enforces the declared runtime deadline (`timeout_seconds`) via ThreadPoolExecutor, terminating overtime tools with HTTP 504 Gateway Timeout without committing partial transactions.
- Counter photo/Parchi uploads are limited to JPEG/PNG/WebP, decoded and re-encoded with metadata removed, capped at 8 MB and 24 megapixels, and reduced to bounded dimensions. Audio upload is capped at 12 MB with an allow-listed MIME type. Recognition/transcription is review-only and cannot add a draft line; only the canonical Counter service sets product, price, and stock.
- Counter image/audio data is sent to a provider only when the corresponding provider is configured and the user explicitly consents. Candidate matching uses only the active authenticated merchant catalogue. Non-finite confidence values are converted to unknown rather than leaking invalid JSON values. Missing providers return `NOT CONFIGURED`; provider failures return a manual fallback without changing the draft.
- Sound Mode starts muted and displays committed amount/source/time separately from browser delivery, acknowledgement, and playback confirmation. Browser playback can be blocked; the UI does not treat a committed event as proof that sound played. All 7 mandatory negative payment conditions fail-closed and produce zero sound events.
- Storefront QR verification requires HTTPS, rejects localhost/private/link-local/reserved IPs and non-global DNS answers, pins the checked DNS addresses for the HTTPS connection, disables redirects and environment proxy use, validates bounded JSON response shape and exact store slug, and keeps QR unavailable until verified. The configured URL in this workspace is local HTTP, so the QR remains not ready.
- Opportunity Pulse stores normalized query/outcome and a bucketed one-way hash without shopper PII, and derives factual business indicators (low-stock counts, verified sales, Khata outstanding, pending fulfillments, and financial breakdown) strictly from persisted database records.
- SQLite snapshots use the online backup API rather than copying an active `.db` file without its WAL.

## Remaining risks and controls needed

| Risk | Current evidence | Required before broader release |
|---|---|---|
| Provider configuration and external callbacks | No Paytm link, checkout, or callback ran in this cycle | Verify exact merchant capability and public HTTPS callbacks in an isolated Paytm test environment |
| Database backend and deployment | SQLite is the runtime; Render source points to another repository | Reconcile repository, environment, storage, worker ownership, and backup/restore before deployment |
| Concurrency and long-running workers | SQLite WAL and conditional inventory writes are tested locally | Stress concurrent final-unit orders, Counter receipts, and Khata repayments on the chosen production database |
| Session/account lifecycle | Login, revocation, role, CSRF, and route tests cover current flows | Add account recovery, password rotation, operator provisioning/audit runbook, and deployment TLS review |
| Public URL and outbound fetch abuse | Local/private/non-global targets, unsafe URL forms, DNS failures, redirects, malformed responses, timeouts, and refused connections are rejected by tests; transport dials the prevalidated public IP while retaining TLS hostname validation and does not follow redirects | Verify the intended public HTTPS storefront and deployment egress policy; the current local HTTP URL is not ready for QR use |
| Public abuse | Durable checkout/search rate limits and input bounds exist | Validate proxy/client IP handling, bot controls, limits, and monitoring under intended public traffic |
| Demand evidence | Search query text is normalized and source-limited, but customer search terms are still user-entered | Add retention policy and review privacy/abuse controls before broad public use |
| New Merchant OS notifications | Sound is in-app only; external delivery is not wired | Add a shared notification worker only when channel behavior, retries, and consent are defined |
| Sarkar breadth | Deterministic registry has ten read-only tools and a prepared/confirmed stock receipt; compact read-tool traces are persisted without raw customer/payment output; declared runtime timeout metadata is enforced via ThreadPoolExecutor with HTTP 504 on deadline | Add further mutations only with durable exact-parameter approval, revalidation, replay/stale-state tests, and post-execution verification |
| Photo/audio input | Validation and review-only fallback tests pass; vision is `NOT CONFIGURED`; Sarvam is configured but Counter STT was not provider-tested | Verify OCR/STT accuracy and retention with an authorized test provider, then assess consent wording and transcript/image retention before production enablement |
| Sound browser behavior | UI and polling state are implemented; Counter E2E passed in local Chromium, but audio was not played | Exercise browser autoplay/mute/blocked states and device cursor behavior in supported browsers before claiming playback compatibility |
| Protected local database | A browser harness setup incident added 12 `Payment` columns, assigned `store_default` to the 630 existing rows, and inserted a smoke-test owner and session. A verified online backup was created before revoking that session and deactivating only the smoke-test user/membership; the Payment table digest remained unchanged. The new engine guard blocks routine ORM access to this database | Historical provider/currency values are unknown and must not be inferred from migration defaults. The database remains modified; no pre-incident snapshot or restore rehearsal exists. Keep the verified backup and do not reset, migrate, or relabel these financial records |
| SQLite immutable triggers | SQLite protections are tested; database owners can still bypass application controls | Restrict filesystem/DB access, monitor migrations, and use an append-only external audit export if threat model requires it |

## Payment and approval boundaries

- A successful redirect or callback does not settle a payment. Server status must identify the configured merchant and the exact source.
- A duplicate success for the same payment is idempotent. A second payment that cannot settle its source goes to reconciliation and cannot emit a second source success event.
- Counter/Shop/Khata states are separate. A Shop payment cannot create a Khata repayment; a Counter payment cannot settle a different bill.
- Manual Khata receipt is explicitly owner-attested, not Paytm verified.
- Fake mode is an isolated simulator and cannot produce a Paytm SoundEvent.
- Refunds and automatic external customer messaging are not provided by the Merchant OS slice.

One read-only status query for a fresh random Paytm reference returned `NOT_FOUND` with a validated provider response checksum. No checkout, Payment Link, real/test transaction, external customer message, protected-database initialization, Render setting change, or deployment was performed during this review. The owner-authorized private GitHub repository creation is documented below. The local SQLite setup incident above is disclosed separately from external integration status.

## Source publication boundary

The owner-authorized source snapshot was pushed to private GitHub repository `rushmanthnalluri/wapas-merchant-os` (commit `a1ed642`). `.env`, the protected installation database and SQLite sidecars, backups, generated hidden files, and submission exports were not tracked. The staged tree passed a high-confidence credential-pattern scan; that scan does not replace a full secret audit. No Render configuration, production environment, payment capability, or DNS setting was changed.
