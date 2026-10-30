import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select

from app import auth, auth_api, merchant_api
from app.auth_models import AuthSession, MerchantMembership, User
from app.config import get_settings
from app.db import init_db, reset_engine, session
from app.main import app
from app.models import AuditEvent, Merchant, Store

ORIGIN = "https://merchant.test"


@pytest.fixture()
def clean_db(tmp_path, monkeypatch):
    cfg = get_settings()
    monkeypatch.setenv("WAPAS_ENV", "production")
    monkeypatch.setattr(cfg, "app_env", "production")
    monkeypatch.setattr(cfg, "database_url", f"sqlite:///{tmp_path / 'onboard_test.db'}")
    reset_engine()
    init_db(drop=True)
    yield
    reset_engine()


def _login_client(client, username, password, origin=ORIGIN):
    res = client.post("/api/auth/login", json={"username": username, "password": password},
                      headers={"Origin": origin})
    assert res.status_code == 200, res.text
    data = res.json()
    csrf = data["csrf_token"]
    headers = {"Origin": origin, "X-Wapas-CSRF": csrf}
    return headers, data


def test_merchant_self_serve_registration(clean_db):
    client = TestClient(app, base_url=ORIGIN)

    # 1. Invalid password complexity fails
    bad_pw = client.post("/api/auth/register", json={
        "business_name": "Test Kirana",
        "store_name": "Koramangala Branch",
        "username": "new_owner",
        "password": "short",
    }, headers={"Origin": ORIGIN})
    assert bad_pw.status_code in {400, 422}

    # 2. Cross-origin request fails
    cross_origin = client.post("/api/auth/register", json={
        "business_name": "Test Kirana",
        "store_name": "Koramangala Branch",
        "username": "new_owner",
        "password": "ValidPassword2026!",
    }, headers={"Origin": "https://evil.test"})
    assert cross_origin.status_code == 403

    # 3. Valid registration succeeds
    res = client.post("/api/auth/register", json={
        "business_name": "Test Kirana",
        "store_name": "Koramangala Branch",
        "username": "new_owner",
        "password": "ValidPassword2026!",
        "city": "Bengaluru",
        "phone": "9876543210",
    }, headers={"Origin": ORIGIN})
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["authenticated"] is True
    assert data["username"] == "new_owner"
    assert data["role"] == "OWNER"
    assert data["store_slug"] == "koramangala-branch"
    assert data["merchant_name"] == "Test Kirana"
    assert data["store_name"] == "Koramangala Branch"
    assert client.cookies.get(auth_api.SESSION_COOKIE)
    assert client.cookies.get(auth_api.CSRF_COOKIE) == data["csrf_token"]

    # 4. Check audit log
    with session() as s:
        audit_event = s.exec(select(AuditEvent).where(
            AuditEvent.action == "MERCHANT_REGISTERED",
            AuditEvent.merchant_id == data["merchant_id"],
        )).first()
        assert audit_event is not None
        assert "koramangala-branch" in audit_event.details_json

    # 5. Duplicate username registration fails with 409
    dup = client.post("/api/auth/register", json={
        "business_name": "Another Store",
        "store_name": "Indiranagar",
        "username": "new_owner",
        "password": "ValidPassword2026!",
    }, headers={"Origin": ORIGIN})
    assert dup.status_code == 409

    # 6. Store slug collision avoids overwrite
    res2 = client.post("/api/auth/register", json={
        "business_name": "Second Branch",
        "store_name": "Koramangala Branch",
        "username": "second_owner",
        "password": "ValidPassword2026!",
    }, headers={"Origin": ORIGIN})
    assert res2.status_code == 201
    assert res2.json()["store_slug"] != "koramangala-branch"
    assert res2.json()["store_slug"].startswith("koramangala-branch-")


