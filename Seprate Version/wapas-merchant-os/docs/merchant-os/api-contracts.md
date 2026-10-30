# Wapas Merchant OS — implemented API contracts

Updated: 2026-10-30. This is a route guide to the local implementation. The APIs use the existing `/api/merchant` and `/api/public` prefixes; the earlier proposed `/api/v1` paths were not implemented.

## Shared request rules

- Private merchant routes require a valid session cookie linked to an active membership. Merchant/store IDs and role are resolved server-side; clients cannot choose their tenant in the request body.
- Console writes require the session CSRF token in `X-Wapas-CSRF` and a same-origin request. `WAPAS_ENV=production` requires HTTPS for the origin and sets secure cookies/HSTS.
- Staff access is limited to catalogue, Counter bills, order listing/fulfillment, and read-only Sarkar requests. Other private routes are owner-only.
- Public routes resolve a store by slug. Public order status requires the random order token in `X-Order-Token`.
- Amounts use integer paise. Inventory quantities use decimal values. State labels in responses are persisted domain state; client redirects do not establish payment success.
- Some writes accept an `idempotency_key` in their JSON body. Do not assume every route accepts the standard `Idempotency-Key` header.

## Authentication

| Method and path | Purpose |
|---|---|
| `POST /api/auth/login` | Verify password and optionally select a membership; sets session and CSRF cookies |
| `GET /api/auth/session` | Return the current membership identity and CSRF token |
| `POST /api/auth/logout` | Revoke the current session and clear cookies |

Login accepts username/password and, where needed, a membership ID. Provision the first owner through `app.auth_cli`; there is no public owner signup route.

## Catalogue and inventory

| Method and path | Purpose |
|---|---|
| `GET /api/merchant/catalog/products` | List the current store's products with on-hand, reserved, and available quantity |
| `GET /api/merchant/catalog/products/lookup` | Resolve a product by product ID, barcode, or SKU |
| `POST /api/merchant/catalog/products` | Create a product with unit price and optional opening stock |
| `PATCH /api/merchant/catalog/products/{product_id}` | Update catalogue fields and active/archive state |
| `POST /api/merchant/catalog/products/{product_id}/stock-adjustments` | Apply an idempotent stock adjustment with reason |
| `GET /api/merchant/catalog/movements` | Read the store's recent stock movements |
| `GET /api/merchant/opportunities/pulse` | Aggregate persisted unmatched and out-of-stock public searches |

## Counter billing and Khata

| Method and path | Purpose |
|---|---|
| `POST /api/merchant/bills` | Create/reuse a draft bill by body `idempotency_key` |
| `GET /api/merchant/bills` / `GET /api/merchant/bills/{bill_id}` | List or read current-store bills and line/payment state |
| `PUT /api/merchant/bills/{bill_id}/lines/{product_id}` | Set a draft line quantity; product and price come from the server catalogue |
| `DELETE /api/merchant/bills/{bill_id}/lines/{line_id}` | Remove a draft line |
| `POST /api/merchant/bills/{bill_id}/issue` | Validate and issue the immutable bill snapshot; reserves physical stock |
| `POST /api/merchant/bills/{bill_id}/payments` | Create/reuse a Counter collection attempt; body carries `idempotency_key` |
| `POST /api/merchant/bills/{bill_id}/cancel` | Cancel a draft or eligible unpaid issued bill; releases held stock where applicable |
| `POST /api/merchant/bills/{bill_id}/khata` | Add an eligible issued bill as customer credit |
| `POST /api/merchant/bills/{bill_id}/input/photo` | Multipart `image` plus optional `consent_to_external_processing`; returns tenant-catalogue candidates for review |
| `POST /api/merchant/bills/{bill_id}/input/parchi` | Multipart `image` plus optional `consent_to_external_processing`; returns extracted list candidates for review |
| `POST /api/merchant/bills/{bill_id}/input/voice` | Multipart `audio` plus optional `consent_to_external_processing`; turn-based Sarvam transcription and candidate lines for review |
| `POST /api/merchant/bills/{bill_id}/input/text` | JSON `{ "text": "2 rice bags" }`; manual Parchi transcription parsed into candidate lines |
| `GET /api/merchant/khata/accounts` / `GET /api/merchant/khata/accounts/{account_id}` | List balances or read ledger and any pending collection |
| `POST /api/merchant/khata/accounts/{account_id}/repayments` | Record an owner-confirmed cash/other receipt with amount and idempotency key |
| `POST /api/merchant/khata/accounts/{account_id}/payment-links` | Create/reuse a collection attempt for the requested amount |
| `POST /api/merchant/khata/entries/{entry_id}/reverse` | Append a compensating Khata ledger entry with reason |

An issued Counter bill has `state=ISSUED`; payment remains separate (`NOT_RECORDED`, `PENDING`, `PAID`, or `FAILED` on the bill projection). A fake Counter/Khata collection is marked `SIMULATED` at the Payment layer and is not a verified receipt. A Khata repayment requires `confirm_received=true`; the API records the merchant-attested basis.

All four non-typed input routes require an editable draft. Images are limited to 8 MB, JPEG/PNG/WebP, decoded and re-encoded with EXIF removed and dimensions bounded. Audio is limited to 12 MB and an allowed audio MIME. The route returns review-only candidates; it never changes draft lines. Photo/Parchi processing returns `NOT CONFIGURED` when the separately configured vision service is absent and requires explicit consent before external processing. Voice returns `NOT CONFIGURED` when Sarvam STT is absent and requires explicit consent before transcription. The UI/manual transcription fallback remains available. Candidate identity, price, stock, and issue state are resolved by Wapas; reviewed candidates are added with the existing `PUT /lines/{product_id}` route, and issuance still uses the canonical issue service.

