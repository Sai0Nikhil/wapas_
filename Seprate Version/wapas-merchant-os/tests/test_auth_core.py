from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, select

from app import auth, auth_api, auth_models
from app.config import get_settings
from app.db import init_db, reset_engine, session
from app.models import Merchant, Store


@pytest.fixture()
def auth_db(tmp_path, monkeypatch):
    cfg = get_settings()
    monkeypatch.setenv("WAPAS_ENV", "test")
    monkeypatch.setattr(cfg, "database_url", f"sqlite:///{tmp_path / 'auth.db'}")
    reset_engine()
    init_db(drop=True)
    with session() as s:
        s.add(Merchant(id="merchant_two", name="Second Merchant"))
        s.add(Store(id="store_two", merchant_id="merchant_two", name="Second Store", slug="second-store"))
        s.commit()
    yield
    reset_engine()


def _auth_client(*, base_url="https://merchant.test"):
    app = FastAPI()
    app.include_router(auth_api.router)
    return TestClient(app, base_url=base_url)


def _login(client, payload):
    return client.post("/api/auth/login", json=payload, headers={"Origin": str(client.base_url).rstrip("/")})


def test_scrypt_password_hash_and_session_lifecycle(auth_db, monkeypatch):
    monkeypatch.setenv("WAPAS_ENV", "production")
    user, membership = auth.create_user_membership(
        username="Owner@Store.test", password="Correct Horse Battery 77!", 
        merchant_id="merchant_default", store_id="store_default", role="OWNER",
    )
    assert user.username == "owner@store.test"
    assert user.password_hash.startswith("scrypt$")
    assert "Correct Horse" not in user.password_hash
    assert auth.verify_password("Correct Horse Battery 77!", user.password_hash)
    assert not auth.verify_password("Wrong Password", user.password_hash)

    token, csrf, expires = auth.create_session(membership.id)
    identity = auth.resolve_session(token)
    assert identity is not None
    assert (identity.user_id, identity.membership_id, identity.merchant_id, identity.store_id,
            identity.store_slug, identity.role) == (
        user.id, membership.id, "merchant_default", "store_default", "default-store", "OWNER",
    )
    assert auth.session_csrf_valid(identity, token, csrf)
    assert not auth.session_csrf_valid(identity, "wrong-session", csrf)
    assert not auth.session_csrf_valid(identity, token, "wrong-csrf")
    assert expires > datetime.now(timezone.utc)
    assert auth.revoke_session(token)
    assert auth.resolve_session(token) is None
    assert not auth.revoke_session(token)


def test_login_requires_same_origin_and_returns_only_session_identity(auth_db, monkeypatch):
    monkeypatch.setenv("WAPAS_ENV", "development")
    user, membership = auth.create_user_membership(
        username="owner", password="Strong local password 1234!",
        merchant_id="merchant_default", store_id="store_default", role="OWNER",
    )
    c = _auth_client(base_url="http://merchant.test")
    bad_origin = c.post("/api/auth/login", json={"username": "owner", "password": "Strong local password 1234!"},
                        headers={"Origin": "http://attacker.test"})
    assert bad_origin.status_code == 403

    response = _login(c, {"username": "owner", "password": "Strong local password 1234!"})
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["username"] == "owner" and data["role"] == "OWNER"
    assert data["merchant_id"] == membership.merchant_id
    assert data["store_id"] == membership.store_id and data["store_slug"] == "default-store"
    assert data["csrf_token"] and user.password_hash not in response.text
    session_cookie = response.cookies.get(auth_api.SESSION_COOKIE)
    csrf_cookie = response.cookies.get(auth_api.CSRF_COOKIE)
    assert session_cookie and csrf_cookie == data["csrf_token"]
    assert "httponly" in response.headers.get("set-cookie", "").lower()

    current = c.get("/api/auth/session")
    assert current.status_code == 200
    assert current.json()["csrf_token"] == data["csrf_token"]
    logout = c.post("/api/auth/logout", headers={"Origin": "http://merchant.test",
                                                 "X-Wapas-CSRF": data["csrf_token"]})
    assert logout.status_code == 204
    assert c.get("/api/auth/session").json() == {"authenticated": False}


