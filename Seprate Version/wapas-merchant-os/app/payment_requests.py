"""Idempotent Payment Link requests for issued Counter bills and Khata accounts."""
import hashlib
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlmodel import select

from . import billing, inventory, khata
from .config import get_settings
from .db import session
from .gateway import get_gateway
from .models import Customer, Payment
from .khata_models import KhataLedgerEntry
from .tenant_context import current_merchant_id, current_store_id
from .billing_models import Bill


def _request_link(*, source_type: str, source_id: str, amount_paise: int, customer: Customer,
                  idempotency_key: str, merchant_id: str, store_id: str) -> dict:
    if amount_paise <= 0:
        raise HTTPException(409, "A zero-value bill or collection cannot be paid")
    cfg = get_settings()
    provider = get_gateway()
    if provider.name == "paytm":
        parsed = urlsplit(cfg.public_base_url.rstrip("/"))
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise HTTPException(409, "A public HTTPS address is required for Paytm collection")

    prefix = f"{source_type.lower()}:{merchant_id}:{store_id}:"
    request_key = idempotency_key if idempotency_key.startswith(prefix) else prefix + idempotency_key
    with session() as s:
        payment = s.exec(select(Payment).where(
            Payment.merchant_id == merchant_id, Payment.store_id == store_id,
            Payment.idempotency_key == request_key,
        )).first()
        if payment is None:
            active = s.exec(select(Payment).where(
                Payment.merchant_id == merchant_id, Payment.store_id == store_id,
                Payment.source_type == source_type, Payment.source_id == source_id,
                Payment.status.in_(("INIT_UNKNOWN", "PENDING", "PENDING_RECONCILIATION")),
            )).first()
            if active:
                if active.amount_paise != amount_paise or active.provider != provider.name:
                    raise HTTPException(409, "A different collection request is already pending for this bill or account")
                # Repeated clicks, a lost HTTP response, or a fresh browser session
                # resolve to the same pending provider attempt rather than making
                # a second link.
                payment = active
                if payment.provider_link_url:
                    return {
                        "payment_id": payment.id, "status": payment.status,
                        "payment_state": payment.status, "provider": payment.provider,
                        "checkout_url": payment.provider_link_url,
                        "idempotency_key": payment.idempotency_key,
                        "mode": "SIMULATED" if payment.provider == "fake" else "PAYTM",
                    }
                request_key = active.idempotency_key
            else:
                order_id = "WAP" + uuid.uuid4().hex[:20].upper()
                payment = Payment(
                    id="pay_" + order_id, merchant_id=merchant_id, store_id=store_id,
                    order_id=order_id, customer_id=customer.id, amount_paise=amount_paise,
                    currency="INR", source_type=source_type, source_id=source_id,
                    provider=provider.name, provider_mid=cfg.paytm_mid if provider.name == "paytm" else "",
                    idempotency_key=request_key, bank="", method="PAYMENT_LINK", status="INIT_UNKNOWN",
                )
                s.add(payment)
                if source_type == "COUNTER_BILL":
                    bill = s.exec(select(Bill).where(
                        Bill.id == source_id, Bill.merchant_id == merchant_id, Bill.store_id == store_id,
                    )).first()
                    if bill is None or bill.state != "ISSUED":
                        raise HTTPException(409, "Only an issued Counter bill can request payment")
                    if bill.payment_state == "PAID":
                        raise HTTPException(409, "This bill is already paid")
                    bill.payment_state, bill.payment_id = "PENDING", payment.id
                    s.add(bill)
                s.commit()
        elif payment.provider != provider.name:
            raise HTTPException(409, "The saved request belongs to a different payment provider")
        elif payment.status in {"SUCCESS", "FAILED", "SIMULATED"} or payment.provider_link_url:
            return {
                "payment_id": payment.id, "status": payment.status,
                "payment_state": payment.status, "provider": payment.provider,
                "checkout_url": payment.provider_link_url,
                "idempotency_key": payment.idempotency_key,
                "mode": "SIMULATED" if payment.provider == "fake" else "PAYTM",
            }
        payment_id = payment.id

    result = provider.create_link(
        idempotency_key=request_key, amount_paise=amount_paise,
        customer_name=customer.name or "Customer", customer_phone=customer.phone or "",
        description=("Counter bill " if source_type == "COUNTER_BILL" else "Khata collection ") + source_id[:18],
        callback_url=cfg.public_base_url.rstrip("/") + "/api/paytm/payment-callback",
    )
    with session() as s:
        payment = s.get(Payment, payment_id)
        if result.ok:
            payment.provider_link_id, payment.provider_link_url = result.link_id, result.short_url
            payment.status = "PENDING"
            s.add(payment)
            if source_type == "COUNTER_BILL":
                bill = s.get(Bill, source_id)
                if bill and bill.payment_id == payment.id:
                    bill.payment_state, bill.updated_at = "PENDING", datetime.now(timezone.utc)
                    s.add(bill)
        elif provider.name == "fake":
            payment.status = "INIT_FAILED"
            if source_type == "COUNTER_BILL":
                bill = s.get(Bill, source_id)
                if bill and bill.payment_id == payment.id:
                    bill.payment_state, bill.updated_at = "FAILED", datetime.now(timezone.utc)
                    s.add(bill)
        # Paytm failures remain INIT_UNKNOWN. Retrying the same key performs a
        # provider lookup before any new creation, so uncertainty cannot duplicate a link.
        s.add(payment)
        s.commit()
        return {
            "payment_id": payment.id, "status": payment.status,
            "payment_state": payment.status, "provider": payment.provider,
            "checkout_url": payment.provider_link_url,
            "idempotency_key": payment.idempotency_key,
            "mode": "SIMULATED" if provider.name == "fake" else ("PAYTM" if result.ok else "pending"),
            "detail": "" if result.ok else "The request is not confirmed. Retry with the same key.",
        }


