"""Single terminal settlement path for checkout and collection payment attempts."""
from datetime import datetime, timezone

from sqlmodel import select

from . import audit, inventory, khata
from .billing_models import Bill, BillLine
from .commerce_models import StoreOrder, StoreOrderLine
from .merchant_os_models import InventoryReservation
from .models import Payment
from .payment_events import record_terminal_failure, record_verified_success, verify_paytm_status
from .ports import PayStatus, StatusResult


def _is_acceptable(payment: Payment, result: StatusResult, gateway_name: str,
                   expected_order_id: str, expected_link_id: str) -> bool:
    if payment.provider in {"paytm", "unknown"} and gateway_name == "paytm":
        return verify_paytm_status(payment, result, gateway_name=gateway_name,
                                   expected_order_id=expected_order_id, expected_link_id=expected_link_id)
    return (payment.provider in {"fake", "unknown"} and gateway_name == "fake"
            and result.status in {PayStatus.SUCCESS, PayStatus.FAILED})


def _settle_shop_order(session, payment: Payment, succeeded: bool, *, gateway_name: str) -> str:
    order = session.exec(select(StoreOrder).where(
        StoreOrder.id == payment.source_id, StoreOrder.merchant_id == payment.merchant_id,
        StoreOrder.store_id == payment.store_id,
    )).first()
    if order is None or order.payment_id != payment.id:
        return "SOURCE_MISSING"
    if order.status != "PAYMENT_PENDING":
        return "ALREADY_SETTLED"
    lines = session.exec(select(StoreOrderLine).where(
        StoreOrderLine.order_id == order.id, StoreOrderLine.merchant_id == payment.merchant_id,
        StoreOrderLine.store_id == payment.store_id,
    )).all()
    simulated = succeeded and gateway_name == "fake"
    for line in lines:
        if not line.reservation_id:
            continue
        if succeeded and not simulated:
            inventory.complete_reservation(session, merchant_id=payment.merchant_id, store_id=payment.store_id,
                                           reservation_id=line.reservation_id)
        else:
            inventory.release_stock(session, merchant_id=payment.merchant_id, store_id=payment.store_id,
                                    reservation_id=line.reservation_id,
                                    source="payment_simulated" if simulated else "payment_failed")
    now = datetime.now(timezone.utc)
    order.status = "SIMULATED" if simulated else ("PAID" if succeeded else "PAYMENT_FAILED")
    order.updated_at = now
    if succeeded and not simulated:
        order.paid_at = now
    session.add(order)
    audit.record(session, action=("shop.payment_simulated" if simulated else
                                  "shop.payment_verified" if succeeded else "shop.payment_failed"),
                 entity_type="store_order", entity_id=order.id, merchant_id=payment.merchant_id,
                 store_id=payment.store_id, source="paytm-status" if gateway_name == "paytm" else "fake-gateway",
                 idempotency_key="shop-settlement:" + payment.id + ":" + order.status,
                 payload={"status": order.status, "amount_paise": payment.amount_paise})
    return order.status


def _settle_counter_bill(session, payment: Payment, succeeded: bool) -> str:
    bill = session.exec(select(Bill).where(
        Bill.id == payment.source_id, Bill.merchant_id == payment.merchant_id,
        Bill.store_id == payment.store_id,
    )).first()
    if bill is None or bill.state != "ISSUED" or bill.total_paise != payment.amount_paise:
        return "SOURCE_MISSING"
    if bill.payment_state == "PAID":
        return "ALREADY_PAID"
    if bill.payment_id not in (None, payment.id):
        return "STALE_ATTEMPT"
    lines = session.exec(select(BillLine).where(
        BillLine.bill_id == bill.id, BillLine.merchant_id == payment.merchant_id,
        BillLine.store_id == payment.store_id,
    )).all()
    if succeeded and payment.provider == "paytm":
        try:
            with session.begin_nested():
                for line in lines:
                    found = inventory.lookup_product(session, merchant_id=payment.merchant_id,
                                                     store_id=payment.store_id, product_id=line.product_id)
                    if found is None or found[0].is_service:
                        continue
                    reservation_id = f"counter:{bill.id}:{line.product_id}"
                    reservation = session.exec(select(InventoryReservation).where(
                        InventoryReservation.id == reservation_id,
                        InventoryReservation.merchant_id == payment.merchant_id,
                        InventoryReservation.store_id == payment.store_id,
                    )).first()
                    if reservation is None:
                        # Compatibility for issued bills created before Counter
                        # began reserving stock at issue time.
                        inventory.sell_stock(
                            session, merchant_id=payment.merchant_id, store_id=payment.store_id,
                            product_id=line.product_id, quantity=line.quantity, source_ref=bill.id,
                            source="counter_bill", idempotency_key=f"counter-sale:{payment.id}:{line.id}",
                        )
                    elif reservation.state == "HELD":
                        inventory.complete_reservation(
                            session, merchant_id=payment.merchant_id, store_id=payment.store_id,
                            reservation_id=reservation_id,
                        )
                    elif reservation.state != "CONSUMED":
                        raise inventory.InventoryConflict("Counter stock reservation is no longer held")
        except inventory.InventoryError:
            return "RECONCILIATION_REQUIRED"
    bill.payment_state = ("SIMULATED" if payment.provider == "fake" else "PAID") if succeeded else "FAILED"
    bill.payment_id = payment.id
    bill.updated_at = datetime.now(timezone.utc)
    if succeeded and payment.provider == "paytm":
        bill.paid_at = bill.updated_at
    session.add(bill)
    event = ("counter.payment_simulated" if payment.provider == "fake" else "counter.payment_verified") if succeeded else "counter.payment_failed"
    audit.record(session, action=event,
                 entity_type="bill", entity_id=bill.id, merchant_id=payment.merchant_id,
                 store_id=payment.store_id, source="paytm-status" if payment.provider == "paytm" else "fake-gateway",
                 idempotency_key="counter-payment:" + payment.id + ":" + bill.payment_state,
                 payload={"payment_id": payment.id, "payment_state": bill.payment_state,
                          "amount_paise": payment.amount_paise})
    return bill.payment_state


