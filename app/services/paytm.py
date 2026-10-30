"""Paytm client. TODO (hours 0-2 and 4-6)."""
import httpx  # noqa: F401

from app.config import get_settings


async def initiate_transaction(order_id: str, amount_inr: str, cust_id: str) -> dict:
    """TODO: build body, sign with paytmchecksum.generateSignature, POST /theia/api/v1/initiateTransaction."""
    raise NotImplementedError


async def create_payment_link(order_id: str, amount_inr: str, description: str) -> dict:
    """TODO: Paytm Payment Link API (test mode). Fallback: hosted initiate-transaction page."""
    raise NotImplementedError


async def transaction_status(order_id: str) -> dict:
    """TODO: POST /v3/order/status (signed). Only source of truth for 'recovered'."""
    raise NotImplementedError


def verify_callback_checksum(params: dict) -> bool:
    """TODO: paytmchecksum.verifySignature(params, merchant_key, CHECKSUMHASH)."""
    return True  # DEV ONLY: replace before demo
