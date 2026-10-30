from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlmodel import select

from app import payment_events
from app import billing, khata
from app.inventory import create_product
from app.payment_lifecycle import apply_terminal_result
from app.config import get_settings
from app.db import session
from app.main import app
from app.models import Customer, Payment
from app.ports import PayStatus, StatusResult
from app.sound_models import SoundEvent


def _verified_result(order_id):
    return StatusResult(
        status=PayStatus.SUCCESS, txn_id="TXN-" + order_id, amount_paise=1234,
        raw={"mid": "MID-SOUND", "orderId": order_id, "txnId": "TXN-" + order_id,
             "txnAmount": "12.34", "currency": "INR"},
    )


def _record_paytm_success(s, customer_id, payment_id, order_id):
    payment = Payment(
        id=payment_id, merchant_id="merchant_default", store_id="store_default",
        order_id=order_id, customer_id=customer_id, amount_paise=1234,
        source_type="SHOP_ORDER", source_id=order_id, provider="paytm", provider_mid="MID-SOUND",
        provider_order_id=order_id, idempotency_key="test-payment:" + payment_id,
        bank="", method="", status="PENDING",
    )
    s.add(payment)
    s.flush()
    assert payment_events.record_verified_success(
        s, payment, _verified_result(order_id), gateway_name="paytm", expected_order_id=order_id,
    )
    return payment


def test_verified_paytm_outbox_is_idempotent_and_new_devices_do_not_replay_history(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "paytm_mid", "MID-SOUND")
    with session() as s:
        customer = s.exec(select(Customer).where(Customer.merchant_id == "merchant_default")).first()
        first = _record_paytm_success(s, customer.id, "payment-sound-1", "ORDER-SOUND-1")
        assert payment_events.record_verified_success(
            s, first, _verified_result("ORDER-SOUND-1"), gateway_name="paytm",
            expected_order_id="ORDER-SOUND-1",
        )
        s.commit()
        assert len(s.exec(select(SoundEvent).where(SoundEvent.payment_id == first.id)).all()) == 1

    client = TestClient(app, base_url="http://merchant.test", headers={"X-Wapas-Console": "1"})
    device_key = "device_test_12345678901234567890"
    registered = client.post("/api/merchant/sound/device", json={"device_key": device_key})
    assert registered.status_code == 200
    assert registered.json()["sound_default"] == "MUTED"
    assert client.get("/api/merchant/sound/events", params={"device_key": device_key}).json()["events"] == []


