from fastapi.testclient import TestClient
from app.main import app
from scripts.seed import main as seed


def test_health_and_duplicate_webhook():
    with TestClient(app) as c:
        seed()
        assert c.get("/health").json()["ok"] is True
        evt = {"ORDERID": "T1", "TXNID": "X1", "STATUS": "TXN_FAILURE", "TXNAMOUNT": "2340.00",
               "BANKNAME": "HDFC", "CUSTID": "cust-rahul", "RESPMSG": "Bank timeout"}
        r1 = c.post("/webhooks/paytm", json=evt).json()
        r2 = c.post("/webhooks/paytm", json=evt).json()
        assert r1["result"] == "case_created"
        assert r2["result"] == "duplicate_ignored"
        cases = c.get("/cases").json()
        assert len(cases) == 1
        case_id = cases[0]["id"]

        # Check evidence log has AI proposal and Policy authorization
        detail = c.get(f"/cases/{case_id}").json()
        assert len(detail["evidence"]) >= 3


def test_simulate_failure_and_approval_flow():
    with TestClient(app) as c:
        seed()
        sim_res = c.post("/dev/simulate-failure", json={
            "amount_inr": 6500.0,  # Exceeds 5000 INR limit -> policy should ASK_OWNER
            "customer_ref": "cust-suresh",
            "bank": "SBI",
            "resp_msg": "Exceeded limit",
        }).json()

        case_id = sim_res["case_id"]
        detail = c.get(f"/cases/{case_id}").json()
        assert detail["case"]["verdict"] == "ASK_OWNER"
        assert detail["case"]["status"] == "AWAITING_OWNER"

        # Owner issues token and approves
        token = c.get(f"/approvals/token/{case_id}/approve").json()["token"]
        decide_res = c.post(f"/approvals/{token}").json()
        assert decide_res["result"] == "approve"
