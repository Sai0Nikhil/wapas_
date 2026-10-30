from io import BytesIO
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db import session
from app.inventory import create_product
from app.main import app


def _client():
    return TestClient(app, headers={"X-Wapas-Console": "1"})


def _png():
    out = BytesIO()
    Image.new("RGB", (32, 24), "white").save(out, "PNG")
    return out.getvalue()


def _draft_with_products(client):
    products = []
    for name, sku in (("Rice Bag", "RICE-BAG"), ("Oil Packet", "OIL-PKT")):
        response = client.post("/api/merchant/catalog/products", json={
            "name": name, "sku": sku, "unit": "each", "unit_price_paise": 1299,
            "opening_stock": "20",
        })
        assert response.status_code == 201
        products.append(response.json())
    bill = client.post("/api/merchant/bills", json={"idempotency_key": "counter-inputs-draft-01"})
    assert bill.status_code == 201
    return bill.json(), products


def _enable_vision(monkeypatch):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "vision_enabled", True)
    monkeypatch.setattr(cfg, "vision_base_url", "https://vision.example/v1")
    monkeypatch.setattr(cfg, "vision_api_key", "test-only-key")
    monkeypatch.setattr(cfg, "vision_model", "test-vision")


def test_counter_image_validation_rejects_bad_type_mismatch_and_oversize():
    from app.counter_inputs import MAX_AUDIO_BYTES, MAX_IMAGE_BYTES, validate_audio, validate_image
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as invalid:
        validate_image(b"not an image", "image/png")
    assert invalid.value.status_code == 422
    with pytest.raises(HTTPException) as mismatch:
        validate_image(_png(), "image/jpeg")
    assert mismatch.value.status_code == 415
    with pytest.raises(HTTPException) as oversized:
        validate_image(b"x" * (MAX_IMAGE_BYTES + 1), "image/png")
    assert oversized.value.status_code == 413
    with pytest.raises(HTTPException) as audio_too_large:
        validate_audio(b"x" * (MAX_AUDIO_BYTES + 1), "audio/webm")
    assert audio_too_large.value.status_code == 413
    with pytest.raises(HTTPException) as audio_type:
        validate_audio(b"x", "application/octet-stream")
    assert audio_type.value.status_code == 415


def test_photo_and_parchi_are_not_configured_without_provider_and_never_mutate_draft(db, monkeypatch):
    from app import counter_inputs
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "vision_enabled", False)
    monkeypatch.setattr(counter_inputs.httpx, "post", lambda *a, **k: pytest.fail("provider must not be called"))
    client = _client()
    bill, _ = _draft_with_products(client)
    for kind in ("photo", "parchi"):
        response = client.post(f"/api/merchant/bills/{bill['id']}/input/{kind}",
                               files={"image": ("photo.png", _png(), "image/png")},
                               data={"consent_to_external_processing": "true"})
        assert response.status_code == 200
        assert response.json()["status"] == "NOT CONFIGURED"
        assert response.json()["items"] == []
    saved = client.get(f"/api/merchant/bills/{bill['id']}").json()
    assert saved["lines"] == [] and saved["state"] == "DRAFT"


def test_image_consent_required_and_provider_candidates_are_catalogue_scoped_and_review_only(db, monkeypatch):
    from app import counter_inputs

    _enable_vision(monkeypatch)
    client = _client()
    bill, products = _draft_with_products(client)
    called = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"items":[{"name":"Rice Bag","quantity":2,"unit":"each","confidence":0.94,"product_id":"invented","price":0}]}'}}]}

    def fake_post(*args, **kwargs):
        called.append(kwargs)
        return Response()

    monkeypatch.setattr(counter_inputs.httpx, "post", fake_post)
    files = {"image": ("rice.png", _png(), "image/png")}
    refused = client.post(f"/api/merchant/bills/{bill['id']}/input/photo", files=files,
                          data={"consent_to_external_processing": "false"})
    assert refused.status_code == 200 and refused.json()["status"] == "CONSENT REQUIRED"
    assert called == []
    accepted = client.post(f"/api/merchant/bills/{bill['id']}/input/photo", files=files,
                           data={"consent_to_external_processing": "true"})
    result = accepted.json()
    assert result["status"] == "REVIEW REQUIRED" and len(result["items"]) == 1
    item = result["items"][0]
    assert item["recognized_name"] == "Rice Bag" and item["quantity"] == "2"
    assert item["candidates"][0]["product_id"] == products[0]["id"]
    assert item["candidates"][0]["product_id"] != "invented"
    assert item["needs_manual_review"] is True
    assert len(called) == 1
    assert client.get(f"/api/merchant/bills/{bill['id']}").json()["lines"] == []


