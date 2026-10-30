from decimal import Decimal
import hashlib
import hmac
from datetime import datetime, timezone
from fastapi.testclient import TestClient
import pytest
from sqlmodel import select

from app import auth, billing, inventory, khata
from app.config import get_settings
from app.db import session
from app.main import app
from app.merchant_os_models import Product
from app.models import Customer, Merchant, Payment, Store
from app.commerce_models import StoreOrder
from app.khata_models import KhataAccount, KhataLedgerEntry
from app.sound_models import SoundDevice, SoundEvent
from app.sarkar_models import SarkarAction

ORIGIN = "https://merchant.test"


def _create_merchant_fixtures(s, merchant_id: str, store_id: str, slug: str, prefix: str):
    m = Merchant(id=merchant_id, name=f"Merchant {prefix}")
    st = Store(id=store_id, merchant_id=merchant_id, name=f"Store {prefix}", slug=slug)
    s.add(m)
    s.add(st)
    s.flush()

    # Product
    prod = inventory.create_product(
        s, merchant_id=merchant_id, store_id=store_id,
        product_id=f"prod_{prefix}", name=f"Product {prefix}",
        sku=f"SKU-{prefix}", unit="each", unit_price_paise=1500, opening_stock=Decimal("10"),
    )

    # Customer
    cust = Customer(
        id=f"cust_{prefix}", merchant_id=merchant_id, name=f"Customer {prefix}",
        phone=f"987654321{1 if prefix=='A' else 2}",
    )
    s.add(cust)
    s.flush()

    # Bill
    bill = billing.create_draft(
        s, merchant_id=merchant_id, store_id=store_id,
        idempotency_key=f"bill-draft-{prefix}", customer_name=cust.name,
        customer_phone=cust.phone,
    )
    billing.set_line(s, merchant_id=merchant_id, store_id=store_id, bill_id=bill.id,
                     product_id=prod.id, quantity="2")
    billing.issue_bill(s, merchant_id=merchant_id, store_id=store_id, bill_id=bill.id)

    # Khata Account & Entry
    acc, entry = khata.add_bill_to_khata(
        s, merchant_id=merchant_id, store_id=store_id, bill_id=bill.id,
    )

    # Store Order
    token_raw = f"order_token_for_{prefix}_123456789012345678901234567890"
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    order = StoreOrder(
        id=f"order_{prefix}", merchant_id=merchant_id, store_id=store_id,
        customer_id=cust.id, idempotency_key=f"order-idemp-{prefix}",
        token_hash=token_hash, status="PAID", fulfillment_state="UNFULFILLED",
        amount_paise=3000,
    )
    s.add(order)

    # Payment
    payment = Payment(
        id=f"pay_{prefix}", merchant_id=merchant_id, store_id=store_id,
        order_id=order.id, customer_id=cust.id, amount_paise=3000,
        source_type="SHOP_ORDER", source_id=order.id, provider="paytm",
        provider_mid="MID-TEST", provider_order_id=order.id,
        bank="UPI", method="UPI", status="SUCCESS", verified_at=datetime.now(timezone.utc),
    )
    s.add(payment)
    order.payment_id = payment.id

    # Sound Device
    dev = SoundDevice(
        merchant_id=merchant_id, store_id=store_id,
        device_key=f"device_{prefix}_12345678901234567890",
    )
    s.add(dev)

    # Sarkar Action
    action = SarkarAction(
        id=f"action_{prefix}_1234567890", merchant_id=merchant_id, store_id=store_id,
        actor_id=f"user_{prefix}", session_hash="sessionhash123", action_type="stock_receipt",
        payload_json='{"product_id":"' + prod.id + '","quantity":"1","unit":"each","reason":"Restock"}',
        payload_hash=hashlib.sha256(b'{"product_id":"' + prod.id.encode() + b'","quantity":"1","unit":"each","reason":"Restock"}').hexdigest(),
        confirmation_hash=hashlib.sha256(b"secret-token-123").hexdigest(),
        status="OPEN",
        expires_at=datetime.now(timezone.utc),
    )
    s.add(action)
    s.commit()

    return {
        "product": prod, "customer": cust, "bill": bill, "account": acc,
        "entry": entry, "order": order, "token_raw": token_raw,
        "payment": payment, "device": dev, "action": action,
    }


def _login_client(username, password, origin=ORIGIN):
    client = TestClient(app, base_url=origin)
    res = client.post("/api/auth/login", json={"username": username, "password": password},
                      headers={"Origin": origin})
    assert res.status_code == 200, res.text
    data = res.json()
    csrf = data["csrf_token"]
    headers = {"Origin": origin, "X-Wapas-CSRF": csrf}
    return client, headers, data


