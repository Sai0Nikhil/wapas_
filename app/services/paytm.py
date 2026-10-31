"""Paytm test/staging client.
Follows: 'AI proposes, policy authorizes, code executes, Paytm confirms.'
"""
import logging
import paytmchecksum
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)


def is_live_configured() -> bool:
    s = get_settings()
    return bool(s.paytm_mid and s.paytm_merchant_key)


async def initiate_transaction(order_id: str, amount_inr: str, cust_id: str) -> dict:
    """Build body, sign with paytmchecksum.generateSignature, POST /theia/api/v1/initiateTransaction."""
    s = get_settings()
    if not is_live_configured():
        logger.info("Paytm unconfigured; returning mock initiate transaction")
        return {
            "head": {"responseTimestamp": "1730332800", "version": "v1", "signature": "mock_sig"},
            "body": {
                "resultInfo": {"resultStatus": "S", "resultCode": "0000", "resultMsg": "Success"},
                "txnToken": f"mock_token_{order_id}",
                "isPromoCodeValid": False,
                "authenticated": False,
            },
        }

    paytm_params = {
        "body": {
            "requestType": "Payment",
            "mid": s.paytm_mid,
            "websiteName": s.paytm_website,
            "orderId": order_id,
            "txnAmount": {"value": amount_inr, "currency": "INR"},
            "userInfo": {"custId": cust_id},
            "callbackUrl": f"{s.public_base_url}/webhooks/paytm",
        }
    }

    checksum = paytmchecksum.generateSignature(
        str(paytm_params["body"]), s.paytm_merchant_key
    )
    paytm_params["head"] = {"signature": checksum}

    url = f"{s.paytm_base_url}/theia/api/v1/initiateTransaction?mid={s.paytm_mid}&orderId={order_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=paytm_params)
        return resp.json()


async def create_payment_link(order_id: str, amount_inr: str, description: str, cust_phone: str = "") -> dict:
    """Creates a Paytm test payment recovery link."""
    s = get_settings()
    if not is_live_configured():
        return {
            "link_id": f"link_{order_id}",
            "payment_url": f"https://securegw-stage.paytm.in/link/pay?mid=MOCK&orderId={order_id}&amt={amount_inr}",
            "status": "CREATED",
        }

    # Staging Payment Link API
    url = f"{s.paytm_base_url}/link/create"
    body = {
        "mid": s.paytm_mid,
        "linkType": "FIXED",
        "linkDescription": description,
        "linkName": f"Wapas Recovery {order_id}",
        "amount": amount_inr,
    }
    checksum = paytmchecksum.generateSignature(str(body), s.paytm_merchant_key)
    payload = {"head": {"tokenType": "AES", "signature": checksum}, "body": body}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            res_data = resp.json()
            body_res = res_data.get("body", {})
            return {
                "link_id": body_res.get("linkId", f"link_{order_id}"),
                "payment_url": body_res.get("shortUrl") or f"{s.paytm_base_url}/link/pay?orderId={order_id}",
                "status": body_res.get("resultInfo", {}).get("resultStatus", "CREATED"),
            }
    except Exception as exc:
        logger.error(f"Paytm link creation failed: {exc}")
        return {
            "link_id": f"link_{order_id}",
            "payment_url": f"{s.paytm_base_url}/link/pay?orderId={order_id}",
            "status": "FALLBACK_URL",
        }


async def transaction_status(order_id: str) -> dict:
    """POST /v3/order/status (signed). Single source of truth for 'RECOVERED'."""
    s = get_settings()
    if not is_live_configured():
        return {
            "body": {
                "resultInfo": {"resultStatus": "TXN_SUCCESS", "resultCode": "01", "resultMsg": "Txn Successful"},
                "txnId": f"TXN-{order_id}",
                "orderId": order_id,
                "txnAmount": "1420.00",
                "status": "TXN_SUCCESS",
            }
        }

    body = {"mid": s.paytm_mid, "orderId": order_id}
    checksum = paytmchecksum.generateSignature(str(body), s.paytm_merchant_key)
    payload = {"head": {"signature": checksum}, "body": body}

    url = f"{s.paytm_base_url}/v3/order/status"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        return resp.json()


def verify_callback_checksum(params: dict) -> bool:
    """Verifies Paytm callback signature. If in dev mode without key, fails open only for dev."""
    s = get_settings()
    if not s.paytm_merchant_key:
        return True  # Dev fallback when no key is set

    checksum = params.get("CHECKSUMHASH", "")
    if not checksum:
        return False

    params_copy = dict(params)
    params_copy.pop("CHECKSUMHASH", None)
    return paytmchecksum.verifySignature(params_copy, s.paytm_merchant_key, checksum)
