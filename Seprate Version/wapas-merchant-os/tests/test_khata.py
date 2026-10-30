from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient
import pytest

from app.db import session
from app.main import app
from app.models import Customer, Merchant, Store
from app.khata_models import KhataAccount, KhataLedgerEntry


def _client():
    return TestClient(app, headers={"X-Wapas-Console": "1"})


def _issued_bill(client, *, phone="9876543210", name="Asha"):
    product = client.post("/api/merchant/catalog/products", json={
        "name": "Soap", "sku": "SOAP-1", "unit": "each", "unit_price_paise": 12500,
        "opening_stock": "10",
    }).json()
    bill = client.post("/api/merchant/bills", json={
        "idempotency_key": "khata-bill-draft-01", "customer_name": name, "customer_phone": phone,
    }).json()
    assert client.put(f"/api/merchant/bills/{bill['id']}/lines/{product['id']}",
                      json={"quantity": "2"}).status_code == 200
    issued = client.post(f"/api/merchant/bills/{bill['id']}/issue")
    assert issued.status_code == 200
    return issued.json()


def test_counter_bill_credit_and_manual_repayments_are_ledgered_once(db):
    c = _client()
    bill = _issued_bill(c)
    assert bill["payment_state"] == "NOT_RECORDED"
    assert bill["khata_state"] == "NOT_ON_KHATA"

    added = c.post(f"/api/merchant/bills/{bill['id']}/khata", json={"note": "Due next week"})
    assert added.status_code == 200
    assert added.json()["credit_state"] == "ON_KHATA"
    assert added.json()["payment_state"] == "NOT_RECORDED"
    account = added.json()["account"]
    assert account["outstanding_paise"] == 25000
    repeated = c.post(f"/api/merchant/bills/{bill['id']}/khata", json={})
    assert repeated.status_code == 200
    assert repeated.json()["account"]["outstanding_paise"] == 25000
    assert c.get(f"/api/merchant/bills/{bill['id']}").json()["khata_state"] == "ON_KHATA"

    path = f"/api/merchant/khata/accounts/{account['id']}/repayments"
    body = {"amount_paise": 10000, "method": "CASH", "idempotency_key": "repay-asha-001",
            "confirm_received": True, "note": "Cash at counter"}
    refused_without_confirmation = c.post(path, json={**body, "confirm_received": False})
    assert refused_without_confirmation.status_code == 409
    first = c.post(path, json=body)
    retry = c.post(path, json=body)
    assert first.status_code == retry.status_code == 200
    assert first.json()["entry"]["id"] == retry.json()["entry"]["id"]
    assert first.json()["outstanding_paise"] == 15000
    assert first.json()["recording_basis"] == "MERCHANT_CONFIRMED_RECEIPT"
    assert c.post(path, json={**body, "amount_paise": 16000,
                              "idempotency_key": "repay-asha-002"}).status_code == 409

    account_detail = c.get(f"/api/merchant/khata/accounts/{account['id']}").json()
    assert account_detail["outstanding_paise"] == 15000
    assert [entry["delta_paise"] for entry in account_detail["entries"]] == [25000, -10000]

    reversal = c.post(f"/api/merchant/khata/entries/{first.json()['entry']['id']}/reverse",
                      json={"reason": "Wrongly entered cash receipt"})
    assert reversal.status_code == 200
    assert reversal.json()["outstanding_paise"] == 25000
    assert c.post(f"/api/merchant/khata/entries/{first.json()['entry']['id']}/reverse",
                  json={"reason": "Duplicate reversal attempt"}).json()["entry"]["id"] == reversal.json()["entry"]["id"]
    assert c.post(f"/api/merchant/khata/entries/{added.json()['entry']['id']}/reverse",
                  json={"reason": "Remove credit after repayment correction"}).status_code == 200
    final = c.get(f"/api/merchant/khata/accounts/{account['id']}").json()
    assert final["outstanding_paise"] == 0

    with session() as s:
        projection = s.get(KhataAccount, account["id"])
        ledger_total = sum(row[0] for row in s.execute(
            text("SELECT delta_paise FROM khataledgerentry WHERE account_id=:id"), {"id": account["id"]}
        ).all())
        assert projection.balance_paise == ledger_total == final["outstanding_paise"]


def test_counter_bill_cannot_be_both_pending_payment_and_khata_credit(db):
    c = _client()
    bill = _issued_bill(c)
    payment = c.post(f"/api/merchant/bills/{bill['id']}/payments",
                     json={"idempotency_key": "counter-pending-link-0001"})
    assert payment.status_code == 200 and payment.json()["status"] == "PENDING"
    assert c.post(f"/api/merchant/bills/{bill['id']}/khata", json={}).status_code == 409


def test_counter_bill_on_khata_cannot_start_a_payment_link(db):
    c = _client()
    bill = _issued_bill(c)
    added = c.post(f"/api/merchant/bills/{bill['id']}/khata", json={})
    assert added.status_code == 200
    payment = c.post(f"/api/merchant/bills/{bill['id']}/payments",
                     json={"idempotency_key": "counter-khata-link-0001"})
    assert payment.status_code == 409


def test_khata_ledger_is_immutable_and_scoped(db):
    c = _client()
    bill = _issued_bill(c, phone="9123456789", name="Bina")
    account = c.post(f"/api/merchant/bills/{bill['id']}/khata", json={}).json()["account"]
    with session() as s:
        entry = s.execute(text("SELECT id FROM khataledgerentry WHERE account_id=:id"),
                          {"id": account["id"]}).one()[0]
        s.add(Merchant(id="merchant_other", name="Other"))
        s.add(Store(id="store_other", merchant_id="merchant_other", name="Other Store", slug="other-store"))
        s.add(Customer(id="other-customer", merchant_id="merchant_other", name="Other", phone="9000000099"))
        s.add(KhataAccount(id="other-khata", merchant_id="merchant_other", store_id="store_other",
                           customer_id="other-customer"))
        s.add(KhataLedgerEntry(id="other-entry", merchant_id="merchant_other", store_id="store_other",
                              account_id="other-khata", entry_type="CREDIT_GIVEN", delta_paise=100,
                              source_type="fixture", idempotency_key="other-ledger-1"))
        s.commit()
        with pytest.raises(IntegrityError):
            s.execute(text("UPDATE khataledgerentry SET delta_paise=5 WHERE id=:id"), {"id": entry})
            s.commit()
    assert c.get("/api/merchant/khata/accounts/other-khata").status_code == 404


def test_khata_customer_phone_normalization(db):
    c = _client()
    # Phone formatted with +91 and spaces
    bill = _issued_bill(c, phone="+91 98765 43210", name="Ramesh Kumar")
    added = c.post(f"/api/merchant/bills/{bill['id']}/khata", json={})
    assert added.status_code == 200
    account_id = added.json()["account"]["id"]

    # View account and verify phone is canonical 10 digits
    acc_res = c.get(f"/api/merchant/khata/accounts/{account_id}")
    assert acc_res.status_code == 200
    assert acc_res.json()["account"]["phone"] == "9876543210"

