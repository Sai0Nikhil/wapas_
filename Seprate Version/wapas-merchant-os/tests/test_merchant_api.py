from ipaddress import ip_address

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.inventory import create_product
from app.db import session
from app.models import Case, Customer, Merchant, Payment, Store


def _client():
    return TestClient(app, headers={"X-Wapas-Console": "1"})


def test_catalogue_and_stock_api_use_persisted_inventory_service(db):
    c = _client()
    created = c.post("/api/merchant/catalog/products", json={
        "name": "Basmati rice", "category": "Grocery", "sku": "RICE-1", "barcode": "89000001",
        "unit": "kg", "unit_price_paise": 12500, "opening_stock": "5.000",
        "low_stock_threshold": "1.000",
    })
    assert created.status_code == 201
    product = created.json()
    assert product["name"] == "Basmati rice" and product["available"] == "5.000"
    assert product["stock_state"] == "IN_STOCK"

    rows = c.get("/api/merchant/catalog/products").json()
    assert [row["id"] for row in rows] == [product["id"]]
    duplicate = c.post("/api/merchant/catalog/products", json={
        "name": "Duplicate", "sku": "RICE-2", "barcode": "89000001", "unit": "kg",
        "unit_price_paise": 10000,
    })
    assert duplicate.status_code == 409

    change = {"delta": "2.000", "reason": "New delivery", "idempotency_key": "receipt-api-001"}
    first = c.post(f"/api/merchant/catalog/products/{product['id']}/stock-adjustments", json=change)
    second = c.post(f"/api/merchant/catalog/products/{product['id']}/stock-adjustments", json=change)
    assert first.status_code == second.status_code == 200
    assert first.json()["product"]["on_hand"] == second.json()["product"]["on_hand"] == "7.000"
    assert first.json()["movement_id"] == second.json()["movement_id"]
    negative = c.post(f"/api/merchant/catalog/products/{product['id']}/stock-adjustments", json={
        "delta": "-8", "reason": "Incorrect count", "idempotency_key": "bad-adjustment-001",
    })
    assert negative.status_code == 409

    threshold = c.patch(f"/api/merchant/catalog/products/{product['id']}", json={
        "low_stock_threshold": "8.000", "unit_price_paise": 13000,
    })
    assert threshold.status_code == 200
    assert threshold.json()["price_fmt"] == "130.00"
    assert threshold.json()["stock_state"] == "LOW"
    assert c.get("/api/merchant/catalog/movements").json()[0]["id"] == first.json()["movement_id"]


