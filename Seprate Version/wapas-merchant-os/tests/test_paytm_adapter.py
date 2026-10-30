"""Paytm adapter with the network mocked: signing, request shape, result mapping."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.gateway.checksum import generate_signature, verify_signature
from app.gateway.paytm import PaytmGateway
from app.ports import PayStatus

KEY = "abcdefghijklmnop"


def gw(handler):
    s = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY, paytm_host="https://securestage.paytmpayments.com",
                        paytm_link_create_path="/link/create", paytm_link_fetch_txn_path="/link/fetchTransaction",
                        paytm_order_status_path="/v3/order/status", merchant_name="Sharma Electronics",
                        paytm_website="WEBSTAGING", app_env="test", paytm_test_enabled=True)
    g = PaytmGateway(s)
    g.http = httpx.Client(transport=httpx.MockTransport(handler))
    return g


def signed_status_response(body, *, signature=True):
    payload = {"body": body}
    if signature:
        body_json = json.dumps(body, separators=(",", ":"))
        payload["head"] = {"signature": generate_signature(body_json, KEY)}
    return httpx.Response(200, json=payload)


def test_create_link_signed_and_mapped():
    seen = {}

    def handler(req):
        payload = json.loads(req.content)
        if req.url.path == "/link/fetch":
            return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "links": []}})
        seen["path"], seen["payload"] = req.url.path, payload
        body_str = json.dumps(payload["body"], separators=(",", ":"))
        assert verify_signature(body_str, KEY, payload["head"]["signature"])  # Paytm could verify us
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS", "resultCode": "200"},
                                                   "linkId": 991, "shortUrl": "https://paytm.me/x-abc"}})
    r = gw(handler).create_link(idempotency_key="c_A118:link", amount_paise=234000, customer_name="Rahul Sharma",
                                customer_phone="9800000000", description="Order A118", callback_url="https://x/cb")
    assert r.ok and r.link_id == "991" and r.short_url.endswith("x-abc")
    b = seen["payload"]["body"]
    assert seen["path"] == "/link/create" and b["linkType"] == "FIXED" and b["amount"] == 2340.0
    assert b["maxPaymentsAllowed"] == "1" and b["mid"] == "MID123" and seen["payload"]["head"]["tokenType"] == "AES"
    assert b["merchantRequestId"].startswith("wapas") and b["merchantRequestId"].isalnum() and len(b["merchantRequestId"]) <= 64
    import re
    assert re.fullmatch(r"\d\d/\d\d/\d{4} \d\d:\d\d:\d\d", b["expiryDate"]) and "timestamp" in seen["payload"]["head"]


def test_create_link_error_is_not_ok():
    def h(req):
        if req.url.path == "/link/fetch":
            return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "links": []}})
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "FAILED", "resultCode": "5008",
                                                                    "resultMessage": "amount is mandatory"}}})
    r = gw(h).create_link(idempotency_key="k", amount_paise=100, customer_name="A", customer_phone="9",
                          description="Order", callback_url="u")
    assert not r.ok and "5008" in r.error


def test_timeout_is_error_not_success():
    def h(req):
        raise httpx.ConnectTimeout("slow")
    assert gw(h).link_status("991").status == PayStatus.ERROR


def test_paid_only_when_order_status_confirms():
    def h(req):
        if req.url.path == "/link/fetchTransaction":
            return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"},
                                                      "orders": [{"orderId": "ORD1", "orderStatus": "SUCCESS"}]}})
        return signed_status_response({"resultInfo": {"resultStatus": "TXN_SUCCESS"},
                                       "mid": "MID123", "orderId": "ORD1",
                                       "txnId": "T1", "txnAmount": "2340.00"})
    st = gw(h).link_status("991")
    assert st.status == PayStatus.SUCCESS and st.txn_id == "T1" and st.amount_paise == 234000


def test_link_says_paid_but_order_disagrees_is_error():
    def h(req):
        if req.url.path == "/link/fetchTransaction":
            return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"},
                                                      "orders": [{"orderId": "ORD1", "orderStatus": "SUCCESS"}]}})
        return signed_status_response({"resultInfo": {"resultStatus": "PENDING"}})
    assert gw(h).link_status("991").status == PayStatus.ERROR


def test_unpaid_link_is_pending():
    h = lambda req: httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "orders": []}})
    assert gw(h).link_status("991").status == PayStatus.PENDING


def test_callback_checksum():
    g = gw(lambda req: httpx.Response(200))
    params = {"LINKID": "991", "STATUS": "TXN_SUCCESS", "ORDERID": "ORD1"}
    good = dict(params, CHECKSUMHASH=generate_signature(params, KEY))
    assert g.verify_callback(good)
    assert not g.verify_callback(dict(good, STATUS="TXN_FAILURE"))
    assert not g.verify_callback(params)


def test_status_codes_that_are_not_payment_results():
    """Per Paytm's v3 docs: 334 'Invalid Order ID' arrives as TXN_FAILURE but is not a failed payment;
    335 is a bad MID (our config); 402 is pending; 501 is Paytm down."""
    cases = [({"resultStatus": "TXN_FAILURE", "resultCode": "334", "resultMsg": "Invalid Order ID"}, PayStatus.NOT_FOUND),
             ({"resultStatus": "TXN_FAILURE", "resultCode": "501", "resultMsg": "Your Payment has declined by your bank"}, PayStatus.FAILED),
             ({"resultStatus": "TXN_FAILURE", "resultCode": "330", "resultMsg": "Invalid Checksum"}, PayStatus.ERROR),
             ({"resultStatus": "TXN_FAILURE", "resultCode": "335", "resultMsg": "Mid is invalid"}, PayStatus.ERROR),
             ({"resultStatus": "NO_RECORD_FOUND", "resultCode": "331", "resultMsg": "No Record Found"}, PayStatus.NOT_FOUND),
             ({"resultStatus": "TXN_FAILURE", "resultCode": "335", "resultMsg": "Invalid MID"}, PayStatus.ERROR),
             ({"resultStatus": "PENDING", "resultCode": "402", "resultMsg": "Looks like the payment is not complete."}, PayStatus.PENDING),
             ({"resultStatus": "TXN_FAILURE", "resultCode": "501", "resultMsg": "Server Down"}, PayStatus.ERROR),
             ({"resultStatus": "TXN_FAILURE", "resultCode": "227", "resultMsg": "Bank declined"}, PayStatus.FAILED)]
    for info, want in cases:
        g = gw(lambda req, info=info: signed_status_response({
            "resultInfo": info, "mid": "MID123", "orderId": "ORD1",
        }))
        assert g.order_status("ORD1").status == want, info


def test_terminal_status_must_match_mid_and_requested_order_id():
    cases = [
        ({"mid": "MID123", "orderId": "ORD2"}, PayStatus.ERROR),
        ({"mid": "OTHER", "orderId": "ORD1"}, PayStatus.ERROR),
        ({"orderId": "ORD1"}, PayStatus.ERROR),
        ({"mid": "MID123"}, PayStatus.ERROR),
        ({"mid": "MID123", "orderId": "ORD1", "txnId": "T1"}, PayStatus.SUCCESS),
    ]
    for identity, expected in cases:
        body = {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "txnAmount": "10.00", **identity}
        result = gw(lambda req, body=body: signed_status_response(body)).order_status("ORD1")
        assert result.status == expected, identity


@pytest.mark.parametrize("body", [
    {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "mid": "MID123", "orderId": "ORD1",
     "txnId": "T1", "txnAmount": "NaN"},
    {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "mid": "MID123", "orderId": "ORD1",
     "txnId": "T1", "txnAmount": "Infinity"},
    {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "mid": "MID123", "orderId": "ORD1",
     "txnId": "T1", "txnAmount": "10.001"},
    {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "mid": "MID123", "orderId": "ORD1",
     "txnId": "T1", "txnAmount": "0.00"},
    {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "mid": "MID123", "orderId": "ORD1",
     "txnAmount": "10.00"},
    {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "mid": "MID123", "orderId": "ORD1",
     "txnId": " ", "txnAmount": "10.00"},
])
def test_success_status_requires_exact_positive_paise_amount_and_transaction_id(body):
    result = gw(lambda req: signed_status_response(body)).order_status("ORD1")
    assert result.status == PayStatus.ERROR


def test_success_status_parses_exact_decimal_paise_without_float_rounding():
    body = {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "mid": "MID123", "orderId": "ORD1",
            "txnId": "T1", "txnAmount": "2340.00"}
    result = gw(lambda req: signed_status_response(body)).order_status("ORD1")
    assert result.status == PayStatus.SUCCESS
    assert result.amount_paise == 234000


def test_status_api_head_uses_request_timestamp_and_no_token_type():
    seen = {}

    def handler(req):
        seen["head"] = json.loads(req.content)["head"]
        return signed_status_response({"resultInfo": {"resultStatus": "PENDING", "resultCode": "402"}})
    gw(handler).order_status("ORD1")
    assert "requestTimestamp" in seen["head"] and "tokenType" not in seen["head"] and "signature" in seen["head"]


@pytest.mark.parametrize("result_info", [None, [], "SUCCESS"])
def test_malformed_signed_status_result_information_fails_closed(result_info):
    result = gw(lambda req: signed_status_response({
        "resultInfo": result_info, "mid": "MID123", "orderId": "ORD1",
        "txnId": "T1", "txnAmount": "10.00",
    })).order_status("ORD1")
    assert result.status == PayStatus.ERROR


@pytest.mark.parametrize("payload", [
    {"body": None},
    {"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "orders": {}}},
    {"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "orders": [None]}},
])
def test_malformed_link_status_response_fails_closed(payload):
    result = gw(lambda req: httpx.Response(200, json=payload)).link_status("991")
    assert result.status == PayStatus.ERROR


def test_malformed_checkout_response_returns_error_instead_of_raising():
    result = gw(lambda req: httpx.Response(200, json={"body": None})).initiate_checkout(
        order_id="ORD1", amount_paise=100, cust_id="c", callback_url="https://example.test/callback",
    )
    assert result["ok"] is False and "malformed" in result["error"]


def test_production_money_movement_is_disabled_without_explicit_release_flag():
    calls = []
    settings = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY,
                               paytm_host="https://secure.paytmpayments.com",
                               paytm_link_create_path="/link/create", paytm_link_fetch_txn_path="/link/fetchTransaction",
                               paytm_order_status_path="/v3/order/status", merchant_name="Sharma Electronics",
                               paytm_website="DEFAULT")
    gateway = PaytmGateway(settings)
    gateway.http = httpx.Client(transport=httpx.MockTransport(lambda req: calls.append(req.url.path)))

    link = gateway.create_link(idempotency_key="live-key", amount_paise=100,
                               customer_name="A", customer_phone="", description="Order", callback_url="https://x/cb")
    checkout = gateway.initiate_checkout(order_id="ORDER1", amount_paise=100, cust_id="c1", callback_url="https://x/cb")
    probe = gateway.probe_links()
    assert not link.ok and "PAYTM_LIVE_ENABLED" in link.error
    assert not checkout["ok"] and "PAYTM_LIVE_ENABLED" in checkout["error"]
    assert not probe[0] and "PAYTM_LIVE_ENABLED" in probe[1]
    assert calls == []


@pytest.mark.parametrize("host", [
    "https://stage.attacker.example",
    "https://securestage.paytmpayments.com.attacker.example",
    "http://securestage.paytmpayments.com",
    "https://user:pass@securestage.paytmpayments.com",
    "https://securestage.paytmpayments.com:8443",
    "https://securestage.paytmpayments.com/path",
])
def test_gateway_rejects_untrusted_or_malformed_paytm_hosts(host):
    settings = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY, paytm_host=host)
    with pytest.raises(RuntimeError, match="PAYTM_HOST"):
        PaytmGateway(settings)


def test_paytm_action_gates_require_environment_and_exact_official_host():
    staging = gw(lambda req: httpx.Response(500))
    assert staging._payment_actions_disabled() is False

    production_stage = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY,
                                       paytm_host="https://securestage.paytmpayments.com",
                                       app_env="production", paytm_test_enabled=True)
    assert PaytmGateway(production_stage)._payment_actions_disabled() is True

    test_without_opt_in = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY,
                                          paytm_host="https://securestage.paytmpayments.com",
                                          app_env="test", paytm_test_enabled=False)
    assert PaytmGateway(test_without_opt_in)._payment_actions_disabled() is True

    prod_settings = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY,
                                    paytm_host="https://secure.paytmpayments.com",
                                    app_env="production", paytm_live_enabled=False)
    prod = PaytmGateway(prod_settings)
    try:
        assert prod._payment_actions_disabled() is True
    finally:
        prod.http.close()

    test_prod_host = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY,
                                     paytm_host="https://secure.paytmpayments.com",
                                     app_env="test", paytm_live_enabled=True)
    assert PaytmGateway(test_prod_host)._payment_actions_disabled() is True


def test_staging_actions_are_blocked_in_production_even_with_test_flag():
    calls = []
    settings = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY,
                               paytm_host="https://securestage.paytmpayments.com",
                               paytm_link_create_path="/link/create", paytm_link_fetch_txn_path="/link/fetchTransaction",
                               paytm_order_status_path="/v3/order/status", merchant_name="Sharma Electronics",
                               paytm_website="WEBSTAGING", app_env="production", paytm_test_enabled=True,
                               paytm_live_enabled=False)
    gateway = PaytmGateway(settings)
    gateway.http = httpx.Client(transport=httpx.MockTransport(lambda req: calls.append(req.url.path)))
    assert not gateway.create_link(idempotency_key="k", amount_paise=100, customer_name="A",
                                   customer_phone="", description="Order", callback_url="https://x/cb").ok
    assert not gateway.initiate_checkout(order_id="ORDER1", amount_paise=100, cust_id="c",
                                         callback_url="https://x/cb")["ok"]
    assert not gateway.probe_links()[0]
    assert calls == []
    gateway.http.close()


def test_unpaid_link_with_short_success_status_is_pending_not_error():
    """Fetch Link Transactions' own sample answers resultStatus "S"."""
    g = gw(lambda req: httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "S", "resultCode": "200"}, "orders": []}}))
    assert g.link_status("5861").status == PayStatus.PENDING


