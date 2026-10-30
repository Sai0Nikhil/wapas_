"""Validation and transactional outbox writes for server-verified Paytm successes."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlmodel import Session, select

from . import audit
from .config import get_settings
from .models import Payment
from .ports import PayStatus, StatusResult
from .sound_models import SoundEvent


def _paise(value) -> int | None:
    try:
        amount = Decimal(str(value))
        paise = amount * 100
        if not amount.is_finite() or paise != paise.to_integral_value():
            return None
        return int(paise)
    except (InvalidOperation, ValueError, TypeError):
        return None


def verify_paytm_status(payment: Payment, result: StatusResult, *, gateway_name: str,
                        expected_order_id: str = "", expected_link_id: str = "") -> bool:
    """Require provider identity and amount binding before accepting a Paytm terminal result."""
    if payment.provider not in {"paytm", "unknown"} or gateway_name != "paytm" or result.status not in {PayStatus.SUCCESS, PayStatus.FAILED}:
        return False
    raw = result.raw if isinstance(result.raw, dict) else {}
    configured_mid = get_settings().paytm_mid
    reported_mid = str(raw.get("mid") or raw.get("MID") or "")
    reported_order = str(raw.get("orderId") or raw.get("ORDERID") or "")
    expected_mid = payment.provider_mid or configured_mid
    if not configured_mid or expected_mid != configured_mid or reported_mid != expected_mid:
        return False
    if expected_link_id:
        if str(raw.get("_verified_link_id") or "") != expected_link_id:
            return False
        if not reported_order or (payment.provider_order_id and reported_order != payment.provider_order_id):
            return False
    else:
        expected_order_id = expected_order_id or payment.provider_order_id or payment.order_id
        if not expected_order_id or reported_order != expected_order_id:
            return False
    reported_currency = raw.get("currency") or raw.get("txnCurrency") or payment.currency
    if str(reported_currency).upper() != payment.currency.upper():
        return False
    if result.status == PayStatus.SUCCESS:
        if (not result.txn_id or str(raw.get("txnId") or raw.get("TXNID") or "") != result.txn_id
                or result.amount_paise != payment.amount_paise):
            return False
        reported_amount = _paise(raw.get("txnAmount"))
        if reported_amount != payment.amount_paise:
            return False
    return True


def record_verified_success(session: Session, payment: Payment, result: StatusResult, *, gateway_name: str,
                            expected_order_id: str = "", expected_link_id: str = "") -> bool:
    """Update attempt facts and append one idempotent notification in the caller's transaction."""
    if payment.provider in {"paytm", "unknown"} and gateway_name == "paytm":
        if not verify_paytm_status(payment, result, gateway_name=gateway_name,
                                   expected_order_id=expected_order_id, expected_link_id=expected_link_id):
            return False
    elif payment.provider not in {"fake", "unknown"} or gateway_name != "fake" or result.status != PayStatus.SUCCESS:
        return False

    now = datetime.now(timezone.utc)
    raw = result.raw if isinstance(result.raw, dict) else {}
    if gateway_name == "paytm":
        payment.provider = "paytm"
    elif payment.provider == "unknown":
        payment.provider = "fake"
    payment.status = "SUCCESS"
    payment.provider_order_id = str(raw.get("orderId") or payment.provider_order_id or expected_order_id)
    payment.provider_transaction_id = result.txn_id
    payment.verified_at = now
    session.add(payment)
    if payment.provider != "paytm":
        return True

    key = "sound:verified-payment:" + payment.id
    prior = session.exec(select(SoundEvent).where(
        SoundEvent.merchant_id == payment.merchant_id, SoundEvent.idempotency_key == key,
    )).first()
    if prior is None:
        event = SoundEvent(
            merchant_id=payment.merchant_id, store_id=payment.store_id, payment_id=payment.id,
            source_type=payment.source_type, source_id=payment.source_id,
            provider_order_id=payment.provider_order_id, provider_transaction_id=result.txn_id,
            amount_paise=payment.amount_paise, currency=payment.currency,
            idempotency_key=key, verified_at=now,
        )
        session.add(event)
        audit.record(
            session, action="payment.paytm_verified", entity_type="payment", entity_id=payment.id,
            merchant_id=payment.merchant_id, store_id=payment.store_id,
            source="paytm-status", idempotency_key="audit:payment:verified:" + payment.id,
            payload={"source_type": payment.source_type, "source_id": payment.source_id,
                     "amount_paise": payment.amount_paise, "currency": payment.currency,
                     "provider_order_id": payment.provider_order_id,
                     "provider_transaction_id": result.txn_id},
        )
    return True


def record_terminal_failure(payment: Payment, result: StatusResult, *, gateway_name: str,
                            expected_order_id: str = "", expected_link_id: str = "") -> bool:
    if payment.provider in {"paytm", "unknown"} and gateway_name == "paytm":
        if not verify_paytm_status(payment, result, gateway_name=gateway_name,
                                   expected_order_id=expected_order_id, expected_link_id=expected_link_id):
            return False
    elif payment.provider not in {"fake", "unknown"} or gateway_name != "fake" or result.status != PayStatus.FAILED:
        return False
    payment.status = "FAILED"
    if gateway_name == "paytm":
        payment.provider = "paytm"
    elif payment.provider == "unknown":
        payment.provider = "fake"
    return True