def test_sound_device_cursors_and_acknowledgements_are_store_scoped(db, monkeypatch):
    from app import auth
    from app.models import Merchant, Store
    from app.sound_models import SoundDevice

    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "paytm_mid", "MID-SOUND")

    with session() as s:
        s.add(Merchant(id="merchant_other", name="Other Merchant"))
        s.add(Store(id="store_other", merchant_id="merchant_other", name="Other Store", slug="other-store"))
        customer = Customer(id="other-sound-customer", merchant_id="merchant_other", name="Private", phone="9000000022")
        payment = Payment(id="other-sound-payment", merchant_id="merchant_other", store_id="store_other",
                          order_id="OTHER-ORDER", customer_id=customer.id, amount_paise=9876,
                          source_type="SHOP_ORDER", source_id="other-order", provider="paytm",
                          provider_order_id="OTHER-ORDER", provider_transaction_id="OTHER-TXN",
                          bank="", method="UPI", status="SUCCESS", verified_at=datetime.now(timezone.utc))
        s.add(customer); s.add(payment); s.flush()
        event = SoundEvent(merchant_id="merchant_other", store_id="store_other", payment_id=payment.id,
                           source_type="SHOP_ORDER", source_id="other-order", provider_order_id="OTHER-ORDER",
                           provider_transaction_id="OTHER-TXN", amount_paise=9876, currency="INR",
                           idempotency_key="other-store-sound-event")
        s.add(event); s.commit(); other_event_id = event.id

    _owner, membership = auth.create_user_membership(
        username="other-sound-owner", password="Secure owner password 2026!",
        merchant_id="merchant_other", store_id="store_other", role="OWNER",
    )
    raw_session, csrf, _expires = auth.create_session(membership.id)
    other = TestClient(app, base_url="https://merchant.test")
    other.cookies.set("wapas_session", raw_session)
    other.cookies.set("wapas_csrf", csrf)
    headers = {"Origin": "https://merchant.test", "X-Wapas-CSRF": csrf}

    _default_owner, default_membership = auth.create_user_membership(
        username="default-sound-owner", password="Secure owner password 2026!",
        merchant_id="merchant_default", store_id="store_default", role="OWNER",
    )
    default_token, default_csrf, _default_expiry = auth.create_session(default_membership.id)
    default = TestClient(app, base_url="https://merchant.test")
    default.cookies.set("wapas_session", default_token)
    default.cookies.set("wapas_csrf", default_csrf)
    default_headers = {"Origin":"https://merchant.test", "X-Wapas-CSRF":default_csrf}
    device_key = "device_default_12345678901234567890"
    assert default.post("/api/merchant/sound/device", json={"device_key": device_key}, headers=default_headers).status_code == 200
    ack = default.post("/api/merchant/sound/events/ack", json={
        "device_key": device_key, "event_ids": [other_event_id],
    }, headers=default_headers)
    assert ack.status_code == 200 and ack.json()["acknowledged_through"] == 0
    assert default.get("/api/merchant/sound/events", params={"device_key": device_key}).json()["events"] == []

    assert other.get("/api/merchant/sound/events", params={"device_key": device_key}).status_code == 404
    other_device = "device_other_12345678901234567890"
    registered = other.post("/api/merchant/sound/device", json={"device_key": other_device}, headers=headers)
    assert registered.status_code == 200, registered.text
    with session() as s:
        customer = s.get(Customer, "other-sound-customer")
        later_payment = Payment(id="other-sound-payment-later", merchant_id="merchant_other", store_id="store_other",
                                order_id="OTHER-ORDER-LATER", customer_id=customer.id, amount_paise=4321,
                                source_type="SHOP_ORDER", source_id="other-order-later", provider="paytm",
                                provider_order_id="OTHER-ORDER-LATER", provider_transaction_id="OTHER-TXN-LATER",
                                bank="", method="UPI", status="SUCCESS", verified_at=datetime.now(timezone.utc))
        s.add(later_payment); s.flush()
        later_event = SoundEvent(merchant_id="merchant_other", store_id="store_other", payment_id=later_payment.id,
                                 source_type="SHOP_ORDER", source_id="other-order-later",
                                 provider_order_id="OTHER-ORDER-LATER", provider_transaction_id="OTHER-TXN-LATER",
                                 amount_paise=4321, currency="INR", idempotency_key="other-store-later-event")
        s.add(later_event); s.commit(); later_event_id = later_event.id
    cross_ack = default.post("/api/merchant/sound/events/ack", json={
        "device_key": device_key, "event_ids": [later_event_id],
    }, headers=default_headers)
    assert cross_ack.status_code == 200 and cross_ack.json()["acknowledged_through"] == 0
    assert default.get("/api/merchant/sound/events", params={"device_key": device_key}).json()["events"] == []
    visible = other.get("/api/merchant/sound/events", params={"device_key": other_device})
    assert [item["payment_id"] for item in visible.json()["events"]] == ["other-sound-payment-later"]

    with session() as s:
        customer = s.exec(select(Customer).where(Customer.merchant_id == "merchant_default")).first()
        second = _record_paytm_success(s, customer.id, "payment-sound-2", "ORDER-SOUND-2")
        s.commit()

    events = default.get("/api/merchant/sound/events", params={"device_key": device_key}).json()["events"]
    assert len(events) == 1 and events[0]["payment_id"] == second.id
    ack = default.post("/api/merchant/sound/events/ack", json={
        "device_key": device_key, "event_ids": [events[0]["id"]],
    }, headers=default_headers)
    assert ack.status_code == 200
    assert default.get("/api/merchant/sound/events", params={"device_key": device_key}).json()["events"] == []