def _settle_khata(session, payment: Payment, result: StatusResult, succeeded: bool) -> str:
    if not succeeded:
        return "FAILED"
    if payment.provider != "paytm":
        return "SIMULATED"
    try:
        entry, balance = khata.record_verified_paytm_repayment(
            session, merchant_id=payment.merchant_id, store_id=payment.store_id,
            account_id=payment.source_id, amount_paise=payment.amount_paise, payment_id=payment.id,
            note="Paytm transaction " + result.txn_id,
        )
    except khata.KhataError:
        return "RECONCILIATION_REQUIRED"
    audit.record(session, action="khata.paytm_collection_verified", entity_type="khata_account",
                 entity_id=payment.source_id, merchant_id=payment.merchant_id, store_id=payment.store_id,
                 source="paytm-status", idempotency_key="audit:khata-paytm:" + payment.id,
                 payload={"payment_id": payment.id, "entry_id": entry.id,
                          "amount_paise": payment.amount_paise, "outstanding_paise": balance})
    return "PAID"


def apply_terminal_result(session, payment: Payment, result: StatusResult, *, gateway_name: str,
                          expected_order_id: str = "", expected_link_id: str = "") -> str:
    """Verify, settle the source once, then commit the payment fact and outbox with the caller."""
    if result.status not in {PayStatus.SUCCESS, PayStatus.FAILED}:
        return "PENDING"
    succeeded = result.status == PayStatus.SUCCESS
    if succeeded and result.amount_paise != payment.amount_paise:
        payment.status = "PENDING_RECONCILIATION"
        session.add(payment)
        return "AMOUNT_MISMATCH"
    if not _is_acceptable(payment, result, gateway_name, expected_order_id, expected_link_id):
        payment.status = "PENDING_RECONCILIATION"
        session.add(payment)
        return "UNVERIFIED"
    if gateway_name == "paytm":
        payment.provider = "paytm"

    if payment.status == "SUCCESS":
        if succeeded and payment.provider_transaction_id == result.txn_id:
            return "SUCCESS"
        payment.status = "PENDING_RECONCILIATION"
        session.add(payment)
        return "CONFLICTING_TERMINAL_RESULT"
    if payment.status == "SIMULATED" and succeeded and gateway_name == "fake":
        return "SIMULATED"
    if payment.status == "FAILED" and not succeeded:
        return "FAILED"

    source_result = "SUCCESS" if succeeded else "FAILED"
    if payment.source_type == "SHOP_ORDER":
        source_result = _settle_shop_order(session, payment, succeeded, gateway_name=gateway_name)
        if source_result == "SOURCE_MISSING":
            payment.status = "PENDING_RECONCILIATION"
            session.add(payment)
            return source_result
    elif payment.source_type == "COUNTER_BILL":
        source_result = _settle_counter_bill(session, payment, succeeded)
        if source_result in {"SOURCE_MISSING", "RECONCILIATION_REQUIRED"}:
            payment.status = "PENDING_RECONCILIATION"
            session.add(payment)
            return source_result
    elif payment.source_type == "KHATA_COLLECTION":
        source_result = _settle_khata(session, payment, result, succeeded)
        if source_result == "RECONCILIATION_REQUIRED":
            payment.status = "PENDING_RECONCILIATION"
            session.add(payment)
            return source_result

    if source_result in {"ALREADY_PAID", "ALREADY_SETTLED", "STALE_ATTEMPT"}:
        payment.status = "PENDING_RECONCILIATION"
        session.add(payment)
        return source_result

    # The offline gateway is useful for exercising the workflow, but it is not
    # evidence that money moved. Counter and Khata keep that distinction in
    # their canonical state and never emit the Paytm payment outbox event.
    if succeeded and gateway_name == "fake" and payment.source_type in {
        "SHOP_ORDER", "COUNTER_BILL", "KHATA_COLLECTION",
    }:
        payment.status = "SIMULATED"
        session.add(payment)
        return "SIMULATED"

    if succeeded:
        if not record_verified_success(session, payment, result, gateway_name=gateway_name,
                                       expected_order_id=expected_order_id, expected_link_id=expected_link_id):
            raise RuntimeError("Payment verification changed during terminal settlement")
    elif not record_terminal_failure(payment, result, gateway_name=gateway_name,
                                     expected_order_id=expected_order_id, expected_link_id=expected_link_id):
        raise RuntimeError("Payment failure verification changed during terminal settlement")
    return source_result
