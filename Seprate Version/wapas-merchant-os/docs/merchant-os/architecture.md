# Wapas Merchant OS — implemented architecture

Updated: 2026-10-30. This document describes the code in this workspace, not a target design. The release state is **INTEGRATION IN PROGRESS**.

## Runtime shape

Wapas is one FastAPI application with SQLModel domain services, a static HTML/CSS/JavaScript console, and a SQLite database. Existing revenue recovery remains in the same application. The Merchant OS features share the catalogue, inventory, billing, payment, customer, audit, and merchant/store records. MongoDB Atlas and the connected Render project are not part of this runtime.

Private console requests resolve a browser session to an active membership, role, merchant, and store. API handlers use that request context for their queries and writes. Public storefront routes resolve a store by its slug and expose only storefront data. Existing recovery checkout/provider routes continue to use the installation's default merchant/store.

```text
Owner/staff browser ── session + CSRF ──> FastAPI routes
                                            │
Public customer browser ── store slug ──────┤
                                            v
                catalogue ─ inventory ─ Counter bills
                       │             │          │
                       ├── Shop orders          ├── Khata ledger
                       │                         │
                       └────── payment lifecycle ┘
                                 │
                   provider status verification
                                 │
                     transactional audit/outbox
                                 │
                         Sound Mode polling

Sarkar ── deterministic typed router ── saved domain records
```

## Implemented boundaries

| Area | Owns and changes | Important current limitation |
|---|---|---|
| Identity | Users, memberships, roles, password hashes, revocable sessions and CSRF state | No account recovery or production operator lifecycle |
| Catalogue and stock | Products, SKU/barcode lookup, stock balance, append-only movements and reservations | Scanner hardware and camera permission/device behavior are untested |
| Counter | Drafts, server-priced lines, issued bill snapshots, payment links and eligible voids. Typed search, keyboard scanner, optional camera scanner, photo suggestions, Sarvam voice suggestions, and Parchi image/manual transcription all return review candidates that use the canonical draft line service | Vision recognition is separately configured and currently not configured; STT is not provider-verified for Counter |
| Shop | Public store profile/catalogue/search, token-protected customer order status, orders and fulfillment | Public reachability and a live checkout are unverified |
| Payment | Shared Payment record with `RECOVERY`, `SHOP_ORDER`, `COUNTER_BILL`, and `KHATA_COLLECTION` source types | Paytm capability and live/test transaction path are not verified |
| Khata | Append-only credits, repayments and reversals; a cached balance projection is guarded transactionally | Repayment links are wired but have no merchant-specific Paytm evidence |
| Sound Mode | Verified Paytm settlement outbox, per-device cursor and acknowledgement; UI shows amount, source, timestamp, delivery, acknowledgement, and playback state with explicit mute/enable controls | In-app polling only; browser audio may be blocked and no physical/browser audio QA or external notifications were performed |
| Opportunity Pulse | Normalized public-store search events for no-match and out-of-stock outcomes | Search interest is not a sale, revenue estimate, or broad demand signal |
| Sarkar | Deterministic typed registry for tenant-scoped stock, Khata, orders, bills/payment states, low stock, verified payment summaries, pending evidence, business summary, and Opportunity Pulse; prepared stock receipt remains session-bound and one-time; successful calls persist compact redacted audit traces | No general LLM planner or shared approval service; stock receipt is the only mutation; runtime deadline enforcement returns HTTP 504 on timeout and is locally tested; no TTS exists |
| Audit | Merchant/store-scoped mutation audit with idempotency, payload redaction and SQLite immutability guards | No external immutable audit export or retention tooling |

## Canonical data and money

SQLite is the current system of record. Money is integer paise in INR. Product, inventory, bill, order, Payment, Khata, audit, demand, sound and Sarkar action records carry merchant/store scope where applicable. Issued bill lines and Shop order lines are snapshots; later catalogue edits do not rewrite them.

The inventory balance distinguishes on-hand, reserved, and available quantity. Counter issue creates a reservation for physical products. A verified Paytm payment or adding the bill to Khata consumes that reservation. An eligible unpaid bill cancellation releases it. Shop checkout reserves stock; a verified payment does not itself mark an order fulfilled.

Khata ledger entries are append-only. Positive deltas increase the amount owed; repayments and reversals reduce or compensate the balance. `balance_paise` is a transactional projection used for guards; ledger entries remain the business history. Manual repayment is an explicitly confirmed merchant-attested receipt, not provider verification.

## Payment and verification boundary

