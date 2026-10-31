# Flutter to Wapas Merchant OS API Mapping

This document maps each screen of the Wapas Flutter App (`wapas_app/`) to the real backend endpoints of `wapas-merchant-os`.

---

## 1. Authentication & Tenant Session

| Action / UI | HTTP Endpoint | Method | Request Payload / Params | Response Fields | Role / Security |
|---|---|---|---|---|---|
| **Login** | `/api/auth/login` | `POST` | `LoginRequest`<br>• `username`: str<br>• `password`: str<br>• `membership_id`: opt str | `authenticated`: bool<br>`username`: str<br>`membership_id`: str<br>`role`: OWNER / STAFF<br>`merchant_id`: str<br>`store_id`: str<br>`store_slug`: str<br>`merchant_name`: str<br>`store_name`: str<br>`csrf_token`: str<br>`expires_at`: ISO str<br>*Cookies Set: `wapas_session`, `wapas_csrf`* | Public<br>Throttled login |
| **Current Session** | `/api/auth/session` | `GET` | Cookie: `wapas_session` | Same as login identity payload | All authenticated users |
| **List Memberships** | `/api/auth/memberships` | `GET` | Cookie: `wapas_session` | `{"memberships": [{"id", "store_id", "store_name", "store_slug", "role", "is_active"}]}` | All authenticated users |
| **Switch Store** | `/api/auth/switch-membership` | `POST` | `SwitchMembershipRequest`<br>• `membership_id`: str<br>Header: `x-wapas-csrf`, Cookie: `wapas_csrf`, `wapas_session` | Updated identity payload with rotated `csrf_token` and new session cookies | Same-origin + CSRF |
| **Logout** | `/api/auth/logout` | `POST` | Header: `x-wapas-csrf`, Cookies: `wapas_session`, `wapas_csrf` | `204 No Content`<br>Deletes `wapas_session` & `wapas_csrf` | CSRF required |
| **Register (Demo)** | `/api/auth/register` | `POST` | `RegisterRequest`<br>• `business_name`, `store_name`, `username`, `password`, `phone`, `city` | Same as login payload | Public |

---

## 2. Recovery Control Tower Screen (`RecoveryTowerScreen`)

| Action / UI | HTTP Endpoint | Method | Request Payload / Params | Response Fields | Role / Security |
|---|---|---|---|---|---|
| **Live State & Counts** | `/api/state` | `GET` | None | `counts`: `{flagged, contacted, paid, waiting_owner, stopped_by_policy, recovered_inr, recovered_fmt}`<br>`cases`: list of case summaries `{id, name, customer_id, language, amount, amount_fmt, state, diagnosis, confidence, messages_sent, opened_at, source}`<br>`messages`: recent chat logs<br>`events`: system audit events | All authenticated |
| **Case Detail & Evidence** | `/api/cases/{case_id}` | `GET` | Path: `case_id` | `id`, `name`, `amount`, `state`, `diagnosis`, `confidence`<br>`history`: `{on_time, late, vip, opted_out}`<br>`decision`: `{diagnosis, evidence, options, chosen_action, confidence, reasoner}`<br>`policy`: list of `{outcome, rule, version, at}`<br>`actions`: list of `{kind, key, state, error, sent_at}`<br>`outcome`: `{result, txn_id, amount, detail}`<br>`messages`: customer communication thread<br>`timeline`: event history | All authenticated |
| **Case Evidence Bundle** | `/api/cases/{case_id}/evidence` | `GET` | Path: `case_id` | Structured JSON evidence (telemetry, payment request logs, risk score) | All authenticated |
| **Owner Approve Action** | `/api/owner/approve/{case_id}` | `POST` | Path: `case_id`<br>Header: `x-wapas-csrf` | `{"state": "APPROVED"}` | OWNER role only |
| **Owner Skip Action** | `/api/owner/skip/{case_id}` | `POST` | Path: `case_id`<br>Header: `x-wapas-csrf` | `{"state": "SKIPPED"}` | OWNER role only |

---

## 3. POS Counter & Billing Screen (`PosBillingScreen`)