def test_fake_or_mismatched_status_never_creates_sound_event(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "paytm_mid", "MID-SOUND")
    with session() as s:
        customer = s.exec(select(Customer).where(Customer.merchant_id == "merchant_default")).first()
        fake = Payment(id="payment-fake-sound", merchant_id="merchant_default", store_id="store_default",
                       order_id="ORDER-FAKE", customer_id=customer.id, amount_paise=1234,
                       provider="fake", provider_order_id="ORDER-FAKE", bank="", method="", status="PENDING")
        wrong = Payment(id="payment-wrong-sound", merchant_id="merchant_default", store_id="store_default",
                        order_id="ORDER-WRONG", customer_id=customer.id, amount_paise=1234,
                        provider="paytm", provider_mid="MID-SOUND", provider_order_id="ORDER-WRONG",
                        bank="", method="", status="PENDING")
        s.add(fake)
        s.add(wrong)
        s.flush()
        assert payment_events.record_verified_success(
            s, fake, _verified_result("ORDER-FAKE"), gateway_name="fake", expected_order_id="ORDER-FAKE",
        )
        mismatch = _verified_result("ORDER-WRONG")
        mismatch.raw["mid"] = "SOMEONE-ELSE"
        assert not payment_events.record_verified_success(
            s, wrong, mismatch, gateway_name="paytm", expected_order_id="ORDER-WRONG",
        )
        s.commit()
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id.in_([fake.id, wrong.id]))).all() == []


def test_pending_failed_unknown_and_missing_source_payments_remain_silent(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "paytm_mid", "MID-SOUND")
    with session() as s:
        customer = s.exec(select(Customer).where(Customer.merchant_id == "merchant_default")).first()
        payments = []
        for suffix in ("pending", "unknown", "failed", "missing-source"):
            payment = Payment(
                id="silent-" + suffix, merchant_id="merchant_default", store_id="store_default",
                order_id="ORDER-" + suffix, customer_id=customer.id, amount_paise=1234,
                source_type="RECOVERY" if suffix == "failed" else "SHOP_ORDER",
                source_id="missing-order-" + suffix, provider="paytm",
                provider_mid="MID-SOUND", provider_order_id="ORDER-" + suffix,
                idempotency_key="silent-test:" + suffix, bank="", method="PAYMENT_LINK", status="PENDING",
            )
            s.add(payment); payments.append(payment)
        s.flush()
        pending = StatusResult(status=PayStatus.PENDING, raw={})
        assert apply_terminal_result(s, payments[0], pending, gateway_name="paytm") == "PENDING"
        unknown = StatusResult(status=PayStatus.ERROR, raw={})
        assert apply_terminal_result(s, payments[1], unknown, gateway_name="paytm") == "PENDING"
        failed = StatusResult(status=PayStatus.FAILED,
                              raw={"mid":"MID-SOUND", "orderId":"ORDER-failed", "currency":"INR"})
        assert apply_terminal_result(s, payments[2], failed, gateway_name="paytm") == "FAILED"
        missing = _verified_result("ORDER-missing-source")
        assert apply_terminal_result(s, payments[3], missing, gateway_name="paytm") == "SOURCE_MISSING"
        s.commit()
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id.in_([p.id for p in payments]))).all() == []
        assert s.get(Payment, payments[0].id).status == "PENDING"
        assert s.get(Payment, payments[1].id).status == "PENDING"
        assert s.get(Payment, payments[2].id).status == "FAILED"
        assert s.get(Payment, payments[3].id).status == "PENDING_RECONCILIATION"


