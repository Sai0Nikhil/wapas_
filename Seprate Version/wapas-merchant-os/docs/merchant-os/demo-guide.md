# Wapas Merchant OS — isolated local demo

Updated: 2026-10-30. This walkthrough uses a disposable SQLite file and the fake gateway. It exercises local product, Counter, Shop, Khata, and limited Sarkar flows. All fake payment results are simulations and do not establish a real receipt.

**Protected database notice:** a browser-harness setup error on 2026-10-29 ran additive schema initialization against `D:\Wapas\wapas.db`, assigned `store_default` and default payment metadata to all 630 existing Payment rows, and inserted one `counter-browser-smoke` OWNER account/membership/session; the WAL was modified. A verified online backup was made on 2026-10-30, then only that test account was disabled and its session revoked. Historical provider/currency values remain unknown. Do not use that file for this demo; the application now blocks routine ORM access to it, and the harness asserts it uses a disposable path. See [incident-containment-2026-10-30.md](incident-containment-2026-10-30.md).

## Start with a new demo database

Use a fresh PowerShell window from the project folder. The process settings below override local configuration for this window and keep the populated `wapas.db` out of the demo.

```powershell
$env:WAPAS_ENV = "development"
$env:GATEWAY = "fake"
$env:DATABASE_URL = "sqlite:///./wapas-merchant-os-demo.db"
$env:PUBLIC_BASE_URL = "http://127.0.0.1:8000"
$env:PAYTM_LIVE_ENABLED = "false"
$env:PAYTM_TEST_ENABLED = "false"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell window, set the same `WAPAS_ENV` and `DATABASE_URL`, then create the owner account:

```powershell
$env:WAPAS_ENV = "development"
$env:DATABASE_URL = "sqlite:///./wapas-merchant-os-demo.db"
python -m app.auth_cli create-owner --database-url sqlite:///./wapas-merchant-os-demo.db --username owner
```

Open <http://127.0.0.1:8000/login> and sign in with the password entered by the command. Do not use the populated database for this demo.

## Demo the shared records

1. In **Catalogue & stock**, create a physical product with opening stock. Check its on-hand, reserved, and available quantities.
2. In **Counter**, create a bill, add a product by catalogue search or scan its barcode into the scanner field, and issue it. Rapid duplicate scanner-key events are suppressed; later scans aggregate quantity. The server resolves price and reserves stock. The bill displays `NOT_RECORDED` until a collection is requested.
3. For Parchi fallback, enter a line such as `2 Basmati rice` under manual transcription, review the saved-catalogue match and quantity, then add it to the open draft. The browser smoke exercised this route at desktop and 390 px. Photo/OCR recognition currently shows `NOT CONFIGURED` because no vision provider is enabled; no image is sent and the draft is unchanged. Voice input is turn-based and asks for explicit consent before sending audio to Sarvam; provider transcription was not tested in this sprint.
4. Choose **Create payment link**. The local fake link clearly says it is a test checkout. Opening and paying that fake link marks the Counter result `SIMULATED`; it does not consume the reservation, count as verified money, or trigger Paytm Sound Mode.
5. Create another bill for a customer and choose **Add to Khata**. Inspect the account ledger and outstanding balance. If demonstrating manual receipt, enter a partial amount and confirm only after treating it as an owner-attested test receipt. It is not Paytm-verified.
6. In **Khata**, create a fake collection link and pay it on the local fake page. The result remains simulated and the ledger balance does not change. Do not label it a repayment.
7. Open the storefront at <http://127.0.0.1:8000/s/default-store>. It uses the same catalogue. A fake Shop checkout opens the explicitly labelled fake checkout page; its saved result only demonstrates simulator state transitions. Do not count it as real payment or business performance evidence.
8. Ask Sarkar to inspect stock, recent bills, payment state, low-stock items, Khata, orders, verified payment summaries, or recorded unmet-demand events. Use the **Sarkar tools** list for the typed input/output schemas and current role permissions. Sarkar tools enforce a declared execution deadline (`timeout_seconds`), raising HTTP 504 on timeout. `received 2 kg rice` can prepare a stock receipt only if there is one clear catalogue match; the owner reviews and confirms the exact proposal once. Inspect the saved stock movement afterward. No other Sarkar mutation is available.
9. Search the public store for an absent or out-of-stock item more than once. Opportunity Pulse aggregates repeated recorded searches and displays evidence-backed business indicators (low stock items, verified Paytm sales, Khata credit outstanding, and pending fulfillments) directly derived from persisted records. It shows a not-enough-data state until the minimum search threshold is reached. Searches indicate interest, not guaranteed demand.

The **Sound Mode** page starts muted. Fake payments do not create verified Paytm events; the empty page is expected. The UI distinguishes a committed event, browser delivery, acknowledgement, and playback. Enabling sound does not prove that audio played; browser audio was not exercised in this smoke run. All 7 negative payment conditions fail-closed without sound emission.

## QR and real Paytm boundary

This demo uses localhost HTTP. The storefront QR intentionally remains unavailable. Verification rejects local/private/reserved network targets, unsafe URL forms, DNS failure, redirects, malformed product responses, timeouts/refused connections, and a mismatched store slug; the verified DNS addresses are pinned for the HTTPS request. A printable QR requires a public HTTPS URL, successful reachability and store-identity verification, then a phone scan; none of those are demonstrated here.

No Paytm test or live transaction has been completed for this installation. Do not replace `GATEWAY=fake` with Paytm as a demo shortcut. Staging writes remain off unless `PAYTM_TEST_ENABLED=true` is deliberately set in a non-production environment; production mode rejects staging actions. Production-host payment actions additionally require the separate release gate `PAYTM_LIVE_ENABLED=true`. A Paytm run needs merchant capability, safe test credentials, reachable HTTPS callback configuration, and an authorized controlled transaction/reconciliation check. See `verification-matrix.md` for evidence status.

## Stop and clean up

Stop Uvicorn with Ctrl+C. The demo database is separate from `wapas.db`. Remove `wapas-merchant-os-demo.db` only after confirming it is the disposable demo file and the server is stopped. Keep the fake mode visible in any screenshots or recordings.

## Latest local smoke result

The 2026-10-30 headless Chromium rerun passed scanner quantity aggregation, duplicate suppression, Parchi manual fallback, 390 px layout, payment-state wording, and stored-XSS rendering against a disposable database. Camera/microphone permissions, physical barcode hardware, and audio playback were not tested.