| Action / UI | HTTP Endpoint | Method | Request Payload / Params | Response Fields | Role / Security |
|---|---|---|---|---|---|
| **Catalog Products List** | `/api/merchant/catalog/products` | `GET` | Query: `q` (opt), `category` (opt), `limit`, `offset` | `{"items": [{"id", "name", "category", "price", "unit", "barcode", "current_stock", "is_active"}], "total": int}` | STAFF & OWNER |
| **Barcode Scan Lookup** | `/api/merchant/catalog/products/lookup` | `GET` | Query: `barcode` | Product object `{id, name, price, unit, barcode, current_stock}` or 404 | STAFF & OWNER |
| **Create Draft Bill** | `/api/merchant/bills` | `POST` | `BillCreate`<br>• `idempotency_key`: str<br>• `customer_name`: opt str<br>• `customer_phone`: opt str | `Bill`: `{id, bill_number, status: "DRAFT", lines: [], total_paise: 0, created_at}` | STAFF & OWNER |
| **Add / Update Line** | `/api/merchant/bills/{bill_id}/lines/{product_id}` | `PUT` | `BillLineSet`<br>• `quantity`: Decimal<br>• `unit_price_paise`: opt int | Updated `Bill` object with recalculated `total_paise` | STAFF & OWNER |
| **Remove Line** | `/api/merchant/bills/{bill_id}/lines/{line_id}` | `DELETE` | Path: `bill_id`, `line_id` | Updated `Bill` object | STAFF & OWNER |
| **Issue Bill** | `/api/merchant/bills/{bill_id}/issue` | `POST` | `BillIssue`<br>• `idempotency_key`: str | Updated `Bill` with status `"ISSUED"` | STAFF & OWNER |
| **Record Payment** | `/api/merchant/bills/{bill_id}/payments` | `POST` | `BillPaymentRequest`<br>• `method`: `"CASH"` \| `"PAYTM_DYNAMIC_QR"` \| `"KHATA"`<br>• `idempotency_key`: str | Updated `Bill` with payment verification status and provider references | STAFF & OWNER |
| **Charge to Khata** | `/api/merchant/bills/{bill_id}/khata` | `POST` | `BillKhataCharge`<br>• `customer_phone`: str<br>• `customer_name`: str<br>• `idempotency_key`: str | Updated `Bill` linked to customer Khata account | OWNER role |
| **Get Bill Receipt** | `/api/merchant/bills/{bill_id}/receipt` | `GET` | Path: `bill_id` | HTML printable receipt | STAFF & OWNER |
| **Cancel Bill** | `/api/merchant/bills/{bill_id}/cancel` | `POST` | Path: `bill_id` | Cancelled bill object | STAFF & OWNER |
| **Parchi / Photo Input** | `/api/merchant/bills/{bill_id}/input/parchi` | `POST` | Multipart file: image | OCR extracted bill lines preview | STAFF & OWNER |

---

## 4. Digital Khata Ledger Screen (`KhataLedgerScreen`)

| Action / UI | HTTP Endpoint | Method | Request Payload / Params | Response Fields | Role / Security |
|---|---|---|---|---|---|
| **List Khata Accounts** | `/api/merchant/khata/accounts` | `GET` | Query: `limit`, `offset`, `search` | `{"items": [{"id", "customer_name", "phone", "balance_paise", "credit_limit_paise", "last_activity_at"}], "total": int}` | OWNER role |
| **Account Detail & Ledger** | `/api/merchant/khata/accounts/{account_id}` | `GET` | Path: `account_id` | Account profile + `entries`: list of `{id, type: "DEBIT"|"CREDIT", amount_paise, balance_after_paise, note, created_at}` | OWNER role |
| **Record Repayment** | `/api/merchant/khata/accounts/{account_id}/repayments` | `POST` | `KhataRepayment`<br>• `amount_paise`: int<br>• `method`: `"CASH"` \| `"OTHER"`<br>• `idempotency_key`: str<br>• `note`: str<br>• `confirm_received`: bool | Recorded repayment entry and updated account balance | OWNER role |
| **Generate Payment Link** | `/api/merchant/khata/accounts/{account_id}/payment-links` | `POST` | `KhataCollectionRequest`<br>• `amount_paise`: int<br>• `idempotency_key`: str | `{"payment_link_id", "short_url", "qr_code", "amount_paise"}` | OWNER role |
| **Reverse Entry** | `/api/merchant/khata/entries/{entry_id}/reverse` | `POST` | `KhataReverse`<br>• `reason`: str<br>• `idempotency_key`: str | Reversal entry confirmation | OWNER role |
| **Aging Buckets** | `/api/merchant/khata/aging` | `GET` | None | `{"buckets": {"0_30": paise, "31_60": paise, "61_90": paise, "90_plus": paise}, "total_outstanding_paise": int}` | OWNER role |
| **Statement CSV** | `/api/merchant/khata/accounts/{account_id}/statement.csv` | `GET` | Path: `account_id` | CSV file attachment | OWNER role |

