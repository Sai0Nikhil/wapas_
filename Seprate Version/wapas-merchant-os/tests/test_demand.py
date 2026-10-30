from fastapi.testclient import TestClient

from app.main import app
from app.db import session
from app.demand_models import DemandEvent
from app.inventory import create_product
from app.demand import opportunity_pulse
from app.models import Merchant, Store
from sqlmodel import select


def test_public_search_records_only_repeated_stockout_or_missing_queries(db, monkeypatch):
    import app.commerce as commerce

    client = TestClient(app, headers={"X-Wapas-Console": "1"})
    with session() as s:
        create_product(s, merchant_id="merchant_default", store_id="store_default",
                       product_id="rice-demand", name="Basmati rice", unit="kg",
                       unit_price_paise=9000, opening_stock=0, sku="RICE")
        s.commit()

    clock = {"value": 900}
    monkeypatch.setattr(commerce.time, "time", lambda: clock["value"])
    missing = client.get("/api/public/stores/default-store/search", params={"q": "almond milk"})
    assert missing.status_code == 200 and missing.json()["outcome"] == "NO_MATCH"
    client.get("/api/public/stores/default-store/search", params={"q": "almond milk"})
    clock["value"] += 900
    client.get("/api/public/stores/default-store/search", params={"q": "almond milk"})
    clock["value"] += 900
    sold_out = client.get("/api/public/stores/default-store/search", params={"q": "basmati rice"})
    assert sold_out.status_code == 200
    assert sold_out.json()["outcome"] == "OUT_OF_STOCK"
    assert sold_out.json()["products"][0]["availability"] == "OUT_OF_STOCK"

    with session() as s:
        events = s.exec(select(DemandEvent)).all()
        assert len(events) == 3  # a duplicate in one 15-minute bucket was collapsed
        assert all(not hasattr(event, "phone") for event in events)
        pulse = opportunity_pulse(s, merchant_id="merchant_default", store_id="store_default", days=30)
        assert pulse["status"] == "AVAILABLE"
        assert {(row["query"], row["outcome"], row["sample_count"]) for row in pulse["insights"]} == {
            ("almond milk", "NO_MATCH", 2),
        }
        # A single stockout is retained as evidence, but is not promoted to a repeated-demand insight.
        assert [(row["query"], row["sample_count"]) for row in pulse["insights"]] == [("almond milk", 2)]


def test_opportunity_pulse_empty_state_and_tenant_scoping(db):
    with session() as s:
        assert opportunity_pulse(s, merchant_id="merchant_default", store_id="store_default")["message"] == "Not enough data yet."
        s.add(Merchant(id="merchant_other", name="Other"))
        s.add(Store(id="store_other", merchant_id="merchant_other", name="Other Store", slug="other-store"))
        s.flush()
        s.add(DemandEvent(merchant_id="merchant_other", store_id="store_other", query_text="private item",
                          outcome="NO_MATCH", event_key="private-event-1"))
        s.commit()
        assert opportunity_pulse(s, merchant_id="merchant_default", store_id="store_default")["insights"] == []


def test_opportunity_pulse_business_metrics_and_financial_breakdown(db):
    from datetime import datetime, timezone
    import uuid
    from app.billing_models import Bill
    from app.commerce_models import StoreOrder
    from app.khata_models import KhataAccount
    from app.models import Customer, Payment

    now_utc = datetime.now(timezone.utc)
    with session() as s:
        # 1. Products: one low stock, one healthy
        create_product(s, merchant_id="merchant_default", store_id="store_default",
                       product_id="prod-low", name="Low Stock Sugar", unit="kg",
                       unit_price_paise=4000, opening_stock=1, low_stock_threshold=5, sku="SUGAR-L")
        create_product(s, merchant_id="merchant_default", store_id="store_default",
                       product_id="prod-high", name="Abundant Salt", unit="kg",
                       unit_price_paise=2000, opening_stock=50, low_stock_threshold=5, sku="SALT-H")

        # 2. Payments: one verified Paytm, one pending, one fake (should not count as verified paytm)
        s.add(Payment(id="pay_verified_" + uuid.uuid4().hex[:8],
                      merchant_id="merchant_default", store_id="store_default",
                      order_id="ord_1", customer_id="cust_1", amount_paise=50000,
                      provider="paytm", status="SUCCESS", verified_at=now_utc, bank="HDFC"))
        s.add(Payment(id="pay_pending_" + uuid.uuid4().hex[:8],
                      merchant_id="merchant_default", store_id="store_default",
                      order_id="ord_2", customer_id="cust_1", amount_paise=20000,
                      provider="paytm", status="PENDING", created_at=now_utc, bank="HDFC"))
        s.add(Payment(id="pay_fake_" + uuid.uuid4().hex[:8],
                      merchant_id="merchant_default", store_id="store_default",
                      order_id="ord_3", customer_id="cust_1", amount_paise=30000,
                      provider="fake", status="SUCCESS", verified_at=now_utc, bank="TEST"))

        # 3. Khata customer and account
        s.add(Customer(id="cust_khata_1", merchant_id="merchant_default", name="Khata User", phone="9876543210"))
        s.add(KhataAccount(id="acc_khata_1", merchant_id="merchant_default", store_id="store_default",
                           customer_id="cust_khata_1", balance_paise=12000, status="ACTIVE"))

        # 4. Store order: paid & unfulfilled
        s.add(StoreOrder(id="order_unfulfilled_" + uuid.uuid4().hex[:8],
                         merchant_id="merchant_default", store_id="store_default",
                         customer_id="cust_1", idempotency_key="idemp_ord_1",
                         token_hash="hash_" + uuid.uuid4().hex[:12],
                         status="PAID", fulfillment_state="UNFULFILLED",
                         amount_paise=45000, created_at=now_utc, paid_at=now_utc))

        # 5. Issued bill
        s.add(Bill(id="bill_issued_" + uuid.uuid4().hex[:8],
                   merchant_id="merchant_default", store_id="store_default",
                   bill_number="BILL-001", state="ISSUED", payment_state="NOT_RECORDED",
                   total_paise=75000, issued_at=now_utc))

        s.commit()

        pulse = opportunity_pulse(s, merchant_id="merchant_default", store_id="store_default", days=30)

        # Assert all indicators are correctly computed
        assert pulse["low_stock_summary"]["low_stock_count"] == 1
        assert pulse["sales_summary"]["verified_payment_count"] == 1
        assert pulse["sales_summary"]["verified_total_paise"] == 50000
        assert pulse["khata_summary"]["customer_count"] == 1
        assert pulse["khata_summary"]["outstanding_total_paise"] == 12000
        assert pulse["pending_fulfillment_summary"]["pending_count"] == 1
        assert pulse["pending_fulfillment_summary"]["pending_total_paise"] == 45000

        # Assert financial breakdown
        fb = pulse["financial_breakdown"]
        assert fb["gross_bill_issued_total_paise"] == 75000
        assert fb["gross_bill_issued_count"] == 1
        assert fb["verified_collected_total_paise"] == 50000
        assert fb["verified_collected_count"] == 1
        assert fb["outstanding_credit_total_paise"] == 12000
        assert fb["outstanding_credit_customer_count"] == 1
        assert fb["pending_payment_total_paise"] == 20000
        assert fb["pending_payment_count"] == 1