def test_verified_paytm_counter_and_khata_events_settle_only_their_sources_once(db, monkeypatch):
    from decimal import Decimal
    from app.billing_models import Bill
    from app.khata_models import KhataLedgerEntry
    from app.merchant_os_models import InventoryBalance

    monkeypatch.setattr(get_settings(), "paytm_mid", "MID-SOUND")
    with session() as s:
        customer = s.exec(select(Customer).where(Customer.merchant_id == "merchant_default")).first()
        product = create_product(s, merchant_id="merchant_default", store_id="store_default",
                                 product_id="paytm-stock", name="Tea", unit="each",
                                 unit_price_paise=1234, opening_stock=Decimal("3"), sku="PAYTM-TEA")
        bill = billing.create_draft(s, merchant_id="merchant_default", store_id="store_default",
                                    idempotency_key="paytm-counter-bill", customer_name="Customer",
                                    customer_phone=customer.phone)
        billing.set_line(s, merchant_id="merchant_default", store_id="store_default",
                         bill_id=bill.id, product_id=product.id, quantity="1")
        billing.issue_bill(s, merchant_id="merchant_default", store_id="store_default", bill_id=bill.id)
        bill.payment_state = "PENDING"
        payment = Payment(
            id="payment-paytm-counter", merchant_id="merchant_default", store_id="store_default",
            order_id="ORDER-COUNTER", customer_id=customer.id, amount_paise=1234,
            source_type="COUNTER_BILL", source_id=bill.id, provider="paytm", provider_mid="MID-SOUND",
            provider_order_id="ORDER-COUNTER", provider_link_id="LINK-COUNTER",
            idempotency_key="paytm-counter-attempt-001", bank="", method="PAYMENT_LINK", status="PENDING",
        )
        bill.payment_id = payment.id
        s.add(payment); s.add(bill); s.flush()
        result = _verified_result("ORDER-COUNTER")
        result.raw["_verified_link_id"] = "LINK-COUNTER"
        assert apply_terminal_result(s, payment, result, gateway_name="paytm",
                                     expected_link_id="LINK-COUNTER") == "PAID"
        assert apply_terminal_result(s, payment, result, gateway_name="paytm",
                                     expected_link_id="LINK-COUNTER") == "SUCCESS"
        s.commit()
        assert s.get(Bill, bill.id).payment_state == "PAID"
        stock = s.exec(select(InventoryBalance).where(InventoryBalance.product_id == product.id)).one()
        assert stock.on_hand == Decimal("2.000") and stock.reserved == Decimal("0.000")
        assert len(s.exec(select(SoundEvent).where(SoundEvent.payment_id == payment.id)).all()) == 1

        khata_bill = billing.create_draft(s, merchant_id="merchant_default", store_id="store_default",
                                          idempotency_key="paytm-khata-bill", customer_name="Customer",
                                          customer_phone=customer.phone)
        billing.set_line(s, merchant_id="merchant_default", store_id="store_default",
                         bill_id=khata_bill.id, product_id=product.id, quantity="1")
        billing.issue_bill(s, merchant_id="merchant_default", store_id="store_default", bill_id=khata_bill.id)
        account, credit = khata.add_bill_to_khata(
            s, merchant_id="merchant_default", store_id="store_default", bill_id=khata_bill.id,
        )
        khata_payment = Payment(
            id="payment-paytm-khata", merchant_id="merchant_default", store_id="store_default",
            order_id="ORDER-KHATA", customer_id=customer.id, amount_paise=1234,
            source_type="KHATA_COLLECTION", source_id=account.id, provider="paytm", provider_mid="MID-SOUND",
            provider_order_id="ORDER-KHATA", provider_link_id="LINK-KHATA",
            idempotency_key="paytm-khata-attempt-001", bank="", method="PAYMENT_LINK", status="PENDING",
        )
        s.add(khata_payment); s.flush()
        khata_result = _verified_result("ORDER-KHATA")
        khata_result.raw["_verified_link_id"] = "LINK-KHATA"
        assert apply_terminal_result(s, khata_payment, khata_result, gateway_name="paytm",
                                     expected_link_id="LINK-KHATA") == "PAID"
        s.commit()
        ledger = s.exec(select(KhataLedgerEntry).where(
            KhataLedgerEntry.account_id == account.id,
        ).order_by(KhataLedgerEntry.created_at)).all()
        assert [entry.delta_paise for entry in ledger] == [1234, -1234]
        assert len(s.exec(select(SoundEvent).where(SoundEvent.payment_id == khata_payment.id)).all()) == 1


