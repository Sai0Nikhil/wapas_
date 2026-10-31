import asyncio
from fastapi.testclient import TestClient
from app.main import app
from app.services.sarvam import parse_spoken_khata_entry


def test_parse_spoken_khata_entry_direct():
    text = "hey sarvam today rao gar took 300 ruppes and he only paid 30 ruppes lastmonth"
    existing = [
        {"name": "Suresh Gupta", "totalDue": 2450.0},
        {"name": "Rao Garu", "totalDue": 450.0},
    ]
    result = asyncio.run(parse_spoken_khata_entry(text, existing))
    assert result["debit_amount"] == 300.0 or result["net_amount"] == 270.0
    assert "rao" in result["customer_name"].lower()
    assert result["is_existing_match"] is True
    assert result["matched_existing_customer"] == "Rao Garu"


def test_khata_voice_endpoint():
    with TestClient(app) as c:
        payload = {
            "text": "today rao gar took 300 ruppes and he only paid 30 ruppes lastmonth",
            "existing_customers": [
                {"name": "Rao Garu", "totalDue": 450.0}
            ]
        }
        res = c.post("/khata/voice-parse", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["debit_amount"] == 300.0 or data["net_amount"] == 270.0
        assert data["is_existing_match"] is True
        assert data["matched_existing_customer"] == "Rao Garu"