def test_opportunity_pulse_tenant_isolation_for_metrics(db):
    from datetime import datetime, timezone
    import uuid
    from app.billing_models import Bill
    from app.commerce_models import StoreOrder
    from app.khata_models import KhataAccount
    from app.models import Customer, Payment

    now_utc = datetime.now(timezone.utc)
    with session() as s:
        s.add(Merchant(id="merchant_tenant_b", name="Tenant B"))
        s.add(Store(id="store_tenant_b", merchant_id="merchant_tenant_b", name="Store B", slug="store-b"))
        s.flush()

        create_product(s, merchant_id="merchant_tenant_b", store_id="store_tenant_b",
                       product_id="prod-b-low", name="B Sugar", unit="kg",
                       unit_price_paise=4000, opening_stock=1, low_stock_threshold=5, sku="SUGAR-B")

        s.add(Payment(id="pay_b_" + uuid.uuid4().hex[:8],
                      merchant_id="merchant_tenant_b", store_id="store_tenant_b",
                      order_id="ord_b", customer_id="cust_b", amount_paise=88000,
                      provider="paytm", status="SUCCESS", verified_at=now_utc, bank="HDFC"))

        s.add(Customer(id="cust_b_khata", merchant_id="merchant_tenant_b", name="B Khata", phone="9111111111"))
        s.add(KhataAccount(id="acc_b_khata", merchant_id="merchant_tenant_b", store_id="store_tenant_b",
                           customer_id="cust_b_khata", balance_paise=99000, status="ACTIVE"))

        s.add(StoreOrder(id="order_b_" + uuid.uuid4().hex[:8],
                         merchant_id="merchant_tenant_b", store_id="store_tenant_b",
                         customer_id="cust_b", idempotency_key="idemp_b_1",
                         token_hash="hash_b_" + uuid.uuid4().hex[:12],
                         status="PAID", fulfillment_state="UNFULFILLED",
                         amount_paise=66000, created_at=now_utc, paid_at=now_utc))

        s.add(Bill(id="bill_b_" + uuid.uuid4().hex[:8],
                   merchant_id="merchant_tenant_b", store_id="store_tenant_b",
                   bill_number="BILL-B-001", state="ISSUED", payment_state="NOT_RECORDED",
                   total_paise=77000, issued_at=now_utc))

        s.commit()

        # Query merchant_default: all metrics should be strictly 0, nothing leaked from merchant_tenant_b
        pulse_default = opportunity_pulse(s, merchant_id="merchant_default", store_id="store_default", days=30)
        assert pulse_default["low_stock_summary"]["low_stock_count"] == 0
        assert pulse_default["sales_summary"]["verified_payment_count"] == 0
        assert pulse_default["sales_summary"]["verified_total_paise"] == 0
        assert pulse_default["khata_summary"]["customer_count"] == 0
        assert pulse_default["khata_summary"]["outstanding_total_paise"] == 0
        assert pulse_default["pending_fulfillment_summary"]["pending_count"] == 0
        assert pulse_default["pending_fulfillment_summary"]["pending_total_paise"] == 0
        assert pulse_default["financial_breakdown"]["gross_bill_issued_count"] == 0


def test_opportunity_pulse_validation_and_api(db):
    import pytest
    from app.demand import opportunity_pulse

    with session() as s:
        with pytest.raises(ValueError, match="days must be between 1 and 90"):
            opportunity_pulse(s, merchant_id="merchant_default", store_id="store_default", days=0)

        with pytest.raises(ValueError, match="days must be between 1 and 90"):
            opportunity_pulse(s, merchant_id="merchant_default", store_id="store_default", days=91)

    client = TestClient(app, headers={"X-Wapas-Console": "1"})
    res_err = client.get("/api/merchant/opportunities/pulse", params={"days": 100})
    assert res_err.status_code == 422

    res_ok = client.get("/api/merchant/opportunities/pulse", params={"days": 14})
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert data["window_days"] == 14
    assert "low_stock_summary" in data
    assert "sales_summary" in data
    assert "khata_summary" in data
    assert "pending_fulfillment_summary" in data
    assert "financial_breakdown" in data