def test_storefront_qr_requires_public_https_verification(db, monkeypatch):
    from app.config import get_settings
    import app.merchant_api as merchant_api
    import qrcode
    import socket

    cfg = get_settings()
    monkeypatch.setattr(cfg, "public_base_url", "http://localhost:8000")
    c = _client()
    rejected = c.post("/api/merchant/storefront/qr/verify")
    assert rejected.status_code == 409
    assert c.get("/api/merchant/storefront/qr").json()["ready"] is False

    monkeypatch.setattr(cfg, "public_base_url", "https://shop.example.com")
    monkeypatch.setattr(merchant_api.socket, "getaddrinfo", lambda host, port, type: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("1.1.1.1", port)),
    ])
    calls = []
    monkeypatch.setattr(merchant_api, "_fetch_public_storefront", lambda *a, **k: (
        calls.append((a, k)), (200, {"store": "Default Store", "store_slug": "default-store", "products": []}),
    )[1])
    original_make = qrcode.make
    encoded = []
    monkeypatch.setattr(qrcode, "make", lambda value, *a, **k: (
        encoded.append(value), original_make(value, *a, **k),
    )[1])
    verified = c.post("/api/merchant/storefront/qr/verify")
    assert verified.status_code == 200
    assert calls[0][0][1:] == ("shop.example.com", 443, [ip_address("1.1.1.1")])
    assert calls[0][1] == {"timeout": 8.0}
    assert verified.json()["ready"] is True
    assert verified.json()["store_url"] == "https://shop.example.com/s/default-store"
    image = c.get("/api/merchant/storefront/qr.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert encoded == ["https://shop.example.com/s/default-store"]
    public_image = c.get("/api/public/stores/default-store/qr.png")
    assert public_image.status_code == 200
    assert public_image.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert encoded[-1] == "https://shop.example.com/s/default-store"


@pytest.mark.parametrize("url", [
    "http://shop.example.com", "https://127.0.0.1", "https://10.1.2.3",
    "https://169.254.10.2", "https://[::1]", "https://[fe80::1]",
    "https://[::1",
    "https://shop.example.com:8443", "https://user:pass@shop.example.com",
])
def test_qr_verification_rejects_local_or_unsafe_url_forms(db, monkeypatch, url):
    from app.config import get_settings
    import app.merchant_api as merchant_api

    monkeypatch.setattr(get_settings(), "public_base_url", url)
    monkeypatch.setattr(merchant_api, "_fetch_public_storefront", lambda *a, **k: pytest.fail("unsafe URL must not be fetched"))
    response = _client().post("/api/merchant/storefront/qr/verify")
    assert response.status_code == 409


def test_qr_verification_rejects_private_dns_redirect_wrong_identity_and_bad_products(db, monkeypatch):
    from app.config import get_settings
    import app.merchant_api as merchant_api
    import socket

    cfg = get_settings()
    client = _client()
    monkeypatch.setattr(cfg, "public_base_url", "https://rebind.example")
    monkeypatch.setattr(merchant_api.socket, "getaddrinfo", lambda host, port, type: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.168.1.4", port)),
    ])
    monkeypatch.setattr(merchant_api, "_fetch_public_storefront", lambda *a, **k: pytest.fail("private resolution must not be fetched"))
    assert client.post("/api/merchant/storefront/qr/verify").status_code == 409

    monkeypatch.setattr(merchant_api.socket, "getaddrinfo", lambda host, port, type: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("1.1.1.1", port)),
    ])
    for code, payload in ((302, {}), (200, {"store": "Other", "store_slug": "wrong", "products": []}),
                          (200, {"store": "Default", "store_slug": "default-store", "products": [{"id": 1}]})):
        monkeypatch.setattr(merchant_api, "_fetch_public_storefront",
                            lambda *a, _code=code, _payload=payload, **k: (_code, _payload))
        assert client.post("/api/merchant/storefront/qr/verify").status_code in (409, 502)


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), OSError("connection refused")])
def test_qr_verification_unreachable_https_endpoint_stays_not_ready(db, monkeypatch, failure):
    from app.config import get_settings
    import app.merchant_api as merchant_api
    import socket

    monkeypatch.setattr(get_settings(), "public_base_url", "https://unreachable.example")
    monkeypatch.setattr(merchant_api.socket, "getaddrinfo", lambda host, port, type: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port)),
    ])
    monkeypatch.setattr(merchant_api, "_fetch_public_storefront", lambda *a, **k: (_ for _ in ()).throw(failure))
    client = _client()
    assert client.post("/api/merchant/storefront/qr/verify").status_code == 502
    status = client.get("/api/merchant/storefront/qr").json()
    assert status["ready"] is False
    assert status["status"] == "NOT_READY"


def test_pinned_https_transport_dials_only_validated_ip_and_keeps_host_sni(monkeypatch):
    import app.merchant_api as merchant_api

    calls = []

    class FakeSocket:
        def close(self):
            pass

        def settimeout(self, _timeout):
            pass

    fake_socket = FakeSocket()

    class FakeTLSContext:
        def wrap_socket(self, raw, *, server_hostname):
            calls.append(("sni", server_hostname))
            return raw

    monkeypatch.setattr(merchant_api.ssl, "create_default_context", lambda: FakeTLSContext())
    monkeypatch.setattr(merchant_api.socket, "create_connection", lambda address, timeout: (
        calls.append(("dial", address, timeout)), fake_socket,
    )[1])
    connection = merchant_api._PinnedHTTPSConnection(
        "shop.example.com", 443, [ip_address("93.184.216.34")], timeout=8,
    )
    try:
        connection.connect()
    finally:
        connection.close()
    assert calls[0][:2] == ("dial", ("93.184.216.34", 443))
    assert 0 < calls[0][2] <= 8
    assert calls[1] == ("sni", "shop.example.com")


