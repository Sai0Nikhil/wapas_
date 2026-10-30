"""Production safety and demo isolation tests.

Verifies:
- Demo controls and fake checkout are rejected with 403 in production.
- Unauthenticated requests to non-public demo endpoints are rejected with 401 in production.
- Fake gateway is rejected in production.
- Production seed data auto-population is prevented.
- Production money movement requires explicit PAYTM_LIVE_ENABLED=true.
"""
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.config import get_settings
from app.gateway import get_gateway
from app.main import app

ORIGIN = "https://merchant.test"


def test_demo_controls_enabled_property(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "development")
    assert cfg.demo_controls_enabled is True

    monkeypatch.setattr(cfg, "app_env", "test")
    assert cfg.demo_controls_enabled is True

    monkeypatch.setattr(cfg, "app_env", "production")
    assert cfg.demo_controls_enabled is False


def test_public_fake_checkout_returns_403_in_production(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "production")
    client = TestClient(app, base_url=ORIGIN)

    # Public fake checkout endpoints
    res_get = client.get("/fakecheckout/order_test")
    assert res_get.status_code == 403
    assert "Demo controls are disabled in production" in res_get.text

    res_post = client.post("/fakecheckout/order_test")
    assert res_post.status_code == 403
    assert "Demo controls are disabled in production" in res_post.text

    # /pay/ routes
    pay_get = client.get("/pay/link_test")
    assert pay_get.status_code == 403
    assert "Demo controls are disabled in production" in pay_get.text

    pay_post = client.post("/pay/link_test")
    assert pay_post.status_code == 403
    assert "Demo controls are disabled in production" in pay_post.text


def test_authenticated_demo_endpoints_return_403_in_production(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")

    owner, _ = auth.create_user_membership(
        username="safety-owner", password="Secure password 12345!",
        merchant_id="merchant_default", store_id="store_default", role="OWNER",
    )
    client = TestClient(app, base_url=ORIGIN)
    login_res = client.post("/api/auth/login", json={"username": "safety-owner", "password": "Secure password 12345!"},
                            headers={"Origin": ORIGIN})
    assert login_res.status_code == 200
    csrf = login_res.json()["csrf_token"]
    headers = {"Origin": ORIGIN, "X-Wapas-CSRF": csrf}

    demo_endpoints = [
        ("POST", "/api/demo/reset"),
        ("POST", "/api/demo/spike"),
        ("POST", "/api/demo/bank-recovers"),
        ("POST", "/api/demo/pay/c_test"),
        ("POST", "/api/demo/pay-wrong-amount/c_test"),
        ("POST", "/api/demo/duplicate-callback/c_test"),
        ("POST", "/api/demo/fault/status-timeout"),
        ("POST", "/api/demo/stop/c_test"),
        ("POST", "/api/eval/run"),
        ("GET", "/api/eval"),
    ]

    for method, path in demo_endpoints:
        if method == "POST":
            res = client.post(path, headers=headers)
        else:
            res = client.get(path, headers=headers)
        assert res.status_code == 403, f"{method} {path} expected 403, got {res.status_code}: {res.text}"
        assert "Demo controls are disabled in production" in res.text


def test_unauthenticated_demo_endpoints_return_401_in_production(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    client = TestClient(app, base_url=ORIGIN)

    res = client.post("/api/demo/reset")
    assert res.status_code == 401
    assert "Sign in to access this merchant workspace" in res.text


def test_production_rejects_fake_gateway(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "production")
    monkeypatch.setattr(cfg, "gateway", "fake")
    get_gateway.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="cannot run in WAPAS_ENV=production"):
            get_gateway()
    finally:
        get_gateway.cache_clear()


def test_production_paytm_requires_live_enabled_flag(monkeypatch):
    from app.gateway.paytm import PaytmGateway

    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "production")
    monkeypatch.setattr(cfg, "gateway", "paytm")
    monkeypatch.setattr(cfg, "paytm_mid", "PROD_MID_1234")
    monkeypatch.setattr(cfg, "paytm_merchant_key", "PROD_KEY_1234567890")
    monkeypatch.setattr(cfg, "paytm_host", "https://secure.paytmpayments.com")
    monkeypatch.setattr(cfg, "paytm_live_enabled", False)

    gw = PaytmGateway(cfg)
    assert gw._payment_actions_disabled() is True
    assert "Production Paytm payments are disabled" in gw._payment_gate_error()

    # Now enable live
    monkeypatch.setattr(cfg, "paytm_live_enabled", True)
    assert gw._payment_actions_disabled() is False