@pytest.fixture
def tenancy_setup(db, monkeypatch):
    monkeypatch.setenv("WAPAS_ENV", "production")
    monkeypatch.setattr(get_settings(), "app_env", "production")

    with session() as s:
        fixtures_a = _create_merchant_fixtures(s, "merchant_alpha", "store_alpha", "store-alpha", "A")
        fixtures_b = _create_merchant_fixtures(s, "merchant_beta", "store_beta", "store-beta", "B")

    owner_a, _mbr_oa = auth.create_user_membership(
        username="owner_alpha", password="Alpha owner password 2026!",
        merchant_id="merchant_alpha", store_id="store_alpha", role="OWNER",
    )
    staff_a, _mbr_sa = auth.create_user_membership(
        username="staff_alpha", password="Alpha staff password 2026!",
        merchant_id="merchant_alpha", store_id="store_alpha", role="STAFF",
    )
    owner_b, _mbr_ob = auth.create_user_membership(
        username="owner_beta", password="Beta owner password 2026!",
        merchant_id="merchant_beta", store_id="store_beta", role="OWNER",
    )
    staff_b, _mbr_sb = auth.create_user_membership(
        username="staff_beta", password="Beta staff password 2026!",
        merchant_id="merchant_beta", store_id="store_beta", role="STAFF",
    )

    return {
        "fixtures_a": fixtures_a, "fixtures_b": fixtures_b,
        "users": {
            "owner_a": ("owner_alpha", "Alpha owner password 2026!"),
            "staff_a": ("staff_alpha", "Alpha staff password 2026!"),
            "owner_b": ("owner_beta", "Beta owner password 2026!"),
            "staff_b": ("staff_beta", "Beta staff password 2026!"),
        },
    }


def test_cross_merchant_catalogue_and_stock_attacks(tenancy_setup):
    u = tenancy_setup["users"]
    client_a, headers_a, _ = _login_client(*u["owner_a"])
    prod_b = tenancy_setup["fixtures_b"]["product"]

    # Merchant A cannot see Merchant B's product in list
    list_res = client_a.get("/api/merchant/catalog/products")
    assert list_res.status_code == 200
    product_ids = [p["id"] for p in list_res.json()]
    assert prod_b.id not in product_ids

    # Merchant A cannot lookup Merchant B's product
    lookup_res = client_a.get(f"/api/merchant/catalog/products/lookup?product_id={prod_b.id}")
    assert lookup_res.status_code == 404

    # Merchant A cannot update Merchant B's product
    patch_res = client_a.patch(f"/api/merchant/catalog/products/{prod_b.id}",
                               json={"unit_price_paise": 99999}, headers=headers_a)
    assert patch_res.status_code == 404

    # Merchant A cannot adjust stock on Merchant B's product
    adjust_res = client_a.post(f"/api/merchant/catalog/products/{prod_b.id}/stock-adjustments",
                               json={"delta": "5", "reason": "Attack adjust", "idempotency_key": "att-adj-1"},
                               headers=headers_a)
    assert adjust_res.status_code == 404


def test_cross_merchant_counter_billing_attacks(tenancy_setup):
    u = tenancy_setup["users"]
    client_a, headers_a, _ = _login_client(*u["owner_a"])
    bill_b = tenancy_setup["fixtures_b"]["bill"]
    prod_b = tenancy_setup["fixtures_b"]["product"]
    prod_a = tenancy_setup["fixtures_a"]["product"]
    bill_a = tenancy_setup["fixtures_a"]["bill"]

    # Merchant A cannot read Merchant B's bill
    assert client_a.get(f"/api/merchant/bills/{bill_b.id}").status_code == 404

    # Merchant A cannot add line to Merchant B's bill
    assert client_a.put(f"/api/merchant/bills/{bill_b.id}/lines/{prod_a.id}",
                        json={"quantity": "1"}, headers=headers_a).status_code in (404, 409)

    # Merchant A cannot add Merchant B's product to Merchant A's draft bill
    draft_a = client_a.post("/api/merchant/bills", json={"idempotency_key": "draft-attack-1"},
                            headers=headers_a).json()
    add_cross_prod = client_a.put(f"/api/merchant/bills/{draft_a['id']}/lines/{prod_b.id}",
                                  json={"quantity": "1"}, headers=headers_a)
    assert add_cross_prod.status_code == 409

    # Merchant A cannot issue Merchant B's bill
    assert client_a.post(f"/api/merchant/bills/{bill_b.id}/issue", headers=headers_a).status_code in (404, 409)

    # Merchant A cannot cancel Merchant B's bill
    assert client_a.post(f"/api/merchant/bills/{bill_b.id}/cancel", headers=headers_a).status_code in (404, 409)

    # Merchant A cannot request payment link on Merchant B's bill
    assert client_a.post(f"/api/merchant/bills/{bill_b.id}/payments",
                         json={"idempotency_key": "att-pay-1234567890"}, headers=headers_a).status_code in (404, 409)

    # Merchant A cannot transfer Merchant B's bill to Khata
    assert client_a.post(f"/api/merchant/bills/{bill_b.id}/khata", json={}, headers=headers_a).status_code in (404, 409)