def request_counter_bill_payment(bill_id: str, idempotency_key: str) -> dict:
    merchant_id, store_id = current_merchant_id(), current_store_id()
    with session() as s:
        try:
            bill, _lines = billing.get_bill(s, merchant_id=merchant_id, store_id=store_id, bill_id=bill_id)
        except (billing.BillingError, inventory.InventoryNotFound) as exc:
            raise HTTPException(404, str(exc)) from exc
        if bill.state != "ISSUED":
            raise HTTPException(409, "Only an issued Counter bill can request payment")
        if bill.payment_state == "PAID":
            raise HTTPException(409, "This bill is already paid")
        if s.exec(select(KhataLedgerEntry.id).where(
            KhataLedgerEntry.merchant_id == merchant_id, KhataLedgerEntry.store_id == store_id,
            KhataLedgerEntry.source_type == "counter_bill", KhataLedgerEntry.source_id == bill.id,
            KhataLedgerEntry.entry_type == "CREDIT_GIVEN",
        )).first():
            raise HTTPException(409, "This bill has been placed on Khata; collect through the Khata account")
        customer = None
        if bill.customer_phone:
            customer = s.exec(select(Customer).where(
                Customer.merchant_id == merchant_id, Customer.phone == bill.customer_phone,
            )).first()
        if customer is None:
            customer_id = "counter_" + hashlib.sha256(
                f"{merchant_id}:{store_id}:{bill.id}".encode("utf-8")
            ).hexdigest()[:24]
            customer = s.get(Customer, customer_id)
            if customer is None:
                customer = Customer(id=customer_id, merchant_id=merchant_id,
                                    name=bill.customer_name or "Counter customer",
                                    phone=bill.customer_phone or "")
                s.add(customer)
                s.flush()
        # Keep a detached copy after the context closes; only scalar customer data is used.
        customer_copy = Customer(id=customer.id, merchant_id=customer.merchant_id,
                                 name=customer.name, phone=customer.phone, language=customer.language)
        amount, merchant, store = bill.total_paise, bill.merchant_id, bill.store_id
    return _request_link(source_type="COUNTER_BILL", source_id=bill_id, amount_paise=amount,
                         customer=customer_copy, merchant_id=merchant, store_id=store,
                         idempotency_key=idempotency_key)


def request_khata_payment(account_id: str, amount_paise: int, idempotency_key: str) -> dict:
    merchant_id, store_id = current_merchant_id(), current_store_id()
    with session() as s:
        try:
            account, customer, _entries, outstanding = khata.account_history(
                s, merchant_id=merchant_id, store_id=store_id, account_id=account_id,
            )
        except khata.KhataError as exc:
            raise HTTPException(404, str(exc)) from exc
        if amount_paise <= 0 or amount_paise > outstanding:
            raise HTTPException(409, "Collection amount must be positive and no more than the outstanding balance")
        customer_copy = Customer(id=customer.id, merchant_id=customer.merchant_id,
                                 name=customer.name, phone=customer.phone, language=customer.language)
    return _request_link(source_type="KHATA_COLLECTION", source_id=account_id, amount_paise=amount_paise,
                         customer=customer_copy, merchant_id=merchant_id, store_id=store_id,
                         idempotency_key=idempotency_key)
