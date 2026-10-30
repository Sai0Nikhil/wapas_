from fastapi.testclient import TestClient
from sqlmodel import select

from app import executor
from app.models import Case, Evidence, Payment
from app.ports import PayStatus, StatusResult


def client(db):
    from app.main import app
    return TestClient(app, headers={"X-Wapas-Console": "1"})


def test_real_checkout_failure_opens_a_case_and_success_does_not(db):
    c = client(db)
    r = c.post("/api/shop/checkout", json={"product": "earbuds", "name": "Rahul Sharma", "phone": "9876543210", "language": "hi"})
    assert r.status_code == 200 and r.json()["mode"] == "fake"
    order = r.json()["order_id"]
    r = c.post(f"/fakecheckout/{order}", data={"outcome": "bank", "bank": "Bank B"}, follow_redirects=False)
    assert r.status_code == 303
    with db.session() as s:
        p = s.get(Payment, f"pay_{order}")
        assert p.status == "FAILED" and p.failure_code == "BANK_DECLINED" and p.bank == "Bank B"
        case = s.get(Case, f"c_{order}")
        assert case and case.state == "NEW"
        executor.tick(s)
        assert s.get(Case, f"c_{order}").state == "SENT"   # single failure, bank not degraded: link now
    order2 = c.post("/api/shop/checkout", json={"product": "bulbs", "name": "Lakshmi", "phone": "9123456780", "language": "te"}).json()["order_id"]
    c.post(f"/fakecheckout/{order2}", data={"outcome": "success", "bank": "Bank A"})
    with db.session() as s:
        assert s.get(Payment, f"pay_{order2}").status == "SUCCESS"
        assert s.get(Case, f"c_{order2}") is None


def test_duplicate_and_forged_callbacks(db):
    c = client(db)
    order = c.post("/api/shop/checkout", json={"product": "charger", "name": "Imran", "phone": "9000011111"}).json()["order_id"]
    c.post(f"/fakecheckout/{order}", data={"outcome": "cancel"})
    fake = {"ORDERID": order, "STATUS": "TXN_FAILURE", "RESPCODE": "141", "CHECKSUMHASH": "fake-ok"}
    c.post("/api/paytm/txn-callback", data=fake)  # duplicate
    with db.session() as s:
        assert len(s.exec(select(Case).where(Case.id == f"c_{order}")).all()) == 1
        assert s.get(Payment, f"pay_{order}").failure_code == "USER_DROPPED"
    r = c.post("/api/paytm/txn-callback", data=dict(fake, CHECKSUMHASH="forged"))
    assert r.status_code == 400


def test_checkout_success_requires_exact_status_amount_and_ignores_callback_amount(db):
    from app.gateway import get_gateway

    c = client(db)
    gw = get_gateway()
    for phone, reported_amount in (("9000011112", 1), ("9000011113", 0)):
        order = c.post("/api/shop/checkout", json={
            "product": "charger", "name": "Imran", "phone": phone,
        }).json()["order_id"]
        gw.order_status = lambda _order_id, amount=reported_amount: StatusResult(
            PayStatus.SUCCESS, txn_id="TXN-TEST", amount_paise=amount,
        )

        # Deliberately forge a much larger callback amount. It is checksum-valid in
        # the fake adapter, but the server status response is the only authority.
        r = c.post("/api/paytm/txn-callback", data={
            "ORDERID": order, "TXNAMOUNT": "999999.00", "STATUS": "TXN_SUCCESS",
            "CHECKSUMHASH": "fake-ok",
        }, follow_redirects=False)
        assert r.status_code == 303
        with db.session() as s:
            payment = s.get(Payment, f"pay_{order}")
            assert payment.status == "PENDING"
            assert payment.amount_paise == 125000  # original catalogue amount is unchanged
            assert s.get(Case, f"c_{order}") is None
            assert s.exec(select(Evidence).where(
                Evidence.case_id == "", Evidence.kind == "checkout_amount_mismatch",
            )).first() is not None


