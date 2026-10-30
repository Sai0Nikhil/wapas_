from fastapi.testclient import TestClient

from app import auth
from app.config import get_settings
from app.db import session
from app.main import app
from app.merchant_os_models import Product
from app.models import Merchant, Store
from app.inventory import create_product


ORIGIN = "https://merchant.test"


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password},
                       headers={"Origin": ORIGIN})


def test_console_session_binds_tenant_csrf_and_logout(db, monkeypatch):
    monkeypatch.setenv("WAPAS_ENV", "production")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    owner, membership = auth.create_user_membership(
        username="owner-one", password="Secure owner password 2026!",
        merchant_id="merchant_default", store_id="store_default", role="OWNER",
    )
    with session() as s:
        s.add(Merchant(id="merchant_private", name="Private shop"))
        s.add(Store(id="store_private", merchant_id="merchant_private", name="Private store", slug="private-store"))
        s.flush()
        create_product(s, merchant_id="merchant_private", store_id="store_private",
                       product_id="secret-product", name="Secret item", unit="each",
                       unit_price_paise=999, opening_stock=1)
        s.commit()

    client = TestClient(app, base_url=ORIGIN)
    assert "Sign in to your store" in client.get("/").text
    assert client.get("/api/state").status_code == 401

    signed_in = _login(client, owner.username, "Secure owner password 2026!")
    assert signed_in.status_code == 200
    identity = signed_in.json()
    assert identity["merchant_id"] == membership.merchant_id
    assert identity["store_id"] == membership.store_id
    assert identity["store_slug"] == "default-store"
    assert identity["role"] == "OWNER"
    assert "secure" in signed_in.headers.get("set-cookie", "").lower()
    assert client.get("/api/auth/session").json()["authenticated"] is True

    products = client.get("/api/merchant/catalog/products")
    assert products.status_code == 200
    assert "secret-product" not in products.text
    assert client.get("/api/merchant/catalog/products/lookup?product_id=secret-product").status_code == 404

    body = {"name": "Tea", "sku": "TEA-1", "unit": "kg", "unit_price_paise": 1200}
    assert client.post("/api/merchant/catalog/products", json=body,
                       headers={"Origin": ORIGIN}).status_code == 403
    assert client.post("/api/merchant/catalog/products", json=body,
                       headers={"Origin": "https://attacker.test", "X-Wapas-CSRF": identity["csrf_token"]}).status_code == 403
    created = client.post("/api/merchant/catalog/products", json=body,
                          headers={"Origin": ORIGIN, "X-Wapas-CSRF": identity["csrf_token"]})
    assert created.status_code == 201

    logged_out = client.post("/api/auth/logout", headers={
        "Origin": ORIGIN, "X-Wapas-CSRF": identity["csrf_token"],
    })
    assert logged_out.status_code == 204
    assert client.get("/api/auth/session").json() == {"authenticated": False}


def test_staff_membership_is_limited_to_counter_inventory_and_orders(db, monkeypatch):
    monkeypatch.setenv("WAPAS_ENV", "production")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    staff, _membership = auth.create_user_membership(
        username="staff-one", password="Secure staff password 2026!",
        merchant_id="merchant_default", store_id="store_default", role="STAFF",
    )
    client = TestClient(app, base_url=ORIGIN)
    signed_in = _login(client, staff.username, "Secure staff password 2026!")
    assert signed_in.status_code == 200
    csrf = signed_in.json()["csrf_token"]

    assert client.get("/api/merchant/catalog/products").status_code == 200
    assert client.get("/api/merchant/orders").status_code == 200
    assert client.get("/api/state").status_code == 403
    assert client.get("/api/merchant/khata/accounts").status_code == 403
    assert client.post("/api/merchant/bills/bill-example/khata", json={},
                       headers={"Origin": ORIGIN, "X-Wapas-CSRF": csrf}).status_code == 403

    bill = client.post("/api/merchant/bills", json={"idempotency_key": "staff-counter-bill-001"},
                       headers={"Origin": ORIGIN, "X-Wapas-CSRF": csrf})
    assert bill.status_code == 201