def test_cross_merchant_khata_attacks(tenancy_setup):
    u = tenancy_setup["users"]
    client_a, headers_a, _ = _login_client(*u["owner_a"])
    acc_b = tenancy_setup["fixtures_b"]["account"]
    entry_b = tenancy_setup["fixtures_b"]["entry"]

    # Merchant A cannot list Merchant B's Khata account
    accounts_res = client_a.get("/api/merchant/khata/accounts")
    assert accounts_res.status_code == 200
    account_ids = [a["id"] for a in accounts_res.json()]
    assert acc_b.id not in account_ids

    # Merchant A cannot view Merchant B's Khata account details
    assert client_a.get(f"/api/merchant/khata/accounts/{acc_b.id}").status_code == 404

    # Merchant A cannot record repayment on Merchant B's Khata account
    repay_res = client_a.post(f"/api/merchant/khata/accounts/{acc_b.id}/repayments", json={
        "amount_paise": 1000, "method": "CASH", "idempotency_key": "att-repay-1",
        "confirm_received": True, "note": "Fraud repayment",
    }, headers=headers_a)
    assert repay_res.status_code in (404, 409)

    # Merchant A cannot request online collection on Merchant B's Khata account
    coll_res = client_a.post(f"/api/merchant/khata/accounts/{acc_b.id}/payment-links", json={
        "amount_paise": 1000, "idempotency_key": "att-coll-1234567890",
    }, headers=headers_a)
    assert coll_res.status_code in (404, 409)

    # Merchant A cannot reverse Merchant B's ledger entry
    rev_res = client_a.post(f"/api/merchant/khata/entries/{entry_b.id}/reverse", json={
        "reason": "Unauthorized reversal",
    }, headers=headers_a)
    assert rev_res.status_code in (404, 409)


def test_cross_merchant_shop_order_and_token_attacks(tenancy_setup):
    u = tenancy_setup["users"]
    client_a, headers_a, _ = _login_client(*u["owner_a"])
    order_b = tenancy_setup["fixtures_b"]["order"]
    token_raw_a = tenancy_setup["fixtures_a"]["token_raw"]
    token_raw_b = tenancy_setup["fixtures_b"]["token_raw"]

    # Merchant A cannot view Merchant B's order in list
    orders_res = client_a.get("/api/merchant/orders")
    assert orders_res.status_code == 200
    order_ids = [o["id"] for o in orders_res.json()]
    assert order_b.id not in order_ids

    # Merchant A cannot fulfill Merchant B's order
    fulfill_res = client_a.post(f"/api/merchant/orders/{order_b.id}/fulfill",
                                json={"confirm": True}, headers=headers_a)
    assert fulfill_res.status_code == 404

    # Public endpoint: Customer with Token A cannot read Order B (fails safe with 404)
    public_client = TestClient(app)
    bad_token_res = public_client.get(f"/api/public/orders/{order_b.id}",
                                      headers={"X-Order-Token": token_raw_a})
    assert bad_token_res.status_code == 404

    # Public endpoint: Correct token reads Order B
    good_token_res = public_client.get(f"/api/public/orders/{order_b.id}",
                                       headers={"X-Order-Token": token_raw_b})
    assert good_token_res.status_code == 200
    assert good_token_res.json()["order_id"] == order_b.id


def test_cross_merchant_sound_device_and_events_attacks(tenancy_setup):
    u = tenancy_setup["users"]
    client_a, headers_a, _ = _login_client(*u["owner_a"])
    dev_b = tenancy_setup["fixtures_b"]["device"]

    # Merchant A cannot poll events for Merchant B's device key
    poll_res = client_a.get("/api/merchant/sound/events", params={"device_key": dev_b.device_key})
    assert poll_res.status_code == 404

    # Merchant A cannot acknowledge Merchant B's device key
    ack_res = client_a.post("/api/merchant/sound/events/ack", json={
        "device_key": dev_b.device_key, "event_ids": [1, 2, 3],
    }, headers=headers_a)
    assert ack_res.status_code == 404