def test_ambiguous_paytm_initiation_is_polled_and_not_falsely_failed(db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import store
    from app.gateway import get_gateway

    gw = get_gateway()
    actual_initiate = gw.initiate_checkout

    def accepted_but_response_lost(**kwargs):
        actual_initiate(**kwargs)  # provider accepted and created the order
        return {"ok": False, "uncertain": True, "error": "ReadTimeout"}

    monkeypatch.setattr(gw, "initiate_checkout", accepted_but_response_lost)
    response = client(db).post("/api/shop/checkout", json={
        "product": "charger", "name": "Meena", "phone": "9000011114",
    })
    assert response.status_code == 502
    with db.session() as s:
        pending = s.exec(select(Payment).where(Payment.customer_id == "shop_9000011114")).one()
        order = pending.order_id
        assert pending.status == "INIT_UNKNOWN"

    gw.finish_checkout(order, success=True)
    result = store.reconcile(datetime.now(timezone.utc) + timedelta(minutes=2))
    assert result["recorded"] == 1
    with db.session() as s:
        payment = s.get(Payment, f"pay_{order}")
        assert payment.status == "SUCCESS" and payment.amount_paise == 125000
        assert s.get(Case, f"c_{order}") is None


def test_ambiguous_initiation_with_no_provider_order_closes_without_opening_case(db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import store
    from app.gateway import get_gateway

    gw = get_gateway()
    monkeypatch.setattr(gw, "initiate_checkout", lambda **_: {
        "ok": False, "uncertain": True, "error": "ReadTimeout",
    })
    response = client(db).post("/api/shop/checkout", json={
        "product": "bulbs", "name": "Kiran", "phone": "9000011115",
    })
    assert response.status_code == 502
    with db.session() as s:
        pending = s.exec(select(Payment).where(Payment.customer_id == "shop_9000011115")).one()
        order = pending.order_id
        assert pending.status == "INIT_UNKNOWN"

    result = store.reconcile(datetime.now(timezone.utc) + timedelta(minutes=11))
    assert result["init_failed"] == 1
    with db.session() as s:
        payment = s.get(Payment, f"pay_{order}")
        assert payment.status == "INIT_FAILED"
        assert s.get(Case, f"c_{order}") is None


def test_unknown_checkout_callback_cannot_create_a_paid_payment(db):
    c = client(db)
    r = c.post("/api/paytm/txn-callback", data={
        "ORDERID": "WAPUNKNOWN123", "TXNAMOUNT": "1.00", "STATUS": "TXN_SUCCESS",
        "CHECKSUMHASH": "fake-ok",
    }, follow_redirects=False)
    assert r.status_code == 303
    with db.session() as s:
        assert s.get(Payment, "pay_WAPUNKNOWN123") is None


def test_bad_phone_rejected(db):
    r = client(db).post("/api/shop/checkout", json={"product": "earbuds", "name": "X Y", "phone": "12345"})
    assert r.status_code == 422


def test_public_tunnel_reaches_the_store_but_not_the_console(db, monkeypatch):
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.main import app
    monkeypatch.setattr(get_settings(), "admin_token", "")
    c = TestClient(app, headers={"X-Wapas-Console": "1"})
    via_tunnel = {"X-Forwarded-For": "203.0.113.9"}
    assert c.get("/api/shop/products", headers=via_tunnel).status_code == 200
    assert c.get("/shop", headers=via_tunnel).status_code == 200
    assert "Sign in to your store" in c.get("/", headers=via_tunnel).text
    for path in ("/api/state", "/api/integrations"):
        assert c.get(path, headers=via_tunnel).status_code == 401
    for path in ("/api/demo/reset", "/api/owner/approve/c_A121", "/api/eval/run?n=10"):
        assert c.post(path, headers=via_tunnel).status_code == 401
    assert c.get("/api/state").status_code == 200  # local, un-proxied: the owner at the laptop


def test_legacy_admin_token_does_not_authenticate_console(db, monkeypatch):
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.main import app
    monkeypatch.setattr(get_settings(), "admin_token", "s3cret-token")
    c = TestClient(app, headers={"X-Wapas-Console": "1"})
    via_tunnel = {"X-Forwarded-For": "203.0.113.9"}
    assert c.get("/api/state", headers={**via_tunnel, "X-Wapas-Token": "wrong"}).status_code == 401
    assert c.get("/api/state", headers={**via_tunnel, "X-Wapas-Token": "s3cret-token"}).status_code == 401
    r = c.get("/?token=s3cret-token", headers=via_tunnel)
    assert r.status_code == 200 and "Sign in to your store" in r.text
    assert "wapas_token" not in r.cookies


def test_lost_callback_is_recovered_by_the_reconciler(db):
    from datetime import datetime, timedelta, timezone
    from app import store
    from app.gateway import get_gateway
    c = client(db)
    order = c.post("/api/shop/checkout", json={"product": "speaker", "name": "Meena", "phone": "9811122233", "language": "ta"}).json()["order_id"]
    now = datetime.now(timezone.utc)
    assert store.reconcile(now + timedelta(seconds=10))["checked"] == 0      # Paytm's callback gets a minute first
    assert store.reconcile(now + timedelta(minutes=2))["recorded"] == 0      # still pending at Paytm: nothing opened
    get_gateway().finish_checkout(order, success=False)                     # the customer failed; the callback never arrived
    assert store.reconcile(now + timedelta(minutes=2))["recorded"] == 1
    with db.session() as s:
        p = s.get(Payment, f"pay_{order}")
        assert p.status == "FAILED" and p.customer_id == "shop_9811122233"   # survives a restart: stored at checkout
        assert s.get(Case, f"c_{order}").state == "NEW"
    c.post("/api/paytm/txn-callback", data={"ORDERID": order, "STATUS": "TXN_FAILURE", "RESPCODE": "227", "CHECKSUMHASH": "fake-ok"})
    with db.session() as s:  # the late callback changes nothing
        assert len(s.exec(select(Case).where(Case.id == f"c_{order}")).all()) == 1


def test_abandoned_checkout_opens_a_case_only_after_the_window(db):
    from datetime import datetime, timedelta, timezone
    from app import store
    from app.gateway import get_gateway
    c = client(db)
    order = c.post("/api/shop/checkout", json={"product": "bulbs", "name": "Kiran", "phone": "9822233344"}).json()["order_id"]
    get_gateway().orders.pop(order)  # Paytm has no record of any attempt
    now = datetime.now(timezone.utc)
    assert store.reconcile(now + timedelta(minutes=5))["abandoned"] == 0
    assert store.reconcile(now + timedelta(minutes=11))["abandoned"] == 1
    with db.session() as s:
        p = s.get(Payment, f"pay_{order}")
        assert p.status == "FAILED" and p.failure_code == "USER_DROPPED"
        assert s.get(Case, f"c_{order}") is not None


def test_status_api_down_during_reconcile_changes_nothing(db):
    from datetime import datetime, timedelta, timezone
    from app import store
    from app.gateway import get_gateway
    c = client(db)
    order = c.post("/api/shop/checkout", json={"product": "charger", "name": "Arun", "phone": "9833344455"}).json()["order_id"]
    gw = get_gateway()
    gw.finish_checkout(order, success=False)
    gw.fail_status_calls = True
    try:
        assert store.reconcile(datetime.now(timezone.utc) + timedelta(hours=2))["recorded"] == 0
    finally:
        gw.fail_status_calls = False
    with db.session() as s:
        assert s.get(Payment, f"pay_{order}").status == "PENDING" and s.get(Case, f"c_{order}") is None


def test_cross_site_form_posts_cannot_drive_the_console(db):
    from fastapi.testclient import TestClient
    from app.main import app
    bare = TestClient(app)  # a form auto-submitted from another site: no custom header possible
    assert bare.post("/api/demo/reset", headers={"Origin": "https://evil.example", "Content-Type": "text/plain"}).status_code == 403
    assert bare.post("/api/owner/approve/c_A121").status_code == 403
    ok = TestClient(app, headers={"X-Wapas-Console": "1"})
    assert ok.post("/api/demo/reset", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert ok.post("/api/demo/reset").status_code == 200
    assert bare.post("/api/shop/checkout", json={"product": "earbuds", "name": "A B", "phone": "9876500000"}).status_code == 200


def test_result_page_rejects_script_in_order_id(db):
    c = client(db)
    assert c.get("/shop/result/%3Csvg%20onload%3Dalert(1)%3E").status_code == 404
    assert c.get("/shop/result/WAPNOSUCHORDER").status_code == 404


def test_checkout_is_rate_limited_per_phone(db):
    from app import store
    c = client(db)
    codes = [c.post("/api/shop/checkout", json={"product": "bulbs", "name": "Spam Bot", "phone": "9000000001"}).status_code
             for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