def test_catalog_api_scopes_private_mutations_to_default_store(db):
    with session() as s:
        s.add(Merchant(id="merchant_other", name="Other"))
        s.add(Store(id="store_other", merchant_id="merchant_other", name="Other Store", slug="other-store"))
        s.flush()
        create_product(s, merchant_id="merchant_other", store_id="store_other",
                       product_id="private-product", name="Private", unit="each",
                       unit_price_paise=100, sku="private")
        s.add(Customer(id="other-customer", merchant_id="merchant_other", name="Private Customer",
                       phone="9000000011"))
        s.add(Payment(id="other-payment", merchant_id="merchant_other", order_id="OTHER-ORDER",
                      customer_id="other-customer", amount_paise=500, bank="Bank A", status="FAILED"))
        s.add(Case(id="other-case", merchant_id="merchant_other", payment_id="other-payment"))
        s.commit()
    c = _client()
    assert c.get("/api/merchant/catalog/products").json() == []
    assert c.patch("/api/merchant/catalog/products/private-product", json={"name": "Changed"}).status_code == 404
    assert c.post("/api/merchant/catalog/products/private-product/stock-adjustments", json={
        "delta": "1", "reason": "test", "idempotency_key": "private-adjustment-01",
    }).status_code == 404
    assert all(row["id"] != "other-case" for row in c.get("/api/state").json()["cases"])
    assert c.get("/api/cases/other-case").status_code == 404

    via_tunnel = {"X-Forwarded-For": "203.0.113.9", "X-Wapas-Console": "1"}
    assert c.get("/api/merchant/catalog/products", headers=via_tunnel).status_code == 401


def test_counter_api_creates_server_priced_issued_bill_without_claiming_payment(db):
    c = _client()
    product = c.post("/api/merchant/catalog/products", json={
        "name": "Tea", "sku": "TEA-1", "unit": "kg", "unit_price_paise": 10001,
        "opening_stock": "4.000",
    }).json()
    created = c.post("/api/merchant/bills", json={"idempotency_key": "counter-bill-api-01"})
    assert created.status_code == 201
    bill = created.json()
    assert c.post("/api/merchant/bills", json={"idempotency_key": "counter-bill-api-01"}).json()["id"] == bill["id"]

    changed = c.put(f"/api/merchant/bills/{bill['id']}/lines/{product['id']}", json={"quantity": "1.5"})
    assert changed.status_code == 200
    assert changed.json()["subtotal_paise"] == 15002
    assert changed.json()["payment_state"] == "NOT_RECORDED"

    issued = c.post(f"/api/merchant/bills/{bill['id']}/issue")
    assert issued.status_code == 200
    assert issued.json()["state"] == "ISSUED"
    assert issued.json()["payment_state"] == "NOT_RECORDED"
    stock_after_issue = c.get("/api/merchant/catalog/products").json()[0]
    assert stock_after_issue["available"] == "2.500" and stock_after_issue["reserved"] == "1.500"
    assert c.post(f"/api/merchant/bills/{bill['id']}/issue").json()["state"] == "ISSUED"
    assert c.put(f"/api/merchant/bills/{bill['id']}/lines/{product['id']}", json={"quantity": "2"}).status_code == 409
    assert c.get(f"/api/merchant/bills/{bill['id']}").json()["total_paise"] == 15002