def test_cross_merchant_sarkar_tool_arguments_attacks(tenancy_setup):
    u = tenancy_setup["users"]
    client_a, headers_a, _ = _login_client(*u["owner_a"])
    acc_b = tenancy_setup["fixtures_b"]["account"]
    pay_b = tenancy_setup["fixtures_b"]["payment"]
    action_b = tenancy_setup["fixtures_b"]["action"]

    # inspect_khata_history for Merchant B's account returns 404
    kh_res = client_a.post("/api/merchant/sarkar/tools/inspect_khata_history",
                           json={"arguments": {"account_id": acc_b.id}}, headers=headers_a)
    assert kh_res.status_code == 404

    # explain_payment_state for Merchant B's payment returns 404
    exp_res = client_a.post("/api/merchant/sarkar/tools/explain_payment_state",
                            json={"arguments": {"payment_id": pay_b.id}}, headers=headers_a)
    assert exp_res.status_code == 404

    # confirm_stock_receipt for Merchant B's action returns 404
    conf_res = client_a.post(f"/api/merchant/sarkar/actions/{action_b.id}/confirm",
                             json={"confirmation_token": "secret-token-1234567890"}, headers=headers_a)
    assert conf_res.status_code == 404


def test_role_rbac_staff_cannot_escalate_to_owner(tenancy_setup):
    u = tenancy_setup["users"]
    client_staff, headers_staff, _ = _login_client(*u["staff_a"])
    acc_a = tenancy_setup["fixtures_a"]["account"]
    bill_a = tenancy_setup["fixtures_a"]["bill"]
    entry_a = tenancy_setup["fixtures_a"]["entry"]
    act_a = tenancy_setup["fixtures_a"]["action"]

    # Staff forbidden from Khata accounts
    assert client_staff.get("/api/merchant/khata/accounts").status_code == 403
    assert client_staff.get(f"/api/merchant/khata/accounts/{acc_a.id}").status_code == 403
    assert client_staff.post(f"/api/merchant/khata/accounts/{acc_a.id}/repayments",
                             json={"amount_paise": 100, "method": "CASH", "idempotency_key": "k1",
                                   "confirm_received": True}, headers=headers_staff).status_code == 403
    assert client_staff.post(f"/api/merchant/bills/{bill_a.id}/khata",
                             json={}, headers=headers_staff).status_code == 403
    assert client_staff.post(f"/api/merchant/khata/entries/{entry_a.id}/reverse",
                             json={"reason": "test"}, headers=headers_staff).status_code == 403

    # Staff forbidden from owner console operations
    assert client_staff.get("/api/state").status_code == 403
    assert client_staff.get("/api/integrations").status_code == 403
    assert client_staff.get("/api/proof").status_code == 403
    assert client_staff.get("/api/merchant/opportunities/pulse").status_code == 403
    assert client_staff.get("/api/merchant/storefront/qr").status_code == 403

    # Staff forbidden from Sarkar owner tools
    assert client_staff.post("/api/merchant/sarkar/tools/inspect_khata",
                             json={"arguments": {}}, headers=headers_staff).status_code == 403
    assert client_staff.post("/api/merchant/sarkar/tools/prepare_stock_receipt",
                             json={"arguments": {"message": "received 1 kg rice"}}, headers=headers_staff).status_code == 403
    assert client_staff.post(f"/api/merchant/sarkar/actions/{act_a.id}/confirm",
                             json={"confirmation_token": "token"}, headers=headers_staff).status_code == 403


def test_cross_site_and_csrf_attacks_blocked(tenancy_setup):
    u = tenancy_setup["users"]
    client_a, headers_a, data_a = _login_client(*u["owner_a"])

    # Missing CSRF header on mutation
    no_csrf = client_a.post("/api/merchant/catalog/products",
                            json={"name": "Tea", "sku": "TEA-X", "unit_price_paise": 100},
                            headers={"Origin": ORIGIN})
    assert no_csrf.status_code == 403

    # Forged CSRF header
    bad_csrf = client_a.post("/api/merchant/catalog/products",
                             json={"name": "Tea", "sku": "TEA-X", "unit_price_paise": 100},
                             headers={"Origin": ORIGIN, "X-Wapas-CSRF": "forged_csrf_token_12345"})
    assert bad_csrf.status_code == 403

    # Cross-site origin
    cross_origin = client_a.post("/api/merchant/catalog/products",
                                json={"name": "Tea", "sku": "TEA-X", "unit_price_paise": 100},
                                headers={"Origin": "https://evil-attacker.com", "X-Wapas-CSRF": data_a["csrf_token"]})
    assert cross_origin.status_code == 403

    # Sec-Fetch-Site cross-site
    cross_site = client_a.post("/api/merchant/catalog/products",
                               json={"name": "Tea", "sku": "TEA-X", "unit_price_paise": 100},
                               headers={"Origin": ORIGIN, "X-Wapas-CSRF": data_a["csrf_token"],
                                        "Sec-Fetch-Site": "cross-site"})
    assert cross_site.status_code == 403