def test_parchi_provider_failure_returns_manual_transcription_fallback(db, monkeypatch):
    from app import counter_inputs

    _enable_vision(monkeypatch)
    client = _client()
    bill, _ = _draft_with_products(client)
    monkeypatch.setattr(counter_inputs.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ReadTimeout("slow")))
    response = client.post(f"/api/merchant/bills/{bill['id']}/input/parchi",
                           files={"image": ("list.png", _png(), "image/png")},
                           data={"consent_to_external_processing": "true"})
    assert response.status_code == 200
    assert response.json()["status"] == "DEGRADED"
    assert "transcribe" in response.json()["message"].lower()
    assert client.get(f"/api/merchant/bills/{bill['id']}").json()["lines"] == []


def test_voice_requires_consent_and_missing_provider_has_typed_fallback(db, monkeypatch):
    from app import counter_inputs
    from app.config import get_settings

    client = _client()
    bill, _ = _draft_with_products(client)
    monkeypatch.setattr(get_settings(), "sarvam_api_key", "")
    monkeypatch.setattr(counter_inputs, "transcribe_counter_audio", lambda *a: pytest.fail("STT must not run"))
    missing = client.post(f"/api/merchant/bills/{bill['id']}/input/voice",
                          files={"audio": ("turn.webm", b"audio-bytes", "audio/webm")},
                          data={"consent_to_external_processing": "true"})
    assert missing.status_code == 200 and missing.json()["status"] == "NOT CONFIGURED"
    monkeypatch.setattr(get_settings(), "sarvam_api_key", "test-key")
    refused = client.post(f"/api/merchant/bills/{bill['id']}/input/voice",
                          files={"audio": ("turn.webm", b"audio-bytes", "audio/webm")},
                          data={"consent_to_external_processing": "false"})
    assert refused.status_code == 200 and refused.json()["status"] == "CONSENT REQUIRED"
    assert client.get(f"/api/merchant/bills/{bill['id']}").json()["lines"] == []


def test_voice_and_manual_parchi_lines_resolve_then_share_counter_line_and_issue_service(db, monkeypatch):
    from app import counter_inputs
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "sarvam_api_key", "test-key")
    monkeypatch.setattr(counter_inputs, "transcribe_counter_audio",
                        lambda audio, mime: "Add two Rice Bag and three Oil Packet")
    client = _client()
    bill, products = _draft_with_products(client)
    voice_result = client.post(f"/api/merchant/bills/{bill['id']}/input/voice",
                               files={"audio": ("turn.webm", b"audio-bytes", "audio/webm")},
                               data={"consent_to_external_processing": "true"}).json()
    assert voice_result["status"] == "REVIEW REQUIRED"
    assert voice_result["transcript"] == "Add two Rice Bag and three Oil Packet"
    assert [line["quantity"] for line in voice_result["items"]] == ["2", "3"]
    typed = client.post(f"/api/merchant/bills/{bill['id']}/input/text",
                        json={"text": "2 Rice Bag\n3 Oil Packet"})
    assert typed.status_code == 200 and len(typed.json()["items"]) == 2

    # Every suggestion is added through the existing server-side line service.
    for product, quantity in zip(products, ("2", "3")):
        saved = client.put(f"/api/merchant/bills/{bill['id']}/lines/{product['id']}", json={"quantity": quantity})
        assert saved.status_code == 200
    issued = client.post(f"/api/merchant/bills/{bill['id']}/issue")
    assert issued.status_code == 200 and issued.json()["state"] == "ISSUED"
    assert [line["quantity"] for line in issued.json()["lines"]] == ["2.000", "3.000"]
    assert issued.json()["payment_state"] == "NOT_RECORDED"


