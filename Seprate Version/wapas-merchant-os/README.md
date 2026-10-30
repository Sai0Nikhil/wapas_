# Wapas

Wapas is a FastAPI application for payment recovery and day-to-day kirana work. The original recovery workflow remains in the app. The Merchant OS work adds a shared catalogue and stock ledger, Counter bills, a QR storefront, Khata, verified Paytm collection handling, Sound Mode, and a limited typed Sarkar assistant.

The codebase is a modular monolith backed by SQLModel. The current local database is SQLite. Merchant and store scope comes from a signed-in membership session for private console routes.

## Current release status

**INTEGRATION IN PROGRESS.** This local build has not been deployed or tested with a real or Paytm test-mode payment. Use the fake gateway only as a clearly labelled simulator.

| Area | Current evidence |
|---|---|
| Existing revenue recovery | Regression-tested with the fake gateway and mocked Paytm responses |
| Catalogue, stock, Counter, Shop, and Khata | Domain and API tests use temporary SQLite databases |
| Paytm identity, amount, and status checks | Adapter tests with mocked provider responses; a random-reference status query returned `NOT_FOUND`, which does not prove merchant checkout capability; no payment link or checkout was created |
| Sound Mode | Outbox is written only for a verified Paytm payment and is tested for duplicate suppression; no real alert was received |
| Sarkar | Deterministic typed router for stock, Khata, orders, daily saved-record summary, and demand; stock receipts require a one-time owner confirmation |
| Voice | Optional turn-based Sarvam transcription input; no live voice conversation or Sarkar spoken response |
| Opportunity Pulse | Aggregates repeated public storefront searches and stockout searches; it does not estimate sales |
| MongoDB Atlas / Render | Atlas is not integrated. The inspected Render API/web service points to another repository containing a forbidden Razorpay module; no deployment or source change was performed |

See [implementation status](docs/merchant-os/implementation-status.md), [verification matrix](docs/merchant-os/verification-matrix.md), and the dated [latest implementation report](docs/merchant-os/implementation-report-2026-10-30.md) for current evidence and limitations.

## Run locally

Requirements: Python 3.10 or newer. The frontend is static HTML, CSS, and JavaScript; there is no separate frontend build step.

1. Copy `.env.example` to `.env` and set `WAPAS_ENV=development` for a local HTTP demo. Leave `GATEWAY=fake` to keep payments simulated.
2. If using an existing SQLite database, make a dated online backup first. Follow [migration and recovery](docs/merchant-os/migration-recovery.md); do not copy only the `.db` file while WAL mode is active.
3. Start `run.bat` on Windows or `./run.sh` on macOS/Linux. Startup initializes the schema and default installation identity.
4. In a second terminal, provision the first owner account. The password is entered interactively and is not passed on the command line:

   ```powershell
   .\.venv\Scripts\python.exe -m app.auth_cli create-owner --database-url sqlite:///./wapas.db --username owner
   ```

   Use the exact database URL configured for this installation. On macOS/Linux, use `.venv/bin/python` instead.
5. Sign in at <http://localhost:8000/login>.

Production uses `WAPAS_ENV=production`, HTTPS, a reachable configured callback URL, an initialized database, and a provisioned owner account. Do not expose the owner console through a tunnel. The legacy `ADMIN_TOKEN` is ignored for authentication.

## Local demo path

1. Add a catalogue product with opening stock.
2. Create and issue a Counter bill. Counter prices and stock are resolved on the server.
3. Create a collection link. With `GATEWAY=fake`, the UI marks it **SIMULATED**; it is not a real payment and it does not create a verified Paytm Sound Mode alert or Khata repayment.
4. Add another issued bill to Khata, then inspect the ledger or prepare a collection link. A fake collection leaves the ledger unchanged.
5. Open the persistent storefront from the Catalogue & stock tab. Public searches that find no product or only out-of-stock matches are counted in Opportunity Pulse after repeated observations.
6. Ask Sarkar to inspect stock, Khata, orders, today's saved-record summary, or unmet demand. A goods receipt is only prepared; the owner must confirm the exact product and quantity in the same browser session.

The storefront QR remains unavailable until a public HTTPS storefront responds with the expected store identity. Verification pins the checked DNS address and does not follow redirects. No public URL or phone scan was tested in this implementation cycle.

## Payment modes

- `GATEWAY=fake` uses local test pages and clearly labelled simulated results.
- `GATEWAY=paytm` selects the Paytm adapter. Configuration alone does not prove that checkout or Payment Links are enabled for a merchant.
- `PAYTM_LIVE_ENABLED` defaults to `false`. Paytm status identity, amount, currency, and source binding are verified server-side before payment state changes. A callback alone is never payment proof.
- No Paytm payment link, checkout, external message, or transaction was created during this implementation cycle. Paytm's official status pages document different staging hosts for different API variants; the configured host is documented for JS Checkout status verification, but the enabled merchant product remains unconfirmed. The provider workflow remains **CONFIGURED BUT UNVERIFIED** end to end.

## Security and data

- Private API access uses revocable browser sessions, owner/staff memberships, session-bound CSRF protection, same-origin checks, and server-resolved merchant/store IDs.
- Staff access is limited to Counter, catalogue, orders, and read-only Sarkar requests. Consequential stock receipt confirmation is owner-only and tied to the user, session, payload, expiry, and one-time token.
- Passwords use scrypt; raw session and CSRF tokens are not stored as database values.
- Payment, stock, audit, and Khata mutations are idempotent and linked to merchant/store scope.
- The protected `wapas.db` was modified by the disclosed 2026-10-29 setup incident; the harness account was later disabled and its session revoked after an integrity-checked online backup. Its 630 historical Payment rows retain uncertain provider/currency history. Tests and browser smoke use disposable SQLite databases; see [incident containment](docs/merchant-os/incident-containment-2026-10-30.md).

## Verification

Run the Python suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The latest verification results are recorded in [verification matrix](docs/merchant-os/verification-matrix.md). JavaScript syntax and Python compilation checks are not substitutes for the full suite.

## Known limitations

- Barcode/SKU lookup supports keyboard-emulating scanners and was tested in a local browser smoke; physical scanner and camera-device behavior were not tested. Photo and Parchi recognition return review-only suggestions when separately configured; vision/OCR is **NOT CONFIGURED**. Voice input is turn-based Sarvam transcription with review; no provider request or microphone test was made.
- Sarkar currently uses deterministic routing over a small fixed set of typed tools. It does not use an LLM to plan or execute general merchant tasks. Voice input is turn-based Sarvam STT when configured; there is no streaming conversation, interruption handling, or Sarkar TTS output.
- Opportunity Pulse shows repeated storefront search outcomes only. Searches are evidence of interest, not purchase intent, and no revenue is inferred.
- Paytm checkout/Payment Link availability, public callback reachability, public QR readiness, and real payment settlement are not verified for this installation.
- SQLite is the active database. MongoDB Atlas is not integrated. The connected Render project belongs to another repository and was not used or changed.
- A limited isolated Chromium Counter smoke passed. No full browser E2E suite, production build, live payment, public URL reachability, external notification, Render deployment, Atlas write, camera/microphone/audio QA, Canva design, or LinkedIn publication was performed.
