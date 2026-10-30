# Wapas Merchant OS — current-state audit

Audit date: 2026-10-29

**Historical baseline:** this audit records the repository before Merchant OS implementation and is not a description of the current checkout. Later implementation and verification are in [implementation report](implementation-report-2026-10-29.md). The baseline database row counts and “unchanged during this audit” statement below describe the audit window only. A later browser-harness setup incident modified the protected SQLite database; see the report's protected-database section.

Scope: local workspace at D:\Wapas, the current SQLite file and tests, the connected GitHub and Render project records, the two referenced public repositories, and a non-deep run of Wapas’s integration doctor.

This is the baseline before Merchant OS feature implementation. No application code or existing database records were changed during this audit. New work starts from the contracts in architecture.md, state-machines.md, and api-contracts.md.

## Evidence and limits

- The local directory has no .git directory. Local branch, commit history, tracked/untracked status, and local remote cannot be verified. No AGENTS.md was found.
- The existing database is non-empty: 214 customer rows, 630 payment rows, and one event row; no cases. Only schema and row counts were read, not customer or payment contents.
- The test suite ran against per-test temporary SQLite databases: 111 passed, one Starlette/httpx deprecation warning, in 60.41 seconds.
- A normal doctor run made live, non-mutating status/chat/voice/token-auth checks, but the Windows console raised UnicodeEncodeError while printing. Re-running with Python UTF-8 mode completed. No payment checkout, payment link, or Telegram message was created or sent.
- External service checks are point-in-time evidence. They are not proof of a full checkout flow, production readiness, or service health after this audit.
- The local .env contains configured values. Secret values are deliberately omitted from this document.

## Repository and deployment identity

The local code is a small Python/FastAPI modular monolith with SQLModel, SQLite, and a static HTML/CSS/JavaScript interface. There is no local Node package manifest, Dockerfile, or Render Blueprint.

The connected GitHub and Render records show a separate public repository, <https://github.com/rushmanthnalluri/AI-Revenue-Recovery>, and Render services named pulserecover-api and pulserecover-web. The API service’s latest control-plane deploy is marked live and points at the repository’s 2026-09-06 commit. That repository has a different backend structure and contains a Razorpay service, which is forbidden by this product brief. The Render record is not evidence that the local D:\Wapas files are deployed. No deploy or source change was made.

The MongoDB Atlas connection requires reauthentication. The local app currently uses SQLite and the brief says to retain the existing database unless there is a measured reason to change it; Atlas was not added or queried.

## Existing application map

