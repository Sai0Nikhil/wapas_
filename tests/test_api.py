from fastapi.testclient import TestClient

from app.main import app
from scripts.seed import main as seed


def test_health_and_duplicate_webhook():
    with TestClient(app) as c:
        seed()
        assert c.get("/health").json()["ok"] is True
        evt = {"ORDERID": "T1", "TXNID": "X1", "STATUS": "TXN_FAILURE", "TXNAMOUNT": "2340.00",
               "BANKNAME": "HDFC", "CUSTID": "cust-rahul"}
        r1 = c.post("/webhooks/paytm", json=evt).json()
        r2 = c.post("/webhooks/paytm", json=evt).json()
        assert r1["result"] == "case_created"
        assert r2["result"] == "duplicate_ignored"
        assert len(c.get("/cases").json()) == 1