The `Payment` row binds a local payment to one source record and one amount. Paytm callbacks are hints; the adapter validates the response checksum before interpreting status, then validates the configured MID, provider order or link identity, currency, exact positive paise amount, non-empty transaction ID, and source binding before settlement. Malformed, unsigned, or ambiguous responses remain unresolved. Staging payment actions require `PAYTM_TEST_ENABLED=true` in `development` or `test`; the production environment blocks staging actions. Production-host payment actions require both `WAPAS_ENV=production` and the explicit `PAYTM_LIVE_ENABLED=true` release gate. Both switches are false by default. The fake gateway is a simulator and its Counter/Khata successes do not write a repayment or create a Paytm sound event.

The SoundEvent outbox is written only by the verified Paytm settlement path and in the same database transaction as source settlement. Device polling and acknowledgement are scoped to the signed-in merchant/store and registered device cursor. The browser starts muted, can show committed events without audio, and tracks delivery, acknowledgement, and playback separately. Audio playback can only be reported after the browser's play promise/event confirms it; a blocked or muted browser is not described as having played sound.

## Schema and migration posture

Schema initialization is additive and establishes the default installation merchant/store identity. The existing unscoped recovery data is backfilled to that identity. Tests use temporary databases. A separate online-backup helper is documented in `migration-recovery.md`.

**Data-safety incident, 2026-10-29:** while setting up the browser harness, its parent ran `db.init_db()` against the protected `D:\Wapas\wapas.db` and modified schema/data for the 630 existing Payment rows. The migration defaults now visible on those rows do not establish historical provider or currency. On 2026-10-30, a verified online backup was created, then only the test account was disabled and its session revoked; the payment-row-value SHA-256 digest still matches the verified backup. The incident evidence and backup hash are in [incident-containment-2026-10-30.md](incident-containment-2026-10-30.md). No rollback, payment relabeling, or migration rehearsal was performed. The application now blocks ORM engine creation for the protected database and its `-wal`, `-shm`, and `-journal` sidecars, including recognized SQLite `file:` URI aliases and file aliases, unless an operator explicitly sets `WAPAS_ALLOW_PROTECTED_DB_WRITES=true`; normal tests and browser runs use disposable databases.

This implementation does not add a production migration runner or prove migration/restore against an operator-selected database copy. Existing installations need a dated backup and rehearsed migration before use.

## Input review and unimplemented target paths

Business APIs validate request fields and use domain services; Sarkar cannot run SQL or call a payment provider. Its stock receipt path previews exact product/quantity and requires a one-time owner confirmation bound to actor, browser session, payload, current stock state, and expiry. Counter image uploads are size/type/decode checked and re-encoded before processing. They are sent externally only when a vision provider is configured and the user consents; otherwise the UI returns `NOT CONFIGURED` and offers manual search/transcription. Model responses supply names and uncertainty only; product IDs, prices, and stock come from the current tenant's saved catalogue. Voice input is turn-based Sarvam STT with explicit consent, transcription display, manual review, and no bill issue shortcut. It was not provider-tested for Counter. A shared approval queue, broader Sarkar mutations, and TTS are not implemented.

Storefront QR verification requires HTTPS, rejects localhost/private/link-local/reserved IPs and DNS results, pins the checked addresses for its outbound TLS request, disables redirects and environment proxy use, caps the response, validates the product response shape and exact store slug, and preserves `NOT_READY` until that check succeeds. Tests cover private DNS, unsafe URL forms, redirects, identity/response mismatch, DNS failure, timeout, and refused connections. This workspace's configured URL is local HTTP and QR remains `NOT_READY`; no public endpoint or phone scan was verified.

## Deployment boundary

The application currently uses SQLite and local configuration. Atlas has no adapter in this runtime. One read-only query for a fresh random Paytm reference returned `NOT_FOUND` and its response checksum validated. This verifies a signed status response only; Paytm checkout, Payment Links, and settlement remain **CONFIGURED BUT UNVERIFIED**. The connected Render service was previously reported as pointing at `rushmanthnalluri/AI-Revenue-Recovery`, a different repository that contains a forbidden Razorpay module; this pass could not refresh that inspection because the connector requires a workspace selection. No service was deployed to or changed. Before deployment, confirm source repository/branch, database/persistent storage, environment, callback URL, worker ownership, and backup/recovery behavior.

## Hosting readiness endpoint

The local Render Blueprint targets `/healthz`, which returns only `ready` or `not_ready`. It checks `SELECT 1` against the configured database and freshness of the in-process worker heartbeat; it does not expose internal diagnostics. `/api/state` remains authenticated and is not used as a host health probe. `PUBLIC_BASE_URL` explicitly overrides the configured public URL; on Render, `RENDER_EXTERNAL_URL` supplies the default when no explicit value is set. This code and manifest were tested locally but were not deployed. The new private GitHub repository is not yet linked to the existing Render service.
