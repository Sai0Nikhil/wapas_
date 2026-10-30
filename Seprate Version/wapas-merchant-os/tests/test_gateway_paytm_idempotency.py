"""Durable Paytm Payment Link retry behavior with all network calls mocked."""
import json
from types import SimpleNamespace

import httpx

from app.gateway.paytm import PaytmGateway

KEY = "abcdefghijklmnop"
KW = dict(idempotency_key="c_A118@1:link", amount_paise=234000, customer_name="R",
          customer_phone="9800000000", description="Order A118", callback_url="https://example.test/cb")


def gateway(handler):
    settings = SimpleNamespace(paytm_mid="MID123", paytm_merchant_key=KEY, paytm_host="https://securestage.paytmpayments.com",
                               paytm_link_create_path="/link/create", merchant_name="Sharma Electronics",
                               app_env="test", paytm_test_enabled=True)
    result = PaytmGateway(settings)
    result.http = httpx.Client(transport=httpx.MockTransport(handler))
    return result


def lookup(links):
    return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"}, "links": links}})


def test_fresh_gateway_retry_reuses_link_created_before_timeout():
    calls = []
    creates = 0

    def handler(req):
        nonlocal creates
        calls.append(req.url.path)
        if req.url.path == "/link/fetch":
            if creates:
                request = json.loads(req.content)
                assert request["body"]["merchantRequestId"]
                return lookup([{"linkId": "777", "shortUrl": "https://paytm.test/777", "isActive": True}])
            return lookup([])
        creates += 1
        raise httpx.ReadTimeout("create response lost", request=req)

    first_process = gateway(handler)
    first = first_process.create_link(**KW)
    assert not first.ok

    # A fresh adapter has no process-local retry state; it still finds the provider-side link.
    restarted_process = gateway(handler)
    retry = restarted_process.create_link(**KW)
    assert retry.ok and retry.link_id == "777" and retry.short_url == "https://paytm.test/777"
    assert creates == 1
    assert calls == ["/link/fetch", "/link/create", "/link/fetch"]


def test_lookup_unavailable_fails_closed_without_second_create():
    calls = []
    creates = 0

    def handler(req):
        nonlocal creates
        calls.append(req.url.path)
        if req.url.path == "/link/fetch":
            if creates:
                raise httpx.ConnectError("lookup unavailable", request=req)
            return lookup([])
        creates += 1
        raise httpx.ReadTimeout("create response lost", request=req)

    assert not gateway(handler).create_link(**KW).ok
    retry = gateway(handler).create_link(**KW)
    assert not retry.ok and "lookup failed" in retry.error
    assert creates == 1
    assert calls == ["/link/fetch", "/link/create", "/link/fetch"]


def test_successful_empty_lookup_allows_one_create():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path == "/link/fetch":
            return lookup([])  # definitive no-match
        return httpx.Response(200, json={"body": {"resultInfo": {"resultStatus": "SUCCESS"},
                                                   "linkId": "888", "shortUrl": "https://paytm.test/888"}})

    result = gateway(handler).create_link(**KW)
    assert result.ok and result.link_id == "888"
    assert calls == ["/link/fetch", "/link/create"]
