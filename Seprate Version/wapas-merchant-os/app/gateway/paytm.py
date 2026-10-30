"""Paytm test-environment adapter.

Docs: https://www.paytmpayments.com/docs/api/create-link-api
      https://www.paytmpayments.com/docs/api/v3/transaction-status-api
Known official HTTPS hosts and API paths remain configuration because the
merchant's Paytm product/API variants differ; the host must match the adapter's
allowlist, and the merchant-specific variant still needs dashboard confirmation.
Every request body is signed with Paytm's checksum library.
"""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx

from ..ports import LinkResult, PayStatus, StatusResult

from .checksum import generate_signature, verify_signature

SUCCESS_WORDS = {"TXN_SUCCESS", "SUCCESS"}
FAIL_WORDS = {"TXN_FAILURE", "FAILURE", "FAILED"}
IST = timezone(timedelta(hours=5, minutes=30))
LINK_API_OK = {"S", "SUCCESS"}  # Fetch Transaction's doc table says SUCCESS; its sample says "S"
STAGING_HOSTS = {"securestage.paytmpayments.com"}
PRODUCTION_HOSTS = {"secure.paytmpayments.com"}
ALLOWED_HOSTS = STAGING_HOSTS | PRODUCTION_HOSTS


# Seen on staging (Sep 2026) with a correctly signed request from a known test MID. A wrong key gives
# 2005/5028/330 instead, and an unknown MID gives 501/404, so these point at the MID's setup, not our code.
_HINTS = {
    ("checkout", "239"): "Paytm accepted the MID and signature but will not start a checkout: "
                         "payment gateway is not enabled for this test MID. Ask Paytm to enable it.",
    ("link", "5023"): "Paytm accepted the signature but says Payment Links is not enabled for this test MID. "
                      "Ask Paytm to enable Payment Links on staging.",
}


def hint(code: str, api: str) -> str:
    h = _HINTS.get((api, code))
    return f" ({h})" if h else ""


def _sign(body: dict, key: str) -> str:
    return generate_signature(json.dumps(body, separators=(",", ":")), key)