def test_paytm_khata_collection_partial_replay_and_over_settlement_are_guarded(db, monkeypatch):
    from decimal import Decimal
    from app.khata_models import KhataLedgerEntry

    monkeypatch.setattr(get_settings(), "paytm_mid", "MID-SOUND")
    with session() as s:
        customer = s.exec(select(Customer).where(Customer.merchant_id == "merchant_default")).first()
        product = create_product(s, merchant_id="merchant_default", store_id="store_default",
                                 product_id="khata-collection-stock", name="Rice", unit="each",
                                 unit_price_paise=5000, opening_stock=Decimal("4"), sku="KHATA-RICE")
        bill = billing.create_draft(s, merchant_id="merchant_default", store_id="store_default",
                                    idempotency_key="khata-collection-credit", customer_name=customer.name,
                                    customer_phone=customer.phone)
        billing.set_line(s, merchant_id="merchant_default", store_id="store_default",
                         bill_id=bill.id, product_id=product.id, quantity="2")
        billing.issue_bill(s, merchant_id="merchant_default", store_id="store_default", bill_id=bill.id)
        account, _credit = khata.add_bill_to_khata(
            s, merchant_id="merchant_default", store_id="store_default", bill_id=bill.id,
        )
        partial = Payment(id="khata-partial-payment", merchant_id="merchant_default", store_id="store_default",
                          order_id="KHATA-PARTIAL-ORDER", customer_id=customer.id, amount_paise=5000,
                          source_type="KHATA_COLLECTION", source_id=account.id, provider="paytm",
                          provider_mid="MID-SOUND", provider_order_id="KHATA-PARTIAL-ORDER",
                          provider_link_id="KHATA-PARTIAL-LINK", idempotency_key="khata-partial-key",
                          bank="", method="PAYMENT_LINK", status="PENDING")
        s.add(partial); s.flush()
        partial_result = StatusResult(
            status=PayStatus.SUCCESS, txn_id="KHATA-PARTIAL-TXN", amount_paise=5000,
            raw={"mid":"MID-SOUND", "orderId":"KHATA-PARTIAL-ORDER", "txnId":"KHATA-PARTIAL-TXN",
                 "txnAmount":"50.00", "currency":"INR", "_verified_link_id":"KHATA-PARTIAL-LINK"},
        )
        first = apply_terminal_result(s, partial, partial_result, gateway_name="paytm",
                                      expected_link_id="KHATA-PARTIAL-LINK")
        replay = apply_terminal_result(s, partial, partial_result, gateway_name="paytm",
                                       expected_link_id="KHATA-PARTIAL-LINK")
        assert first == "PAID" and replay == "SUCCESS"
        s.commit()

        entries = s.exec(select(KhataLedgerEntry).where(
            KhataLedgerEntry.account_id == account.id,
        ).order_by(KhataLedgerEntry.created_at, KhataLedgerEntry.id)).all()
        assert [entry.delta_paise for entry in entries] == [10000, -5000]
        assert len(s.exec(select(SoundEvent).where(SoundEvent.payment_id == partial.id)).all()) == 1

        excess = Payment(id="khata-over-payment", merchant_id="merchant_default", store_id="store_default",
                         order_id="KHATA-OVER-ORDER", customer_id=customer.id, amount_paise=6000,
                         source_type="KHATA_COLLECTION", source_id=account.id, provider="paytm",
                         provider_mid="MID-SOUND", provider_order_id="KHATA-OVER-ORDER",
                         provider_link_id="KHATA-OVER-LINK", idempotency_key="khata-over-key",
                         bank="", method="PAYMENT_LINK", status="PENDING")
        s.add(excess); s.flush()
        over_result = StatusResult(
            status=PayStatus.SUCCESS, txn_id="KHATA-OVER-TXN", amount_paise=6000,
            raw={"mid":"MID-SOUND", "orderId":"KHATA-OVER-ORDER", "txnId":"KHATA-OVER-TXN",
                 "txnAmount":"60.00", "currency":"INR", "_verified_link_id":"KHATA-OVER-LINK"},
        )
        assert apply_terminal_result(s, excess, over_result, gateway_name="paytm",
                                     expected_link_id="KHATA-OVER-LINK") == "RECONCILIATION_REQUIRED"
        s.commit()
        assert s.get(Payment, excess.id).status == "PENDING_RECONCILIATION"
        assert len(s.exec(select(KhataLedgerEntry).where(KhataLedgerEntry.account_id == account.id)).all()) == 2
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id == excess.id)).all() == []