def test_membership_selection_requires_valid_password_and_binds_chosen_tenant(auth_db):
    user, first = auth.create_user_membership(
        username="multi", password="Correct multi store password!",
        merchant_id="merchant_default", store_id="store_default", role="OWNER",
    )
    with session() as s:
        s.add(auth_models.MerchantMembership(user_id=user.id, merchant_id="merchant_two",
                                             store_id="store_two", role="STAFF"))
        s.commit()
    c = _auth_client()
    wrong = _login(c, {"username": "multi", "password": "not the password"})
    assert wrong.status_code == 401
    assert not c.cookies.get(auth_api.SESSION_COOKIE)

    selection = _login(c, {"username": "multi", "password": "Correct multi store password!"})
    assert selection.status_code == 200
    assert selection.json()["needs_membership_selection"] is True
    options = selection.json()["memberships"]
    assert {item["merchant_id"] for item in options} == {"merchant_default", "merchant_two"}
    assert not c.cookies.get(auth_api.SESSION_COOKIE)

    chosen = _login(c, {"username": "multi", "password": "Correct multi store password!",
                        "membership_id": options[1]["id"]})
    assert chosen.status_code == 200
    assert chosen.json()["authenticated"] is True
    assert chosen.json()["membership_id"] == options[1]["id"]
    assert chosen.json()["merchant_id"] == options[1]["merchant_id"]
    assert chosen.json()["role"] == options[1]["role"]


def test_login_failures_are_durably_throttled_and_raw_identifiers_not_stored(auth_db):
    c = _auth_client()
    for _ in range(auth.LOGIN_FAILURE_LIMIT):
        response = _login(c, {"username": "missing.user", "password": "Wrong password 12345"})
        assert response.status_code == 401
    blocked = _login(c, {"username": "missing.user", "password": "Wrong password 12345"})
    assert blocked.status_code == 429
    with session() as s:
        rows = s.exec(select(auth_models.LoginThrottle)).all()
        assert len(rows) == 2
        assert all("missing.user" not in row.attempt_hash for row in rows)
        assert all(row.blocked_until is not None for row in rows)


def test_expiry_membership_revocation_and_cookie_secure_mode(auth_db, monkeypatch):
    monkeypatch.setenv("WAPAS_ENV", "production")
    user, membership = auth.create_user_membership(
        username="expire", password="Strong expiry password 98765",
        merchant_id="merchant_default", store_id="store_default", role="STAFF",
    )
    token, _, _ = auth.create_session(membership.id)
    with session() as s:
        row = s.get(auth_models.AuthSession, auth._sha256(token))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.add(row)
        s.commit()
    assert auth.resolve_session(token) is None

    c = _auth_client()
    response = _login(c, {"username": "expire", "password": "Strong expiry password 98765"})
    assert response.status_code == 200
    assert "secure" in response.headers.get("set-cookie", "").lower()


def test_local_bootstrap_is_development_loopback_only_and_idempotent(auth_db):
    kwargs = {"username": "local-owner", "password": "Strong local bootstrap password 12!",
              "merchant_id": "merchant_default", "store_id": "store_default", "app_env": "development"}
    with pytest.raises(PermissionError):
        auth.bootstrap_local_owner(**kwargs, remote_addr="203.0.113.3")
    with pytest.raises(PermissionError):
        auth.bootstrap_local_owner(**kwargs, remote_addr="127.0.0.1", forwarded_headers=("x-forwarded-for",))
    with pytest.raises(PermissionError):
        auth.bootstrap_local_owner(**{**kwargs, "app_env": "production"}, remote_addr="127.0.0.1")
    created = auth.bootstrap_local_owner(**kwargs, remote_addr="127.0.0.1")
    assert created is not None and created[1].role == "OWNER"
    assert auth.bootstrap_local_owner(**kwargs, remote_addr="127.0.0.1") is None