---

## 5. Sarkar AI Retail Copilot Screen (`SarkarCopilotScreen`)

| Action / UI | HTTP Endpoint | Method | Request Payload / Params | Response Fields | Role / Security |
|---|---|---|---|---|---|
| **Ask Sarkar (Text or Voice)** | `/api/merchant/sarkar/ask` | `POST` | `SarkarAsk`<br>• `message`: str<br>• `audio_base64`: opt base64 audio<br>• `mime_type`: opt str | `status`: `"SUCCESS"` \| `"NEEDS_CONFIRMATION"` \| `"NEEDS_CLARIFICATION"`<br>`engine`: str<br>`message`: formatted Markdown / plaintext<br>`data`: structured data tables/cards (stocks, khata, orders)<br>`confirmation`: opt `{action_id, token, summary}`<br>`tool_trace`: list of `{tool, version, correlation_id, arguments, result}`<br>`input`: `{mode, provider, latency_ms}` | STAFF & OWNER (Read)<br>Mutations require OWNER |
| **Confirm Action** | `/api/merchant/sarkar/actions/{action_id}/confirm` | `POST` | Path: `action_id`<br>`SarkarActionConfirm`<br>• `confirmation_token`: str | Execution status `{status: "COMPLETED", message: str}` | OWNER role |
| **List Sarkar Tools** | `/api/merchant/sarkar/tools` | `GET` | None | Available tools metadata & schemas | STAFF & OWNER |

---

## 6. Paytm Soundbox Feed Screen (`SoundboxFeedScreen`)

| Action / UI | HTTP Endpoint | Method | Request Payload / Params | Response Fields | Role / Security |
|---|---|---|---|---|---|
| **Register Sound Device** | `/api/merchant/sound/device` | `POST` | `SoundDeviceRegister`<br>• `device_key`: str (UUID) | `{"device_key": str, "cursor": int, "sound_default": "MUTED"}` | OWNER role |
| **Poll Sound Events** | `/api/merchant/sound/events` | `GET` | Query: `device_key`: str, `limit`: int | `{"events": [{"id", "payment_id", "source_type", "amount_paise", "currency", "verified_at"}], "cursor": int}` | OWNER role |
| **Acknowledge Events** | `/api/merchant/sound/events/ack` | `POST` | `SoundEventAck`<br>• `device_key`: str<br>• `event_id`: int | `{"acknowledged": true, "cursor": int}` | OWNER role |

---

## 7. Catalog & Stock Adjustments

| Action / UI | HTTP Endpoint | Method | Request Payload / Params | Response Fields | Role / Security |
|---|---|---|---|---|---|
| **Add Product** | `/api/merchant/catalog/products` | `POST` | `ProductCreate`<br>• `name`, `category`, `price`, `unit`, `barcode`, `min_stock_alert` | Created product object | OWNER role |
| **Stock Adjustment** | `/api/merchant/catalog/products/{product_id}/stock-adjustments` | `POST` | `StockAdjustment`<br>• `delta`: Decimal<br>• `reason`: str<br>• `idempotency_key`: str | Updated stock record & movement entry | OWNER role |
| **Stock Movements** | `/api/merchant/catalog/movements` | `GET` | Query: `product_id` (opt), `limit` | Stock movement history rows | OWNER role |

---

## 8. Storefront & Online Orders

| Action / UI | HTTP Endpoint | Method | Request Payload / Params | Response Fields | Role / Security |
|---|---|---|---|---|---|
| **List Orders** | `/api/merchant/orders` | `GET` | Query: `status` (opt), `limit` | `{"orders": [{"id", "order_number", "customer_name", "total_paise", "status", "created_at"}]}` | STAFF & OWNER |
| **Fulfill Order** | `/api/merchant/orders/{order_id}/fulfill` | `POST` | Path: `order_id` | Updated order with status `"FULFILLED"` | OWNER role |
| **Storefront QR Info** | `/api/merchant/storefront/qr` | `GET` | None | `{"qr_payload": str, "store_slug": str, "storefront_url": str}` | STAFF & OWNER |
| **Storefront QR Image** | `/api/merchant/storefront/qr.png` | `GET` | None | Raw PNG image stream | STAFF & OWNER |