def test_manual_list_parser_keeps_uncertain_or_missing_quantities_unresolved():
    from app.counter_inputs import parse_manual_list, parse_voice_transcript

    assert [item["quantity"] for item in parse_voice_transcript("Add two rice bags and three oil packets")] == ["2", "3"]
    assert [item["name"] for item in parse_manual_list("2 rice bags\n3 oil packets")] == ["rice bags", "oil packets"]
    assert parse_voice_transcript("Add some rice bags") == []
    assert parse_manual_list("rice bags") == []


def test_ambiguous_and_unknown_catalogue_candidates_are_never_auto_selected(db):
    from app.counter_inputs import resolve_candidates

    client = _client()
    bill, products = _draft_with_products(client)
    with session() as s:
        create_product(s, merchant_id="merchant_default", store_id="store_default",
                       product_id="rice-bag-second", name="Rice Bag", unit="each",
                       unit_price_paise=1400, opening_stock=5, sku="RICE-BAG-2")
        s.commit()
        ambiguous = resolve_candidates(s, merchant_id="merchant_default", store_id="store_default",
                                       raw_items=[{"name":"Rice Bag", "quantity":2}])[0]
        unknown = resolve_candidates(s, merchant_id="merchant_default", store_id="store_default",
                                     raw_items=[{"name":"Cinnamon Whistle", "quantity":1}])[0]
    assert ambiguous["needs_manual_review"] and ambiguous["needs_clarification"]
    assert len(ambiguous["candidates"]) >= 2
    assert unknown["candidates"] == [] and unknown["needs_clarification"]
    assert client.get(f"/api/merchant/bills/{bill['id']}").json()["lines"] == []


def test_non_finite_model_confidence_is_returned_as_uncertain_not_json_nan(db):
    from app.counter_inputs import resolve_candidates

    client = _client()
    _draft_with_products(client)
    with session() as s:
        candidates = resolve_candidates(s, merchant_id="merchant_default", store_id="store_default",
                                        raw_items=[{"name": "Rice Bag", "quantity": 1,
                                                    "confidence": "NaN"}])
    assert candidates[0]["provider_confidence"] is None
    assert candidates[0]["needs_manual_review"] is True


def test_barcode_lookup_rejects_inactive_and_insufficient_stock_is_rejected_by_billing(db):
    client = _client()
    active = client.post("/api/merchant/catalog/products", json={
        "name":"No stock tea", "sku":"NO-STOCK-TEA", "barcode":"89990001",
        "unit":"each", "unit_price_paise":100, "opening_stock":"0",
    }).json()
    bill = client.post("/api/merchant/bills", json={"idempotency_key":"scanner-stock-bill-01"}).json()
    lookup = client.get("/api/merchant/catalog/products/lookup", params={"barcode":"89990001"})
    assert lookup.status_code == 200 and lookup.json()["id"] == active["id"]
    assert client.put(f"/api/merchant/bills/{bill['id']}/lines/{active['id']}", json={"quantity":"1"}).status_code == 409
    archived = client.patch(f"/api/merchant/catalog/products/{active['id']}", json={"status":"ARCHIVED"})
    assert archived.status_code == 200
    assert client.get("/api/merchant/catalog/products/lookup", params={"barcode":"89990001"}).status_code == 404
    assert client.get("/api/merchant/catalog/products/lookup", params={"barcode":"unknown-code"}).status_code == 404
