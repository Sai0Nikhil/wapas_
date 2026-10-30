from fastapi.testclient import TestClient
from decimal import Decimal

from app import auth
from app.config import get_settings
from app.db import session
from app.main import app
from app.models import AuditEvent
from app.merchant_os_models import Product
from sqlmodel import select


ORIGIN = "https://merchant.test"


def test_sarkar_uses_saved_stock_and_one_time_session_bound_confirmation(db, monkeypatch):
    monkeypatch.setenv("WAPAS_ENV", "production")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    owner, membership = auth.create_user_membership(
        username="sarkar-owner", password="Secure owner password 2026!",
        merchant_id="merchant_default", store_id="store_default", role="OWNER",
    )
    client = TestClient(app, base_url=ORIGIN)
    signed_in = client.post("/api/auth/login", json={"username": owner.username,
                              "password": "Secure owner password 2026!"}, headers={"Origin": ORIGIN})
    assert signed_in.status_code == 200
    csrf = signed_in.json()["csrf_token"]
    headers = {"Origin": ORIGIN, "X-Wapas-CSRF": csrf}
    created = client.post("/api/merchant/catalog/products", json={
        "name": "Basmati rice", "sku": "RICE-1", "unit": "kg", "unit_price_paise": 8000,
        "opening_stock": "2",
    }, headers=headers)
    assert created.status_code == 201

    inspected = client.post("/api/merchant/sarkar/ask", json={"message": "Show stock for rice"}, headers=headers)
    assert inspected.status_code == 200
    assert inspected.json()["tool_trace"][0]["tool"] == "inspect_stock"
    assert inspected.json()["data"]["products"][0]["available"] == "2.000"

    prepared = client.post("/api/merchant/sarkar/ask", json={
        "message": "We received 5 kg of rice",
    }, headers=headers)
    assert prepared.status_code == 200
    action = prepared.json()["confirmation"]
    assert prepared.json()["status"] == "NEEDS_CONFIRMATION"
    with session() as s:
        product_before = s.get(Product, created.json()["id"])
        assert product_before is not None
        assert s.exec(select(AuditEvent).where(AuditEvent.action == "sarkar.action_prepared")).first()

    # A second browser session for the same user cannot use the first session's approval.
    raw_session, second_csrf, _expires = auth.create_session(membership.id)
    second = TestClient(app, base_url=ORIGIN)
    second.cookies.set("wapas_session", raw_session)
    second.cookies.set("wapas_csrf", second_csrf)
    denied = second.post(f"/api/merchant/sarkar/actions/{action['action_id']}/confirm",
                         json={"confirmation_token": action["token"]},
                         headers={"Origin": ORIGIN, "X-Wapas-CSRF": second_csrf})
    assert denied.status_code == 403

    confirmed = client.post(f"/api/merchant/sarkar/actions/{action['action_id']}/confirm",
                            json={"confirmation_token": action["token"]}, headers=headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "EXECUTED"
    assert confirmed.json()["data"]["on_hand"] == "7.000"
    replay = client.post(f"/api/merchant/sarkar/actions/{action['action_id']}/confirm",
                         json={"confirmation_token": action["token"]}, headers=headers)
    assert replay.status_code == 409
    assert client.get("/api/merchant/catalog/products").json()[0]["on_hand"] == "7.000"


def test_sarkar_ambiguous_receipt_does_not_mutate_stock(db):
    client = TestClient(app, headers={"X-Wapas-Console": "1"})
    for sku in ("RICE-A", "RICE-B"):
        assert client.post("/api/merchant/catalog/products", json={
            "name": "Rice " + sku[-1], "sku": sku, "unit": "kg", "unit_price_paise": 8000,
            "opening_stock": "1",
        }).status_code == 201
    result = client.post("/api/merchant/sarkar/ask", json={"message": "received 3 kg rice"})
    assert result.status_code == 200
    assert result.json()["status"] == "NEEDS_CLARIFICATION"
    assert len(result.json()["candidates"]) == 2
    assert all(row["on_hand"] == "1.000" for row in client.get("/api/merchant/catalog/products").json())


def test_typed_tool_registry_declares_contracts_and_executes_tenant_scoped_reads(db):
    from app import inventory
    from app.models import Merchant, Store

    client = TestClient(app, headers={"X-Wapas-Console": "1"})
    product = client.post("/api/merchant/catalog/products", json={
        "name":"Default tea", "sku":"DEFAULT-TEA", "unit":"each", "unit_price_paise":100,
        "opening_stock":"0", "low_stock_threshold":"2",
    }).json()
    with session() as s:
        s.add(Merchant(id="merchant_other", name="Other"))
        s.add(Store(id="store_other", merchant_id="merchant_other", name="Other Store", slug="other-store"))
        inventory.create_product(s, merchant_id="merchant_other", store_id="store_other",
                                 product_id="other-product", name="Private tea", unit="each",
                                 unit_price_paise=999, opening_stock=9, sku="PRIVATE-TEA")
        s.commit()

    contracts = client.get("/api/merchant/sarkar/tools")
    assert contracts.status_code == 200
    tools = {tool["name"]: tool for tool in contracts.json()["tools"]}
    expected = {"inspect_stock", "inspect_khata", "inspect_khata_history", "inspect_orders",
                "inspect_recent_bills", "inspect_low_stock", "summarize_verified_payments",
                "explain_payment_state", "inspect_business_summary", "inspect_unmet_demand",
                "prepare_stock_receipt", "confirm_stock_receipt"}
    assert expected <= set(tools)
    assert tools["prepare_stock_receipt"]["approval_required"] is True
    assert tools["prepare_stock_receipt"]["classification"] == "MUTATION_PREPARATION"
    assert tools["inspect_stock"]["input_schema"]["properties"]
    assert tools["inspect_stock"]["output_schema"]["properties"]

    invoked = client.post("/api/merchant/sarkar/tools/inspect_stock", json={"arguments":{"query":"tea"}})
    assert invoked.status_code == 200
    response = invoked.json()
    assert [row["id"] for row in response["data"]["products"]] == [product["id"]]
    assert response["correlation_id"].startswith("sarkar_tool_")
    assert response["tool_trace"][0]["version"] == "1.0"
    with session() as s:
        trace = s.exec(select(AuditEvent).where(
            AuditEvent.action == "sarkar.tool_executed",
            AuditEvent.entity_id == response["correlation_id"],
        )).one()
        assert trace.merchant_id == "merchant_default"
        assert trace.store_id == "store_default"
        assert trace.actor_type == "merchant"
        assert '"tool":"inspect_stock"' in trace.details_json
        assert '"input_sha256"' in trace.details_json
        assert '"products_count":1' in trace.details_json
        assert "Default tea" not in trace.details_json
    invalid = client.post("/api/merchant/sarkar/tools/inspect_recent_bills",
                          json={"arguments":{"limit":500,"sql":"select *"}})
    assert invalid.status_code == 422


def test_sarkar_staff_can_use_only_scoped_read_tools(db, monkeypatch):
    from app import inventory
    from app.models import Merchant, Store

    monkeypatch.setattr(get_settings(), "app_env", "production")

    with session() as s:
        s.add(Merchant(id="merchant_staff", name="Staff Merchant"))
        s.add(Store(id="store_staff", merchant_id="merchant_staff", name="Staff Store", slug="staff-store"))
        inventory.create_product(s, merchant_id="merchant_staff", store_id="store_staff",
                                 product_id="staff-product", name="Staff product", unit="each",
                                 unit_price_paise=100, opening_stock=1, sku="STAFF-PRODUCT")
        s.commit()
    user, membership = auth.create_user_membership(
        username="sarkar-staff", password="Secure staff password 2026!",
        merchant_id="merchant_staff", store_id="store_staff", role="STAFF",
    )
    raw_session, csrf, _expires = auth.create_session(membership.id)
    client = TestClient(app, base_url=ORIGIN)
    client.cookies.set("wapas_session", raw_session)
    client.cookies.set("wapas_csrf", csrf)
    headers = {"Origin": ORIGIN, "X-Wapas-CSRF": csrf}

    visible_tools = client.get("/api/merchant/sarkar/tools").json()["tools"]
    names = {tool["name"] for tool in visible_tools}
    assert "inspect_stock" in names and "inspect_khata" not in names
    result = client.post("/api/merchant/sarkar/tools/inspect_stock", json={"arguments":{}}, headers=headers)
    assert result.status_code == 200
    assert [row["id"] for row in result.json()["data"]["products"]] == ["staff-product"]
    assert client.post("/api/merchant/sarkar/tools/inspect_khata", json={"arguments":{}}, headers=headers).status_code == 403
    assert client.post("/api/merchant/sarkar/tools/prepare_stock_receipt",
                       json={"arguments":{"message":"received 2 each staff product"}}, headers=headers).status_code == 403


def test_sarkar_approval_expiry_payload_tampering_and_stale_stock_are_rejected(db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.inventory import adjust_stock
    from app.sarkar_models import SarkarAction

    client = TestClient(app, headers={"X-Wapas-Console": "1"})
    product = client.post("/api/merchant/catalog/products", json={
        "name":"Rice", "sku":"RICE-APPROVAL", "unit":"kg", "unit_price_paise":100,
        "opening_stock":"2",
    }).json()

    prepared = client.post("/api/merchant/sarkar/ask", json={"message":"received 1 kg rice"}).json()
    action = prepared["confirmation"]
    with session() as s:
        row = s.get(SarkarAction, action["action_id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.add(row); s.commit()
    expired = client.post(f"/api/merchant/sarkar/actions/{action['action_id']}/confirm",
                          json={"confirmation_token":action["token"]})
    assert expired.status_code == 410

    stale = client.post("/api/merchant/sarkar/ask", json={"message":"received 1 kg rice"}).json()["confirmation"]
    with session() as s:
        adjust_stock(s, merchant_id="merchant_default", store_id="store_default",
                     product_id=product["id"], delta=Decimal("1"), kind="receipt",
                     source_ref="concurrent-stock-change", reason="Concurrent receipt",
                     idempotency_key="sarkar-stale-stock-adjustment")
        s.commit()
    rejected_stale = client.post(f"/api/merchant/sarkar/actions/{stale['action_id']}/confirm",
                                 json={"confirmation_token":stale["token"]})
    assert rejected_stale.status_code == 409

    modified = client.post("/api/merchant/sarkar/ask", json={"message":"received 1 kg rice"}).json()["confirmation"]
    with session() as s:
        row = s.get(SarkarAction, modified["action_id"])
        row.payload_json = row.payload_json.replace('"quantity":"1"', '"quantity":"2"')
        s.add(row); s.commit()
    rejected_payload = client.post(f"/api/merchant/sarkar/actions/{modified['action_id']}/confirm",
                                   json={"confirmation_token":modified["token"]})
    assert rejected_payload.status_code == 409


def test_sarkar_tool_timeout_enforced(db, monkeypatch):
    import time
    from app import sarkar

    client = TestClient(app, headers={"X-Wapas-Console": "1"})

    def _slow_handler(s, args):
        time.sleep(0.3)
        return sarkar.ToolEnvelope(status="OK", message="Done", data={})

    slow_spec = sarkar.ToolSpec(
        name="test_slow_tool", version="1.0", input_model=sarkar.EmptyInput,
        output_model=sarkar.ToolEnvelope, handler=_slow_handler, required_role="STAFF",
        permission="test", ownership_rule="test", classification="READ_ONLY",
        approval_required=False, idempotency_required=False, timeout_seconds=0.05,
        max_retries=0, post_execution_verification="test",
    )
    monkeypatch.setitem(sarkar.TOOL_REGISTRY, "test_slow_tool", slow_spec)

    response = client.post("/api/merchant/sarkar/tools/test_slow_tool", json={"arguments": {}})
    assert response.status_code == 504
    assert "exceeded deadline" in response.json()["detail"]