| Area | Local implementation | Current boundary |
|---|---|---|
| Owner application | FastAPI serves static app/static/index.html and app/static/app.js | One owner console, not a multi-merchant application |
| Store | app/store.py and app/static/shop.html | Four hard-coded products and a single-product checkout form |
| Database | SQLite through SQLModel; eight tables: Customer, Payment, Case, Decision, PolicyResult, ActionRecord, Outcome, Message, Evidence, Event (ten tables) | No canonical Merchant/Store record or tenant key |
| Schema evolution | create_all plus app/db.py additive missing-column helper | No versioned migration framework; existing schema is retained |
| Recovery loop | app/detect.py, agent.py, policy.py, executor.py, gateway/* | Existing revenue-recovery workflow must remain intact |
| Agent | Optional OpenAI-compatible LLM with deterministic rules fallback; three read-only context tools | Decision support for one failed payment, not a general merchant teammate |
| Policy | Fail-closed YAML for recovery links, quiet hours, opt-outs, duplicates, amount/confidence limits, VIP review, and refunds | Not yet a shared domain-action policy |
| Approvals | Signed, expiring Telegram owner buttons bound to a recovery decision; local console actions | No shared approval-request model for billing, stock, orders, or Khata |
| Voice | Sarvam STT/TTS; deterministic owner Q&A over recovered-payment, approval, and stopped-case counts | No voice-driven inventory, billing, order, or ledger mutation |
| Background work | In-process worker thread plus Telegram poller and store-order reconciler | No durable general-purpose job queue or worker deployment configured locally |
| Audit/evidence | Evidence stores redacted provider/owner/customer responses; Event is a human-readable timeline | Event is explicitly not an immutable audit log; no shared agent-run or verified-outcome domain model |
| UI checks | Existing Python API tests | No frontend package checks or browser E2E suite in the local project |

## Verified capability inventory

| Capability | Status | Evidence from this audit | Missing or limited |
|---|---|---|---|
| Revenue recovery rules and fake-gateway flow | TEST VERIFIED | 111 local tests passed; tests use fake gateway and temporary databases | A complete live Paytm recovery is not verified today |
| Existing Paytm status API authentication | LIVE VERIFIED (narrow scope) | Doctor received the expected not-found response for a deliberately unknown order at the configured staging host; MID/signature were accepted | This proves a status query, not checkout, link creation, callback delivery, or paid-order reconciliation |
| Paytm checkout and Payment Links | PARTIAL / NOT VERIFIED | Source adapters and test coverage exist; doctor did not run its deep mode | No public HTTPS callback URL; no test checkout or payment link attempted in this audit |
| Sarvam chat/reasoning endpoint | LIVE VERIFIED | Doctor received “OK” from configured sarvam-105b endpoint | This is a connectivity check, not proof of a correct merchant task |
| Sarvam speech | LIVE VERIFIED | Doctor generated Hindi audio and transcribed it back | Only the existing voice question path is present |
| Telegram bot authentication | LIVE VERIFIED (narrow scope) | getMe succeeded and configured owner/customer channel fields were recognized | A Telegram message send was not exercised |
| Local SQLite reachability/schema | LIVE VERIFIED | Doctor SELECT 1 and verified all existing tables/columns | SQLite has no merchant isolation; existing records are unscoped |
| Background worker | IMPLEMENTED / NOT VERIFIED | Worker loop and reconciliation code exist | It was not running in the doctor process; no hosted worker is configured here |
| Recovery policy and owner approval | TEST VERIFIED | Policy and approval tests passed in the 111-test suite | Policy covers recovery actions only |
| Integration doctor | PARTIAL / BROKEN ON DEFAULT WINDOWS CODE PAGE | UTF-8 rerun completed; normal invocation raised UnicodeEncodeError printing an arrow | Output needs safe console encoding behavior |
| Storefront checkout | PARTIAL | Static product list, public checkout endpoint, persisted Payment row, Paytm callback/status-check code, and fake checkout | Not a persistent catalogue/storefront; no cart, QR, order lifecycle, stock, or fulfillment state |
| Counter and digital bills | MISSING | No bill, bill-line, cart, barcode, photo, OCR, or Parchi entities or endpoints | All four input modes and one canonical bill workflow are absent |
| Inventory | MISSING | No product/SKU or stock balance/movement schema or service | No persistence, reservations, or shared product source |
| Storefront QR and online catalogue | MISSING | /shop is a fixed demo checkout; products are a Python constant | No store slug, public URL per merchant, generated QR, search, or persisted availability |
| Khata and collections | MISSING | No ledger, account, repayment, or collection-request schema | No outstanding balance or collection reconciliation |
| Sarkar merchant operations | MISSING | Existing recovery agent cannot perform store operations; voice asks about recovery counts | No shared typed tool registry, task pipeline, approval flow, or outcome memory for Merchant OS actions |
| Sound Mode | MISSING | Existing callbacks and recovery events are logged; no verified merchant payment notification/audio event for Counter/Shop/Khata | No merchant-scoped notification emitted only after verified payment |
| Opportunity Pulse | MISSING in Wapas | No persisted merchant-demand request model | The reference’s pulse numbers are hard-coded and must not be imported |
| Multi-merchant authentication/isolation | MISSING | Console has local-only/ADMIN_TOKEN gating and a single configured merchant name | No user session tied to a merchant/store or tenant-scoped database queries |
| n8n | NOT CONFIGURED | Doctor reports optional integration off | No n8n connection |
| MongoDB Atlas | NOT CONFIGURED for this app | Local DATABASE_URL is SQLite; Atlas connector reports reauthentication required | No Atlas runtime or migration plan |

The built-in doctor run reported Paytm as DEGRADED overall: status API authentication passed, but payment flow remained unproven and the configured public base URL was localhost. Sarvam LLM and voice were VERIFIED; Telegram bot token was VERIFIED but no message was sent; SQLite was VERIFIED; n8n was NOT CONFIGURED; worker was UNVERIFIED in that process.

## Payment implementation details found

- Existing recovery payment links use the Paytm Link API adapter and a per-case idempotency key.
- Existing test-store checkout writes a PENDING Payment before initiating Paytm checkout, validates callback checksum, calls server-side order status, and has a periodic reconciler for missed callbacks.
- Fake-gateway and recovery tests distinguish verified recovery amount from client-side success, including a wrong-amount recovery test.
- Store checkout products remain a hard-coded map. The store callback path should be included in later adversarial review for equality between the verified Paytm amount and the amount originally requested; its current record helper accepts the verified amount as the saved Payment amount rather than comparing it to the original expected snapshot.
- Official Paytm pages currently show different host families for different staging APIs. The configured host answered the order-status authentication check, but checkout and Payment Links capability are not verified. Do not change the configured provider host or claim end-to-end Paytm support without a supported merchant flow.

Official documentation reviewed: [Initiate Transaction API](https://www.paytmpayments.com/docs/api/initiate-transaction-api/), [Transaction Status API v3](https://www.paytmpayments.com/docs/api/v3/transaction-status-api/), [Create Link API](https://business.paytm.com/docs/api/create-link-api/), and [Callback and Webhook URL](https://business.paytm.com/docs/callback-and-webhook/).

## Baseline validation

| Validation | Result |
|---|---|
| Local backend suite | 111 passed, one deprecation warning |
| Default Windows doctor output | Failed while printing Unicode under cp1252; integration checks had already run |
| Doctor with UTF-8 mode | Command completed; Paytm overall DEGRADED, LLM/voice/database VERIFIED, Telegram authentication VERIFIED, n8n NOT CONFIGURED, worker UNVERIFIED |
| Database schema | Current relative to local SQLModel definitions |
| Paytm paid checkout/callback | NOT VERIFIED |
| Render health for local files | NOT VERIFIED; Render service points to different GitHub repository |
| Frontend build/browser E2E | NOT CONFIGURED / NOT RUN; static frontend has no package manifest |
| Clean startup | Not run during audit to avoid starting the background worker against the existing local database |

## Immediate implementation priorities

1. Preserve and regression-test revenue recovery, Paytm callback verification, approval signing, and the existing fake-gateway path.
2. Define merchant identity and tenant scoping before adding new business records.
3. Add durable inventory and canonical product/catalogue records before building Counter or Shop.
4. Add a canonical bill and payment-attempt model with verified payment state separate from bill/order state.
5. Add Khata as an append-only ledger with exact-once repayment reconciliation.
6. Route Sarkar through typed plans, deterministic validation/policy, approval, execution, verification, audit, and merchant-scoped context.
7. Keep the current Paytm adapter and credentials in explicitly tested/configured state; no Razorpay code or dependency.
8. Reconcile the local folder with the intended GitHub/Render source before any remote deploy. Do not deploy the separate Razorpay-containing repository as Wapas Merchant OS.