def test_verified_paytm_shop_payment_is_source_bound_and_fulfillment_requires_it(db, monkeypatch):
    from decimal import Decimal
    from app import inventory
    from app.commerce_models import StoreOrder, StoreOrderLine
    from app.merchant_os_models import InventoryBalance

    monkeypatch.setattr(get_settings(), "paytm_mid", "MID-SOUND")
    with session() as s:
        customer = s.exec(select(Customer).where(Customer.merchant_id == "merchant_default")).first()
        product = create_product(s, merchant_id="merchant_default", store_id="store_default",
                                 product_id="paytm-shop-stock", name="Lamp", unit="each",
                                 unit_price_paise=1234, opening_stock=Decimal("2"), sku="PAYTM-LAMP")
        order = StoreOrder(
            id="shop-paytm-verified", merchant_id="merchant_default", store_id="store_default",
            customer_id=customer.id, payment_id="payment-paytm-shop", idempotency_key="shop-paytm-verified-key",
            token_hash="t" * 64, status="PAYMENT_PENDING", fulfillment_state="UNFULFILLED", amount_paise=1234,
        )
        payment = Payment(
            id="payment-paytm-shop", merchant_id="merchant_default", store_id="store_default",
            order_id=order.id, customer_id=customer.id, amount_paise=1234,
            source_type="SHOP_ORDER", source_id=order.id, provider="paytm", provider_mid="MID-SOUND",
            provider_order_id=order.id, idempotency_key="paytm-shop-attempt-001", bank="", method="UPI", status="PENDING",
        )
        s.add(payment); s.flush()
        s.add(order); s.flush()
        reservation_id = order.id + ":" + product.id
        inventory.reserve_stock(s, merchant_id=order.merchant_id, store_id=order.store_id,
                                product_id=product.id, quantity=Decimal("1"), reservation_id=reservation_id,
                                source_ref=order.id, source="shop_order")
        s.add(StoreOrderLine(
            merchant_id=order.merchant_id, store_id=order.store_id, order_id=order.id,
            product_id=product.id, product_name=product.name, sku=product.sku, unit=product.unit,
            quantity=Decimal("1"), unit_price_paise=1234, line_total_paise=1234,
            reservation_id=reservation_id,
        ))
        assert apply_terminal_result(s, payment, _verified_result(order.id), gateway_name="paytm",
                                     expected_order_id=order.id) == "PAID"
        assert apply_terminal_result(s, payment, _verified_result(order.id), gateway_name="paytm",
                                     expected_order_id=order.id) == "SUCCESS"
        s.commit()
        saved_order = s.get(StoreOrder, order.id)
        saved_payment = s.get(Payment, payment.id)
        balance = s.exec(select(InventoryBalance).where(InventoryBalance.product_id == product.id)).one()
        assert saved_order.status == "PAID" and saved_order.paid_at is not None
        assert saved_payment.status == "SUCCESS" and saved_payment.verified_at is not None
        assert balance.on_hand == Decimal("1.000") and balance.reserved == Decimal("0.000")
        assert len(s.exec(select(SoundEvent).where(SoundEvent.payment_id == payment.id)).all()) == 1

    client = TestClient(app, base_url="http://merchant.test", headers={"X-Wapas-Console": "1"})
    fulfilled = client.post(f"/api/merchant/orders/{order.id}/fulfill", json={"confirm": True})
    assert fulfilled.status_code == 200 and fulfilled.json()["fulfillment_state"] == "FULFILLED"