class PaytmGateway:
    name = "paytm"

    def __init__(self, s):
        if not (s.paytm_mid and s.paytm_merchant_key):
            raise RuntimeError("GATEWAY=paytm needs PAYTM_MID and PAYTM_MERCHANT_KEY")
        try:
            parsed_host = urlsplit(s.paytm_host)
            host = (parsed_host.hostname or "").rstrip(".").casefold()
            port = parsed_host.port
        except ValueError as exc:
            raise RuntimeError("PAYTM_HOST must be a valid official HTTPS Paytm host") from exc
        if (parsed_host.scheme != "https" or host not in ALLOWED_HOSTS
                or port not in (None, 443) or parsed_host.username or parsed_host.password
                or parsed_host.query or parsed_host.fragment or parsed_host.path not in ("", "/")):
            raise RuntimeError("PAYTM_HOST must be an official HTTPS Paytm host without credentials or extra URL components")
        self.s = s
        self.http = httpx.Client(timeout=10.0)

    def _payment_actions_disabled(self) -> bool:
        host = (urlsplit(self.s.paytm_host).hostname or "").rstrip(".").casefold()
        environment = str(getattr(self.s, "app_env", "production")).strip().casefold()
        if host in STAGING_HOSTS:
            return environment not in {"development", "test", "staging"} or not bool(getattr(self.s, "paytm_test_enabled", False))
        return environment != "production" or not bool(getattr(self.s, "paytm_live_enabled", False))

    def _payment_gate_error(self) -> str:
        host = (urlsplit(self.s.paytm_host).hostname or "").rstrip(".").casefold()
        environment = str(getattr(self.s, "app_env", "production")).strip().casefold()
        if host in STAGING_HOSTS:
            if environment not in {"development", "test", "staging"}:
                return "Paytm staging requests are disabled in production mode"
            return "Paytm test payments are disabled; set PAYTM_TEST_ENABLED=true in a non-production environment explicitly"
        return "Production Paytm payments are disabled; complete release review and set PAYTM_LIVE_ENABLED=true explicitly"

    def _post(self, path: str, body: dict, token_type: str | None = "AES", ts_key: str = "timestamp",
              extra_head: dict | None = None) -> dict:
        """Link APIs take head.timestamp + tokenType AES; v3 status and Initiate Transaction take
        head.requestTimestamp and no tokenType. The signature is over the exact body string sent."""
        head = {"signature": _sign(body, self.s.paytm_merchant_key), ts_key: str(int(time.time()))}
        if token_type:
            head["tokenType"] = token_type
        if extra_head:
            head.update(extra_head)
        payload = json.dumps({"head": head, "body": body}, separators=(",", ":"))
        r = self.http.post(self.s.paytm_host.rstrip("/") + path, content=payload,
                           headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()

    def _verified_status_body(self, data: dict) -> dict | None:
        """Return a status response body only when its Paytm checksum is valid."""
        if not isinstance(data, dict):
            return None
        head, body = data.get("head"), data.get("body")
        signature = head.get("signature") if isinstance(head, dict) else None
        if not isinstance(body, dict) or not isinstance(signature, str) or not signature:
            return None
        body_json = json.dumps(body, separators=(",", ":"))
        if not verify_signature(body_json, self.s.paytm_merchant_key, signature):
            return None
        return body

    @staticmethod
    def _response_body(data) -> dict | None:
        if not isinstance(data, dict):
            return None
        body = data.get("body")
        return body if isinstance(body, dict) else None

    @staticmethod
    def merchant_request_id(idempotency_key: str) -> str:
        """Paytm has no documented server-side dedupe for Create Link, so our key travels as
        merchantRequestId (letters and digits only, well under 64 chars) and is looked up before a retry."""
        return "wapas" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]

    def _find_link(self, mrid: str) -> LinkResult | None:
        """Look up a link by its stable merchant request ID.

        None means Paytm returned a successful, well-formed empty result. Transport errors,
        API failures, and malformed responses raise so callers cannot mistake an unknown
        lookup result for proof that creating another link is safe.
        """
        data = self._post("/link/fetch", {"mid": self.s.paytm_mid, "merchantRequestId": mrid},
                          extra_head={"channelId": "WEB"})
        body = data.get("body")
        info = body.get("resultInfo") if isinstance(body, dict) else None
        if not isinstance(info, dict) or str(info.get("resultStatus", "")).upper() not in LINK_API_OK:
            raise RuntimeError("Paytm link lookup did not return a successful result")
        links = body.get("links")
        if not isinstance(links, list):
            raise RuntimeError("Paytm link lookup returned no links list")
        if not links:
            return None

        active = []
        inactive = []
        for ln in links:
            if not isinstance(ln, dict) or not ln.get("linkId"):
                raise RuntimeError("Paytm link lookup returned a malformed link")
            result = LinkResult(ok=True, link_id=str(ln["linkId"]), short_url=ln.get("shortUrl", ""))
            (inactive if ln.get("isActive", True) is False else active).append(result)
        if active:
            return active[0]
        # The stable request ID already belongs to an inactive link. Do not create another
        # link under the same logical action; the caller can surface/review this failure.
        return LinkResult(ok=False, error="Paytm already has an inactive link for this request")

    def create_link(self, *, idempotency_key, amount_paise, customer_name, customer_phone,
                    description, callback_url) -> LinkResult:
        if self._payment_actions_disabled():
            return LinkResult(ok=False, error=self._payment_gate_error())
        desc = (description or "Payment")[:30]
        if len(desc) < 3:
            desc = "Payment"
        body = {
            "mid": self.s.paytm_mid,
            "linkType": "FIXED",
            "linkName": self.s.merchant_name[:64].replace(" ", ""),
            "linkDescription": desc,
            "amount": round(amount_paise / 100, 2),
            # No customerContact: Wapas delivers the link itself (sendSms/sendEmail are off), so Paytm
            # does not need the customer's phone. Staging also rejects many numbers with 6019.
            "partialPayment": False,  # documented as mandatory
            "bindLinkIdMobile": False,  # documented as mandatory
            "sendSms": False,
            "sendEmail": False,
            "maxPaymentsAllowed": "1",  # documented as a string
            "expiryDate": (datetime.now(IST) + timedelta(days=1)).strftime("%d/%m/%Y %H:%M:%S"),
            "statusCallbackUrl": callback_url,
            "linkNotes": f"wapas:{idempotency_key}"[:254],
            "merchantRequestId": self.merchant_request_id(idempotency_key),
        }
        # Always check Paytm before creating. The ActionRecord retry may run in a new
        # process after an ambiguous timeout, so an in-memory uncertainty flag is not enough.
        try:
            found = self._find_link(body["merchantRequestId"])
        except Exception as e:  # noqa: BLE001
            return LinkResult(ok=False, error=f"Paytm link lookup failed; no create attempted: {type(e).__name__}: {e}")
        if found is not None:
            return found
        try:
            data = self._post(self.s.paytm_link_create_path, body)
        except Exception as e:  # noqa: BLE001
            return LinkResult(ok=False, error=f"{type(e).__name__}: {e}")
        b = self._response_body(data)
        if b is None or not isinstance(b.get("resultInfo"), dict):
            return LinkResult(ok=False, error="Paytm link creation returned a malformed response")
        info = b["resultInfo"]
        if info.get("resultStatus") == "SUCCESS" and b.get("linkId"):
            return LinkResult(ok=True, link_id=str(b["linkId"]), short_url=b.get("shortUrl", ""))
        code = str(info.get("resultCode", ""))
        return LinkResult(ok=False, error=f"{code}: {info.get('resultMessage')}" + hint(code, "link"))

    def probe_links(self) -> tuple[bool, str]:
        """Doctor --deep: can this MID create a Payment Link? Creates one ₹1 link that expires in a
        day, with no customer attached and no SMS/email, so nobody is contacted."""
        if self._payment_actions_disabled():
            return False, self._payment_gate_error()
        body = {"mid": self.s.paytm_mid, "linkType": "FIXED", "linkName": "WapasDoctor",
                "linkDescription": "Wapas doctor check", "amount": 1.0, "partialPayment": False,
                "bindLinkIdMobile": False, "sendSms": False, "sendEmail": False, "maxPaymentsAllowed": "1",
                "expiryDate": (datetime.now(IST) + timedelta(days=1)).strftime("%d/%m/%Y %H:%M:%S"),
                "linkNotes": "wapas:doctor", "merchantRequestId": f"wapasdoctor{int(time.time())}"}
        try:
            data = self._post(self.s.paytm_link_create_path, body)
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"
        b = self._response_body(data)
        if b is None or not isinstance(b.get("resultInfo"), dict):
            return False, "Paytm link probe returned a malformed response"
        info = b["resultInfo"]
        if info.get("resultStatus") in LINK_API_OK and b.get("linkId"):
            return True, f"link {b['linkId']} created (₹1, expires in 24 h, nobody notified)"
        code = str(info.get("resultCode", ""))
        return False, f"{code}: {info.get('resultMessage') or info.get('resultMsg')}" + hint(code, "link")

    def link_status(self, link_id) -> StatusResult:
        """Paid only if Paytm says so. Fetch Link Transactions finds the order; the v3 Transaction
        Status API must confirm its merchant ID, order ID, amount and terminal result. Link fetch alone
        never establishes payment, including when the status API has no record of that order."""
        try:
            data = self._post(self.s.paytm_link_fetch_txn_path, {"mid": self.s.paytm_mid, "linkId": link_id})
        except Exception as e:  # noqa: BLE001
            return StatusResult(PayStatus.ERROR, raw={"error": str(e)})
        b = self._response_body(data)
        if b is None or not isinstance(b.get("resultInfo"), dict):
            return StatusResult(PayStatus.ERROR, raw={"error": "Paytm link status returned a malformed response"})
        info = b["resultInfo"]
        orders = b.get("orders")
        if orders is None:
            orders = b.get("orderDetails", [])
        if not isinstance(orders, list):
            return StatusResult(PayStatus.ERROR, raw={"error": "Paytm link status returned a malformed orders list"})
        for o in orders:
            if not isinstance(o, dict):
                return StatusResult(PayStatus.ERROR, raw={"error": "Paytm link status returned a malformed order"})
            st = str(o.get("orderStatus") or o.get("txnStatus") or o.get("status") or "").upper()
            if st in SUCCESS_WORDS | FAIL_WORDS:
                order_id = o.get("orderId", "")
                confirmed = self.order_status(order_id) if isinstance(order_id, str) and order_id else None
                expected = PayStatus.SUCCESS if st in SUCCESS_WORDS else PayStatus.FAILED
                if confirmed and confirmed.status == expected:
                    confirmed.raw = dict(confirmed.raw or {}) | {"_verified_link_id": link_id}
                    return confirmed
                return StatusResult(PayStatus.ERROR, raw={"note": "link terminal status was not confirmed by order status",
                                                          "order": o, "status": confirmed.raw if confirmed else None})
        rs = str(info.get("resultStatus", "")).upper()
        if info and rs not in LINK_API_OK and str(info.get("resultCode")) != "404":
            return StatusResult(PayStatus.ERROR, raw=b)
        return StatusResult(PayStatus.PENDING, raw=b)

    def order_status(self, order_id: str) -> StatusResult:
        try:
            data = self._post(self.s.paytm_order_status_path, {"mid": self.s.paytm_mid, "orderId": order_id},
                              token_type=None, ts_key="requestTimestamp")
        except Exception as e:  # noqa: BLE001
            return StatusResult(PayStatus.ERROR, raw={"error": str(e)})
        b = self._verified_status_body(data)
        if b is None:
            return StatusResult(PayStatus.ERROR, raw={
                "error": "Paytm status response checksum is missing or invalid",
            })
        info = b.get("resultInfo")
        if not isinstance(info, dict):
            return StatusResult(PayStatus.ERROR, raw={"error": "Paytm status response is missing result information"})
        st = str(info.get("resultStatus", "")).upper()
        code = str(info.get("resultCode", ""))
        msg = str(info.get("resultMsg") or info.get("resultMessage") or "").lower()
        # Codes per Paytm's Transaction Status API v3 docs + response-codes PDF. Several "failures" are
        # not about the customer's payment at all, and must never open or close a case.
        if "system error" in msg or "server down" in msg:
            return StatusResult(PayStatus.ERROR, raw=b)  # Paytm could not answer: UNKNOWN, never a result
        if code in ("330", "2005") or "checksum" in msg:
            return StatusResult(PayStatus.ERROR, raw=b)  # our signature/key is wrong
        if code == "335" or "invalid mid" in msg or "mid is invalid" in msg:
            return StatusResult(PayStatus.ERROR, raw=b)  # our configuration is wrong
        if code in ("334", "331") or st == "NO_RECORD_FOUND" or "invalid order" in msg:
            return StatusResult(PayStatus.NOT_FOUND, raw=b)  # 334 arrives as TXN_FAILURE: it is not a failed payment
        if st in SUCCESS_WORDS | FAIL_WORDS and (
                str(b.get("mid") or "") != self.s.paytm_mid
                or str(b.get("orderId") or "") != order_id):
            return StatusResult(PayStatus.ERROR, raw={
                "identity_error": "terminal status response did not match the requested MID and order ID",
                "response": b,
            })
        if st in SUCCESS_WORDS:
            txn_id = b.get("txnId")
            if not isinstance(txn_id, str) or not txn_id or txn_id != txn_id.strip():
                return StatusResult(PayStatus.ERROR, raw={
                    "error": "Paytm success response did not contain a valid transaction ID",
                })
            try:
                amount = Decimal(str(b.get("txnAmount")))
                paise_decimal = amount * 100
                if (not amount.is_finite() or amount <= 0
                        or paise_decimal != paise_decimal.to_integral_value()
                        or paise_decimal > Decimal(2**63 - 1)):
                    raise InvalidOperation
                paise = int(paise_decimal)
            except (InvalidOperation, ValueError, TypeError):
                return StatusResult(PayStatus.ERROR, raw={
                    "error": "Paytm success response did not contain a valid INR amount",
                })
            return StatusResult(PayStatus.SUCCESS, txn_id=txn_id, amount_paise=paise, raw=b)
        if st in FAIL_WORDS:
            return StatusResult(PayStatus.FAILED, raw=b)
        return StatusResult(PayStatus.PENDING, raw=b)

    # --- checkout (the merchant's real store takes payments through Paytm) ---
    def initiate_checkout(self, *, order_id: str, amount_paise: int, cust_id: str, callback_url: str) -> dict:
        if self._payment_actions_disabled():
            return {"ok": False, "error": self._payment_gate_error()}
        body = {"requestType": "Payment", "mid": self.s.paytm_mid, "websiteName": self.s.paytm_website,
                "orderId": order_id, "callbackUrl": callback_url,
                "txnAmount": {"value": f"{amount_paise / 100:.2f}", "currency": "INR"},
                "userInfo": {"custId": cust_id}}
        path = f"/theia/api/v1/initiateTransaction?mid={self.s.paytm_mid}&orderId={order_id}"
        try:
            data = self._post(path, body, token_type=None, ts_key="requestTimestamp")
        except Exception as e:  # noqa: BLE001
            # The request may have reached Paytm even though the response did not.
            # The caller must keep the order pollable until status is established.
            return {"ok": False, "uncertain": True, "error": f"{type(e).__name__}: {e}"}
        b = self._response_body(data)
        if b is None or not isinstance(b.get("resultInfo"), dict):
            return {"ok": False, "error": "Paytm checkout returned a malformed response"}
        info = b["resultInfo"]
        if info.get("resultStatus") == "S" and b.get("txnToken"):
            host = self.s.paytm_host.rstrip("/")
            return {"ok": True, "mode": "paytm", "mid": self.s.paytm_mid, "order_id": order_id, "txn_token": b["txnToken"],
                    "amount": f"{amount_paise / 100:.2f}",
                    "script_url": f"{host}/merchantpgpui/checkoutjs/merchants/{self.s.paytm_mid}.js"}
        code = str(info.get("resultCode", ""))
        return {"ok": False, "error": f"{code}: {info.get('resultMsg')}" + hint(code, "checkout")}

    def verify_callback(self, payload: dict) -> bool:
        checksum = payload.get("CHECKSUMHASH")
        if not checksum:
            return False
        params = {k: str(v) for k, v in payload.items() if k != "CHECKSUMHASH"}
        return verify_signature(params, self.s.paytm_merchant_key, checksum)