def test_terminal_status_requires_a_valid_provider_checksum():
    body = {"resultInfo": {"resultStatus": "TXN_SUCCESS"}, "mid": "MID123", "orderId": "ORD1",
            "txnId": "T1", "txnAmount": "10.00"}
    unsigned = gw(lambda req: httpx.Response(200, json={"body": body})).order_status("ORD1")
    assert unsigned.status == PayStatus.ERROR

    signed = signed_status_response(body).json()
    signed["body"]["txnAmount"] = "0.01"  # alter the amount after signing
    tampered = gw(lambda req: httpx.Response(200, json=signed)).order_status("ORD1")
    assert tampered.status == PayStatus.ERROR


def test_link_paid_but_status_api_has_no_record_is_not_a_verified_payment():
    def handler(req):
        if req.url.path == "/link/fetchTransaction":
            return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "S"}, "orders": [
                {"orderId": "LINKORD1", "txnId": "T9", "orderStatus": "SUCCESS", "txnAmount": "2340.00"}]}})
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "TXN_FAILURE", "resultCode": "334",
                                                                 "resultMsg": "Invalid Order ID"}}})
    r = gw(handler).link_status("5861")
    assert r.status == PayStatus.ERROR


def test_create_link_retry_after_timeout_finds_the_first_link_instead_of_making_a_second():
    calls = []
    creates = 0

    def handler(req):
        nonlocal creates
        calls.append(req.url.path)
        if req.url.path == "/link/fetch":
            body = json.loads(req.content)
            assert body["head"]["channelId"] == "WEB" and body["body"]["merchantRequestId"].startswith("wapas")
            if calls.count("/link/fetch") == 1:
                return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "links": []}})
            return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"},
                                                      "links": [{"linkId": 777, "shortUrl": "https://p-y.tm/x", "isActive": True}]}})
        creates += 1
        if creates == 1:
            raise httpx.ReadTimeout("slow", request=req)  # Paytm may have created it anyway
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "linkId": 888, "shortUrl": "https://p-y.tm/y"}})
    g = gw(handler)
    kw = dict(idempotency_key="c_A118@1:link", amount_paise=234000, customer_name="R", customer_phone="9800000000",
              description="Order A118", callback_url="https://x/cb")
    assert not g.create_link(**kw).ok
    r = g.create_link(**kw)
    assert r.ok and r.link_id == "777" and creates == 1
    assert calls == ["/link/fetch", "/link/create", "/link/fetch"]