def test_staff_management_and_rbac(clean_db):
    client = TestClient(app, base_url=ORIGIN)

    # Register owner
    reg = client.post("/api/auth/register", json={
        "business_name": "Alpha Retail",
        "store_name": "Main Store",
        "username": "alpha_owner",
        "password": "AlphaPassword2026!",
    }, headers={"Origin": ORIGIN})
    assert reg.status_code == 201
    owner_csrf = reg.json()["csrf_token"]
    owner_headers = {"Origin": ORIGIN, "X-Wapas-CSRF": owner_csrf}

    # List staff as owner
    list_res = client.get("/api/merchant/staff", headers=owner_headers)
    assert list_res.status_code == 200
    staff_list = list_res.json()["staff"]
    assert len(staff_list) == 1
    assert staff_list[0]["username"] == "alpha_owner"
    assert staff_list[0]["role"] == "OWNER"

    # Add staff member
    add_res = client.post("/api/merchant/staff", json={
        "username": "alpha_staff",
        "password": "StaffPassword2026!",
        "role": "STAFF",
    }, headers=owner_headers)
    assert add_res.status_code == 201
    staff_data = add_res.json()
    assert staff_data["username"] == "alpha_staff"
    assert staff_data["role"] == "STAFF"
    assert staff_data["is_active"] is True
    staff_membership_id = staff_data["membership_id"]

    # Now login as the staff member
    staff_client = TestClient(app, base_url=ORIGIN)
    staff_headers, staff_login = _login_client(staff_client, "alpha_staff", "StaffPassword2026!")
    assert staff_login["role"] == "STAFF"

    # Staff member cannot access staff management API (RBAC 403)
    forbidden_list = staff_client.get("/api/merchant/staff", headers=staff_headers)
    assert forbidden_list.status_code == 403

    forbidden_add = staff_client.post("/api/merchant/staff", json={
        "username": "another_staff",
        "password": "StaffPassword2026!",
        "role": "STAFF",
    }, headers=staff_headers)
    assert forbidden_add.status_code == 403

    # Owner cannot deactivate only owner
    deactivate_owner = client.patch(f"/api/merchant/staff/{staff_list[0]['membership_id']}", json={
        "is_active": False,
    }, headers=owner_headers)
    assert deactivate_owner.status_code == 400
    assert "only active owner" in deactivate_owner.json()["detail"]

    # Owner deactivates staff member
    deact_res = client.patch(f"/api/merchant/staff/{staff_membership_id}", json={
        "is_active": False,
    }, headers=owner_headers)
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # Deactivated staff member's active session is revoked immediately
    check_session = staff_client.get("/api/auth/session")
    assert check_session.json()["authenticated"] is False


def test_membership_listing_and_switching(clean_db):
    client = TestClient(app, base_url=ORIGIN)

    # Register user with store 1
    reg1 = client.post("/api/auth/register", json={
        "business_name": "Multi Mart 1",
        "store_name": "Store One",
        "username": "multichannel_user",
        "password": "UserPassword2026!",
    }, headers={"Origin": ORIGIN})
    assert reg1.status_code == 201
    membership1_id = reg1.json()["membership_id"]
    csrf1 = reg1.json()["csrf_token"]
    headers1 = {"Origin": ORIGIN, "X-Wapas-CSRF": csrf1}

    # Add second store to same user directly
    with session() as s:
        m2 = Merchant(id="mer_two", name="Multi Mart 2")
        st2 = Store(id="sto_two", merchant_id="mer_two", name="Store Two", slug="store-two")
        s.add(m2)
        s.add(st2)
        s.flush()
        user = s.exec(select(User).where(User.username == "multichannel_user")).first()
        mbr2 = MerchantMembership(
            user_id=user.id, merchant_id="mer_two", store_id="sto_two", role="OWNER",
        )
        s.add(mbr2)
        s.commit()
        membership2_id = mbr2.id

    # List memberships
    memberships_res = client.get("/api/auth/memberships", headers=headers1)
    assert memberships_res.status_code == 200
    m_list = memberships_res.json()["memberships"]
    assert len(m_list) == 2
    assert {m["store_slug"] for m in m_list} == {"store-one", "store-two"}

    # Switch membership to Store Two
    switch_res = client.post("/api/auth/switch-membership", json={
        "membership_id": membership2_id,
    }, headers=headers1)
    assert switch_res.status_code == 200
    switch_data = switch_res.json()
    assert switch_data["authenticated"] is True
    assert switch_data["store_slug"] == "store-two"
    assert switch_data["merchant_name"] == "Multi Mart 2"
    assert switch_data["store_name"] == "Store Two"
    assert switch_data["membership_id"] == membership2_id

    # Verify session reflects new active store
    sess = client.get("/api/auth/session")
    assert sess.json()["store_slug"] == "store-two"
    assert sess.json()["merchant_id"] == "mer_two"