def test_sound_mode_mandatory_negative_conditions_never_announce_payment(db, monkeypatch):
    """Prove that pending, forged, unknown, mismatched, failed, ambiguous, and duplicate callbacks
    do not emit false soundbox announcements."""
    from app.gateway import get_gateway
    from app.billing_models import Bill

    monkeypatch.setattr(get_settings(), "paytm_mid", "MID-SOUND")
    provider = get_gateway()
    monkeypatch.setattr(provider, "name", "paytm")
    client = TestClient(app)

    with session() as s:
        customer = s.exec(select(Customer).where(Customer.merchant_id == "merchant_default")).first()
        test_bill = Bill(
            id="bill-sound-negative", merchant_id="merchant_default", store_id="store_default",
            bill_number="NEG-001", state="ISSUED", payment_state="PENDING", total_paise=5000,
        )
        test_payment = Payment(
            id="payment-sound-negative", merchant_id="merchant_default", store_id="store_default",
            order_id="NEG-ORDER-001", customer_id=customer.id, amount_paise=5000,
            source_type="COUNTER_BILL", source_id=test_bill.id, provider="paytm",
            provider_mid="MID-SOUND", provider_order_id="NEG-ORDER-001",
            provider_link_id="LINK-NEG-001", idempotency_key="neg-attempt-001",
            bank="", method="PAYMENT_LINK", status="PENDING",
        )
        test_bill.payment_id = test_payment.id
        s.add(test_bill)
        s.add(test_payment)
        s.commit()

    # 1. Forged callback (invalid checksum signature)
    monkeypatch.setattr(provider, "verify_callback", lambda form: False)
    res_forged = client.post("/api/paytm/payment-callback", data={"LINKID": "LINK-NEG-001", "CHECKSUMHASH": "bad"})
    assert res_forged.status_code == 400
    with session() as s:
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id == test_payment.id)).all() == []

    # Enable valid signature mock
    monkeypatch.setattr(provider, "verify_callback", lambda form: True)

    # 2. Unknown order / link ID
    res_unknown = client.post("/api/paytm/payment-callback", data={"LINKID": "LINK-UNKNOWN-999", "CHECKSUMHASH": "ok"})
    assert res_unknown.status_code == 200
    assert res_unknown.json()["status"] == "unknown"
    with session() as s:
        assert s.exec(select(SoundEvent)).all() == []

    # 3. Pending checkout / status
    monkeypatch.setattr(provider, "link_status", lambda link_id: StatusResult(status=PayStatus.PENDING, raw={}))
    res_pending = client.post("/api/paytm/payment-callback", data={"LINKID": "LINK-NEG-001", "CHECKSUMHASH": "ok"})
    assert res_pending.status_code == 200
    assert res_pending.json()["status"] == "PENDING"
    with session() as s:
        assert s.get(Payment, test_payment.id).status == "PENDING"
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id == test_payment.id)).all() == []

    # 4. Amount mismatch (expected 5000 paise, provider reports 2500)
    mismatch_result = StatusResult(
        status=PayStatus.SUCCESS, txn_id="TXN-MISMATCH", amount_paise=2500,
        raw={"mid": "MID-SOUND", "orderId": "NEG-ORDER-001", "txnId": "TXN-MISMATCH",
             "txnAmount": "25.00", "currency": "INR", "_verified_link_id": "LINK-NEG-001"},
    )
    monkeypatch.setattr(provider, "link_status", lambda link_id: mismatch_result)
    res_mismatch = client.post("/api/paytm/payment-callback", data={"LINKID": "LINK-NEG-001", "CHECKSUMHASH": "ok"})
    assert res_mismatch.status_code == 200
    assert res_mismatch.json()["status"] == "AMOUNT_MISMATCH"
    with session() as s:
        assert s.get(Payment, test_payment.id).status == "PENDING_RECONCILIATION"
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id == test_payment.id)).all() == []

    # Reset payment status for failure test
    with session() as s:
        p = s.get(Payment, test_payment.id)
        p.status = "PENDING"
        s.add(p); s.commit()

    # 5. Failed / Expired payment
    fail_result = StatusResult(
        status=PayStatus.FAILED, txn_id="TXN-FAIL", amount_paise=5000,
        raw={"mid": "MID-SOUND", "orderId": "NEG-ORDER-001", "currency": "INR", "_verified_link_id": "LINK-NEG-001"},
    )
    monkeypatch.setattr(provider, "link_status", lambda link_id: fail_result)
    res_fail = client.post("/api/paytm/payment-callback", data={"LINKID": "LINK-NEG-001", "CHECKSUMHASH": "ok"})
    assert res_fail.status_code == 200
    assert res_fail.json()["status"] == "FAILED"
    with session() as s:
        assert s.get(Payment, test_payment.id).status == "FAILED"
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id == test_payment.id)).all() == []

    # 6. Ambiguous status (gateway error)
    with session() as s:
        p = s.get(Payment, test_payment.id)
        p.status = "PENDING"
        s.add(p); s.commit()
    ambiguous_result = StatusResult(status=PayStatus.ERROR, raw={})
    monkeypatch.setattr(provider, "link_status", lambda link_id: ambiguous_result)
    res_ambiguous = client.post("/api/paytm/payment-callback", data={"LINKID": "LINK-NEG-001", "CHECKSUMHASH": "ok"})
    assert res_ambiguous.status_code == 200
    assert res_ambiguous.json()["status"] == "ERROR"
    with session() as s:
        assert s.get(Payment, test_payment.id).status == "PENDING"
        assert s.exec(select(SoundEvent).where(SoundEvent.payment_id == test_payment.id)).all() == []

    # 7. Verified payment emits exactly one event; duplicate callback replay is idempotent
    success_result = StatusResult(
        status=PayStatus.SUCCESS, txn_id="TXN-SUCCESS-NEG", amount_paise=5000,
        raw={"mid": "MID-SOUND", "orderId": "NEG-ORDER-001", "txnId": "TXN-SUCCESS-NEG",
             "txnAmount": "50.00", "currency": "INR", "_verified_link_id": "LINK-NEG-001"},
    )
    monkeypatch.setattr(provider, "link_status", lambda link_id: success_result)
    res_success_1 = client.post("/api/paytm/payment-callback", data={"LINKID": "LINK-NEG-001", "CHECKSUMHASH": "ok"})
    assert res_success_1.status_code == 200
    assert res_success_1.json()["status"] == "PAID"
    with session() as s:
        assert len(s.exec(select(SoundEvent).where(SoundEvent.payment_id == test_payment.id)).all()) == 1

    # Duplicate callback replay
    res_success_2 = client.post("/api/paytm/payment-callback", data={"LINKID": "LINK-NEG-001", "CHECKSUMHASH": "ok"})
    assert res_success_2.status_code == 200
    assert res_success_2.json()["status"] == "SUCCESS"
    with session() as s:
        assert len(s.exec(select(SoundEvent).where(SoundEvent.payment_id == test_payment.id)).all()) == 1

