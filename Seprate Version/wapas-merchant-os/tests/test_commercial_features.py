from decimal import Decimal
from fastapi.testclient import TestClient

from app.db import session
from app.inventory import create_product
from app.main import app


def _client():
    return TestClient(app, headers={"X-Wapas-Console": "1"})


def test_bill_receipt_and_whatsapp_sharing(db):
    c = _client()
    with session() as s:
        create_product(s, merchant_id="merchant_default", store_id="store_default",
                       product_id="prod-soap", name="Bath Soap", unit="each", unit_price_paise=4500,
                       opening_stock=Decimal("10"), sku="SOAP-01")
        s.commit()

    bill = c.post("/api/merchant/bills", json={"customer_name": "Rohan Verma", "customer_phone": "9876543210"}).json()
    c.put(f"/api/merchant/bills/{bill['id']}/lines/prod-soap", json={"quantity": "2"})
    c.post(f"/api/merchant/bills/{bill['id']}/issue")

    receipt = c.get(f"/api/merchant/bills/{bill['id']}/receipt")
    assert receipt.status_code == 200
    assert "text/html" in receipt.headers["content-type"]
    html = receipt.text
    assert "Bath Soap" in html
    assert "₹90.00" in html
    assert "Print Receipt" in html
    assert "https://wa.me/9876543210" in html


def test_khata_debt_aging_and_statement_csv(db):
    c = _client()
    with session() as s:
        create_product(s, merchant_id="merchant_default", store_id="store_default",
                       product_id="prod-rice-5k", name="Basmati Rice 5kg", unit="bag", unit_price_paise=35000,
                       opening_stock=Decimal("5"), sku="RICE-5K")
        s.commit()

    bill = c.post("/api/merchant/bills", json={"customer_name": "Anil Gupta", "customer_phone": "9123456780"}).json()
    c.put(f"/api/merchant/bills/{bill['id']}/lines/prod-rice-5k", json={"quantity": "1"})
    c.post(f"/api/merchant/bills/{bill['id']}/issue")

    added = c.post(f"/api/merchant/bills/{bill['id']}/khata", json={})
    assert added.status_code == 200
    account_id = added.json()["account"]["id"]

    aging = c.get("/api/merchant/khata/aging")
    assert aging.status_code == 200
    data = aging.json()
    assert data["total_outstanding_paise"] >= 35000
    assert data["account_count"] >= 1
    assert data["current_paise"] >= 35000

    statement = c.get(f"/api/merchant/khata/accounts/{account_id}/statement.csv")
    assert statement.status_code == 200
    assert "text/csv" in statement.headers["content-type"]
    assert "Date,Entry ID,Type,Basis" in statement.text
    assert "CREDIT_GIVEN" in statement.text


def test_merchant_sales_and_audit_csv_exports(db):
    c = _client()
    sales = c.get("/api/merchant/reports/sales.csv")
    assert sales.status_code == 200
    assert "text/csv" in sales.headers["content-type"]
    assert "Bill Number,Created At,State" in sales.text

    audit_res = c.get("/api/merchant/reports/audit.csv")
    assert audit_res.status_code == 200
    assert "text/csv" in audit_res.headers["content-type"]
    assert "Timestamp,Action,Entity Type" in audit_res.text