def test_create_link_sends_mandatory_flags_and_no_customer_phone():
    """Docs mark partialPayment/bindLinkIdMobile mandatory; Wapas delivers the link itself, so the
    customer's phone never goes to Paytm (staging also rejected numbers with 6019)."""
    seen = {}

    def handler(req):
        if req.url.path == "/link/fetch":
            return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "links": []}})
        seen["body"] = json.loads(req.content)["body"]
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "linkId": 1, "shortUrl": "u"}})
    gw(handler).create_link(idempotency_key="k", amount_paise=100, customer_name="A", customer_phone="9800000000",
                            description="Order 1", callback_url="https://x/cb")
    b = seen["body"]
    assert b["partialPayment"] is False and b["bindLinkIdMobile"] is False
    assert b["sendSms"] is False and b["sendEmail"] is False
    assert "customerContact" not in b and "9800000000" not in json.dumps(b)


def test_staging_not_enabled_codes_explain_themselves():
    def link_handler(req):
        if req.url.path == "/link/fetch":
            return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "links": []}})
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "FAILED", "resultCode": "5023",
                                                                 "resultMessage": "Merchant Id is invalid."}}})
    r = gw(link_handler).create_link(idempotency_key="k2", amount_paise=100, customer_name="A", customer_phone="",
                                     description="Order 2", callback_url="https://x/cb")
    assert not r.ok and r.error.startswith("5023") and "Payment Links is not enabled" in r.error
    ok, detail = gw(link_handler).probe_links()
    assert ok is False and "not enabled" in detail

    def init_handler(req):
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "F", "resultCode": "239", "resultMsg": "System Error"}}})
    res = gw(init_handler).initiate_checkout(order_id="O1", amount_paise=100, cust_id="c", callback_url="https://x/cb")
    assert res["ok"] is False and res["error"].startswith("239") and "not enabled" in res["error"]


def test_link_probe_success_contacts_nobody():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)["body"]
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "linkId": 77, "shortUrl": "u"}})
    ok, detail = gw(handler).probe_links()
    assert ok and "77" in detail
    b = seen["body"]
    assert b["amount"] == 1.0 and b["sendSms"] is False and b["sendEmail"] is False and "customerContact" not in b