def test_issued_counter_cancellation_releases_stock_but_pending_payment_blocks_void(db):
    c = _client()
    product = c.post("/api/merchant/catalog/products", json={
        "name": "Oil", "sku": "OIL-1", "unit": "litre", "unit_price_paise": 3000,
        "opening_stock": "3",
    }).json()
    bill = c.post("/api/merchant/bills", json={"idempotency_key": "counter-void-bill-01"}).json()
    bill = c.put(f"/api/merchant/bills/{bill['id']}/lines/{product['id']}", json={"quantity": "2"}).json()
    bill = c.post(f"/api/merchant/bills/{bill['id']}/issue").json()
    assert c.get("/api/merchant/catalog/products").json()[0]["available"] == "1.000"

    void_bill = c.post("/api/merchant/bills", json={"idempotency_key": "counter-void-bill-02"}).json()
    void_bill = c.put(f"/api/merchant/bills/{void_bill['id']}/lines/{product['id']}", json={"quantity": "1"}).json()
    void_bill = c.post(f"/api/merchant/bills/{void_bill['id']}/issue").json()
    assert c.get("/api/merchant/catalog/products").json()[0]["available"] == "0.000"
    cancelled = c.post(f"/api/merchant/bills/{void_bill['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "CANCELLED"
    stock = c.get("/api/merchant/catalog/products").json()[0]
    assert stock["available"] == "1.000" and stock["reserved"] == "2.000"

    pending = c.post(f"/api/merchant/bills/{bill['id']}/payments", json={"idempotency_key": "counter-void-link-01"})
    assert pending.status_code == 200
    blocked = c.post(f"/api/merchant/bills/{bill['id']}/cancel")
    assert blocked.status_code == 409
    assert c.get("/api/merchant/catalog/products").json()[0]["reserved"] == "2.000"


def test_counter_payment_link_is_idempotent_and_fake_settlement_is_simulated(db):
    from urllib.parse import urlsplit
    from app.gateway import get_gateway
    from app.payment_lifecycle import apply_terminal_result
    from app.billing_models import Bill
    from app.sound_models import SoundEvent
    from sqlmodel import select

    c = _client()
    product = c.post("/api/merchant/catalog/products", json={
        "name": "Soap", "sku": "SOAP-1", "unit": "each", "unit_price_paise": 2500,
        "opening_stock": "2",
    }).json()
    bill = c.post("/api/merchant/bills", json={
        "idempotency_key": "counter-link-bill-01", "customer_name": "Ramesh", "customer_phone": "9000000011",
    }).json()
    bill = c.put(f"/api/merchant/bills/{bill['id']}/lines/{product['id']}", json={"quantity": "1"}).json()
    bill = c.post(f"/api/merchant/bills/{bill['id']}/issue").json()

    first = c.post(f"/api/merchant/bills/{bill['id']}/payments", json={"idempotency_key": "counter-link-key-01"})
    assert first.status_code == 200
    payload = first.json()
    assert payload["mode"] == "SIMULATED" and payload["status"] == "PENDING"
    assert payload["checkout_url"].endswith("/pay/" + urlsplit(payload["checkout_url"]).path.rsplit("/", 1)[-1])
    retry = c.post(f"/api/merchant/bills/{bill['id']}/payments", json={"idempotency_key": "counter-link-key-02"})
    assert retry.status_code == 200
    assert retry.json()["payment_id"] == payload["payment_id"]
    assert retry.json()["checkout_url"] == payload["checkout_url"]
    gateway = get_gateway()
    assert len(gateway.links) == 1

    link_id = urlsplit(payload["checkout_url"]).path.rsplit("/", 1)[-1]
    assert gateway.pay(link_id)
    status = gateway.link_status(link_id)
    with session() as s:
        payment = s.get(Payment, payload["payment_id"])
        assert apply_terminal_result(s, payment, status, gateway_name="fake", expected_link_id=link_id) == "SIMULATED"
        s.commit()
        saved_bill = s.get(Bill, bill["id"])
        assert saved_bill.payment_state == "SIMULATED"
        assert s.get(Payment, payload["payment_id"]).status == "SIMULATED"
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id == payload["payment_id"])).all() == []


def test_fake_khata_collection_does_not_record_a_ledger_repayment(db):
    from urllib.parse import urlsplit
    from app.gateway import get_gateway
    from app.khata import account_history
    from app.payment_lifecycle import apply_terminal_result
    from app.sound_models import SoundEvent
    from sqlmodel import select

    c = _client()
    product = c.post("/api/merchant/catalog/products", json={
        "name": "Rice", "sku": "RICE-1", "unit": "kg", "unit_price_paise": 5000,
        "opening_stock": "2",
    }).json()
    bill = c.post("/api/merchant/bills", json={
        "idempotency_key": "khata-link-bill-01", "customer_name": "Sita", "customer_phone": "9000000012",
    }).json()
    bill = c.put(f"/api/merchant/bills/{bill['id']}/lines/{product['id']}", json={"quantity": "1"}).json()
    bill = c.post(f"/api/merchant/bills/{bill['id']}/issue").json()
    added = c.post(f"/api/merchant/bills/{bill['id']}/khata", json={})
    assert added.status_code == 200
    account_id = added.json()["account"]["id"]
    initial_balance = added.json()["account"]["outstanding_paise"]
    requested = c.post(f"/api/merchant/khata/accounts/{account_id}/payment-links", json={
        "amount_paise": initial_balance, "idempotency_key": "khata-link-key-0001",
    })
    assert requested.status_code == 200
    payload = requested.json()
    assert payload["mode"] == "SIMULATED" and payload["checkout_url"]
    gateway = get_gateway()
    link_id = urlsplit(payload["checkout_url"]).path.rsplit("/", 1)[-1]
    assert gateway.pay(link_id)
    status = gateway.link_status(link_id)
    with session() as s:
        payment = s.get(Payment, payload["payment_id"])
        assert apply_terminal_result(s, payment, status, gateway_name="fake", expected_link_id=link_id) == "SIMULATED"
        account, _customer, _entries, current_balance = account_history(
            s, merchant_id="merchant_default", store_id="store_default", account_id=account_id,
        )
        assert current_balance == initial_balance
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id == payload["payment_id"])).all() == []