## Public Shop and merchant orders

| Method and path | Purpose |
|---|---|
| `GET /s/{store_slug}` | Render the public store page |
| `GET /api/public/stores/{store_slug}/products` | Read active public products and current availability |
| `GET /api/public/stores/{store_slug}/search?q=...` | Search the public catalogue; no-match/out-of-stock results may create privacy-minimized demand events |
| `GET /api/public/stores/{store_slug}/qr.png` | Return the QR only when the target URL is verified |
| `POST /api/public/stores/{store_slug}/checkout` | Revalidate server price/availability, reserve stock, and start or reuse checkout |
| `GET /api/public/orders/{order_id}` | Read an order using `X-Order-Token` |
| `GET /api/merchant/orders` | List orders for the signed-in store |
| `POST /api/merchant/orders/{order_id}/fulfill` | Mark a paid order fulfilled after explicit confirmation |
| `GET /api/merchant/storefront/qr` | Read QR readiness and target URL |
| `POST /api/merchant/storefront/qr/verify` | Check the configured public HTTPS store endpoint and store identity |
| `GET /api/merchant/storefront/qr.png` | Return the verified merchant QR |

Public checkout accepts customer and item details plus an idempotency key and order token. The server aggregates repeated product IDs and recomputes amount. The QR is not ready merely because an image can be generated; the public URL must resolve only to public IP addresses, answer over HTTPS without a redirect, return a bounded JSON product response, and identify the expected store. DNS answers are pinned for the verification connection to prevent a second lookup from reaching a different address. The configured workspace URL is local HTTP and remains `NOT_READY`.

## Sarkar and Sound Mode

| Method and path | Purpose |
|---|---|
| `POST /api/merchant/sarkar/ask` | Ask a deterministic typed query, or submit an optional turn-based audio clip for Sarvam STT |
| `GET /api/merchant/sarkar/tools` | List typed tool schemas and role/permission/approval metadata available to the current role |
| `POST /api/merchant/sarkar/tools/{tool_name}` | Invoke a validated, tenant-scoped registry tool |
| `POST /api/merchant/sarkar/actions/{action_id}/confirm` | Execute the exact, unexpired stock receipt prepared for the same owner session |
| `POST /api/merchant/sound/device` | Register a browser device key and obtain its scoped cursor |
| `GET /api/merchant/sound/events` | Poll verified sound events after the device cursor |
| `POST /api/merchant/sound/events/ack` | Acknowledge delivered event IDs for that device |

Sarkar's registry currently includes `inspect_stock`, `inspect_khata`, `inspect_khata_history`, `inspect_orders`, `inspect_recent_bills`, `inspect_low_stock`, `summarize_verified_payments`, `explain_payment_state`, `inspect_business_summary`, and `inspect_unmet_demand`. Read tools are role-gated and use the authenticated merchant/store context. `prepare_stock_receipt` and `confirm_stock_receipt` preserve the existing one-time, expiring, session-bound token and also recheck the proposed stock state. Stock receipt is the only mutation. There are no generic SQL/write tools and no other approval-backed mutations. Tool results are schema-validated and carry a correlation ID. Opportunity Pulse responses describe recorded unmatched/out-of-stock searches only; they do not establish sales or demand forecasts. Sarkar audio remains optional turn-based STT; TTS is not implemented. Sound events are created by verified Paytm settlement only.

The registry publishes timeout and retry metadata (`3 seconds`, `0 automatic retries` for the current tools); invocation enforces a runtime deadline using thread-pool isolation and returns HTTP 504 when it expires, covered by `tests/test_sarkar.py`. Each successful tool call now persists a tenant-scoped `sarkar.tool_executed` audit event with its name/version, correlation ID, input digest and field names, output field/count summary, and provenance. Raw customer/payment output is not duplicated into the trace. The durable `SarkarAction` record and confirmation evidence continue to apply to the existing stock-receipt workflow.

## Payment callbacks and compatibility routes

The existing recovery/payment routes remain registered, including `/api/paytm/callback`, `/api/paytm/txn-callback`, `/api/paytm/payment-callback`, and legacy Shop/recovery routes in `app/api.py` and `app/store.py`. Their presence is compatibility code, not evidence that a real Paytm flow has been completed. Callbacks are checked and followed by provider-side status verification where supported; the Paytm status response checksum is mandatory before a status is interpreted. A success additionally requires exact MID/order, INR paise amount, non-empty transaction ID, and source binding. Unsigned, malformed, mismatched, and unknown results remain unresolved.

Paytm payment actions are environment-gated: `PAYTM_TEST_ENABLED` defaults to false and staging link/checkout creation is allowed only when it is explicitly true in `WAPAS_ENV=development` or `test`. Production mode blocks staging requests. Production hosts require both `WAPAS_ENV=production` and explicit `PAYTM_LIVE_ENABLED=true`; the release flag remains false by default. Status queries are read-only and do not establish checkout capability.

## Errors and verification

FastAPI validation and domain errors use the existing route-specific response shape; there is not yet one uniform `code/message/request_id` envelope. Provider secrets and raw session tokens must not be returned. Verify financial state by reading the persisted source record and Payment after server-side reconciliation, not by trusting a customer redirect, callback alone, or simulated result.
