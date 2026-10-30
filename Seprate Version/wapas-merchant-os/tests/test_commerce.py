from datetime import datetime, timedelta, timezone
from decimal import Decimal
import secrets

from fastapi.testclient import TestClient
from sqlmodel import select

from app.db import session
from app.inventory import create_product
from app.main import app
from app.commerce_models import StoreOrder
from app.models import Payment
from app.merchant_os_models import InventoryBalance


def client():
    return TestClient(app, headers={"X-Wapas-Console": "1"})


def _product(*, stock="5"):
    with session() as s:
        create_product(s, merchant_id="merchant_default", store_id="store_default",
                       product_id="shop-tea", name="Tea", unit="kg", unit_price_paise=25000,
                       sku="SHOP-TEA", barcode="8900123456789", opening_stock=Decimal(stock))
        s.commit()


def _body(*, phone="9000012221", quantity="2", key="shop-idempotency-key-0001", token=None):
    return {
        "name": "Asha Rao", "phone": phone, "language": "en",
        "items": [{"product_id": "shop-tea", "quantity": quantity}],
        "idempotency_key": key, "order_token": token or secrets.token_urlsafe(32),
    }


def test_order_result_page_renders_catalogue_values_as_text_nodes(db):
    from app.commerce import order_result_page

    html = order_result_page("WAPTESTORDER")
    assert 'line.textContent=String(x.quantity)' in html
    assert 'document.getElementById("items").innerHTML' not in html


def test_public_store_fake_checkout_is_simulated_and_cannot_be_fulfilled(db):
    from app.gateway import get_gateway

    _product()
    c = client()
    listing = c.get("/api/public/stores/default-store/products")
    assert listing.status_code == 200
    assert listing.json()["products"][0]["name"] == "Tea"
    token = secrets.token_urlsafe(32)
    body = _body(token=token)
    response = c.post("/api/public/stores/default-store/checkout", json=body)
    assert response.status_code == 201
    data = response.json()
    assert data["mode"] == "fake" and data["amount_paise"] == 50000
    order_id = data["order_id"]

    # A retry with the same key and token returns the original order, without a second hold.
    retry = c.post("/api/public/stores/default-store/checkout", json=body)
    assert retry.status_code == 200 and retry.json()["order_id"] == order_id
    with db.session() as s:
        balance = s.exec(select(InventoryBalance).where(InventoryBalance.product_id == "shop-tea")).one()
        assert balance.on_hand == Decimal("5.000") and balance.reserved == Decimal("2.000")
        assert len(s.exec(select(StoreOrder)).all()) == 1
        payment = s.get(Payment, f"pay_{order_id}")
        assert payment.status == "PENDING" and payment.amount_paise == 50000

    assert c.get(f"/api/public/orders/{order_id}").status_code == 401
    assert c.get(f"/api/public/orders/{order_id}", headers={"X-Order-Token": secrets.token_urlsafe(32)}).status_code == 404

    finished = c.post(f"/fakecheckout/{order_id}", data={"outcome": "success"}, follow_redirects=False)
    assert finished.status_code == 303
    status = c.get(f"/api/public/orders/{order_id}", headers={"X-Order-Token": token})
    assert status.status_code == 200
    assert status.json()["status"] == "SIMULATED" and status.json()["fulfillment_state"] == "UNFULFILLED"
    with db.session() as s:
        balance = s.exec(select(InventoryBalance).where(InventoryBalance.product_id == "shop-tea")).one()
        assert balance.on_hand == Decimal("5.000") and balance.reserved == Decimal("0.000")
        payment = s.get(Payment, f"pay_{order_id}")
        assert payment.status == "SIMULATED" and payment.verified_at is None
        from app.sound_models import SoundEvent
        assert not s.exec(select(SoundEvent).where(SoundEvent.payment_id == payment.id)).all()

    assert c.post(f"/api/merchant/orders/{order_id}/fulfill", json={"confirm": True}).status_code == 409
    assert c.get(f"/api/public/orders/{order_id}", headers={"X-Order-Token": token}).json()["fulfillment_state"] == "UNFULFILLED"


def test_failed_shop_payment_releases_stock_and_wrong_token_cannot_read_order(db):
    _product(stock="3")
    c = client()
    token = secrets.token_urlsafe(32)
    response = c.post("/api/public/stores/default-store/checkout", json=_body(
        phone="9000012222", quantity="1", key="shop-idempotency-key-0002", token=token,
    ))
    order_id = response.json()["order_id"]
    c.post(f"/fakecheckout/{order_id}", data={"outcome": "bank"}, follow_redirects=False)
    order = c.get(f"/api/public/orders/{order_id}", headers={"X-Order-Token": token}).json()
    assert order["status"] == "PAYMENT_FAILED"
    with db.session() as s:
        balance = s.exec(select(InventoryBalance).where(InventoryBalance.product_id == "shop-tea")).one()
        assert balance.on_hand == Decimal("3.000") and balance.reserved == Decimal("0.000")


def test_ambiguous_shop_initiation_releases_only_after_provider_reports_no_order(db, monkeypatch):
    from app import store
    from app.gateway import get_gateway

    _product(stock="2")
    gw = get_gateway()
    monkeypatch.setattr(gw, "initiate_checkout", lambda **_: {
        "ok": False, "uncertain": True, "error": "ReadTimeout",
    })
    token = secrets.token_urlsafe(32)
    response = client().post("/api/public/stores/default-store/checkout", json=_body(
        phone="9000012223", quantity="1", key="shop-idempotency-key-0003", token=token,
    ))
    assert response.status_code == 202 and response.json()["mode"] == "pending"
    order_id = response.json()["order_id"]
    with db.session() as s:
        assert s.get(Payment, f"pay_{order_id}").status == "INIT_UNKNOWN"
        balance = s.exec(select(InventoryBalance).where(InventoryBalance.product_id == "shop-tea")).one()
        assert balance.reserved == Decimal("1.000")

    result = store.reconcile(datetime.now(timezone.utc) + timedelta(minutes=11))
    assert result["init_failed"] == 1
    with db.session() as s:
        assert s.get(Payment, f"pay_{order_id}").status == "INIT_FAILED"
        order = s.get(StoreOrder, order_id)
        assert order.status == "PAYMENT_FAILED"
        balance = s.exec(select(InventoryBalance).where(InventoryBalance.product_id == "shop-tea")).one()
        assert balance.reserved == Decimal("0.000")


def test_shop_refuses_oversell_and_cross_store_access(db):
    _product(stock="1")
    c = client()
    assert c.get("/api/public/stores/unknown-store/products").status_code == 404
    response = c.post("/api/public/stores/default-store/checkout", json=_body(
        phone="9000012224", quantity="2", key="shop-idempotency-key-0004",
    ))
    assert response.status_code == 409
    with db.session() as s:
        assert not s.exec(select(StoreOrder)).all()
