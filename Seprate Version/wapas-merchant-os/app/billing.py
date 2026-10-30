"""Canonical Counter bill service. Bills are independent from payment records."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from sqlmodel import Session, select

from .inventory import InventoryConflict, InventoryNotFound, lookup_product, reserve_stock, release_stock
from .merchant_os_models import InventoryReservation
from .khata_models import KhataLedgerEntry
from .models import Merchant, Payment, Store
from .billing_models import Bill, BillLine


class BillingError(Exception):
    """Base class for safe Counter workflow failures."""


def _quantity(value) -> Decimal:
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BillingError("quantity must be a decimal number") from exc
    if not quantity.is_finite() or quantity <= 0 or quantity != quantity.quantize(Decimal("0.001")):
        raise BillingError("quantity must be positive with at most three decimal places")
    return quantity


def _line_total(quantity: Decimal, unit_price_paise: int) -> int:
    return int((quantity * Decimal(unit_price_paise)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _bill(session: Session, *, merchant_id: str, store_id: str, bill_id: str) -> Bill:
    bill = session.exec(select(Bill).where(
        Bill.id == bill_id, Bill.merchant_id == merchant_id, Bill.store_id == store_id,
    )).first()
    if bill is None:
        raise InventoryNotFound("bill not found")
    return bill


def _recalculate(session: Session, bill: Bill) -> Bill:
    lines = session.exec(select(BillLine).where(
        BillLine.bill_id == bill.id, BillLine.merchant_id == bill.merchant_id,
        BillLine.store_id == bill.store_id,
    )).all()
    bill.subtotal_paise = sum(line.line_total_paise for line in lines)
    bill.total_paise = bill.subtotal_paise - bill.discount_paise + bill.tax_paise
    bill.updated_at = datetime.now(timezone.utc)
    session.add(bill)
    session.flush()
    return bill


def create_draft(session: Session, *, merchant_id: str, store_id: str,
                 idempotency_key: str = "", customer_name: str = "", customer_phone: str = "") -> Bill:
    merchant, store = session.get(Merchant, merchant_id), session.get(Store, store_id)
    if merchant is None or store is None or store.merchant_id != merchant_id:
        raise InventoryNotFound("merchant or store not found")
    if idempotency_key:
        existing = session.exec(select(Bill).where(
            Bill.merchant_id == merchant_id, Bill.store_id == store_id,
            Bill.idempotency_key == idempotency_key,
        )).first()
        if existing:
            return existing
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    bill = Bill(
        merchant_id=merchant_id, store_id=store_id,
        bill_number=f"{stamp}-{uuid4().hex[:6].upper()}",
        customer_name=customer_name.strip(), customer_phone=customer_phone.strip(),
        idempotency_key=idempotency_key or None,
    )
    session.add(bill)
    session.flush()
    return bill


def get_bill(session: Session, *, merchant_id: str, store_id: str, bill_id: str) -> tuple[Bill, list[BillLine]]:
    bill = _bill(session, merchant_id=merchant_id, store_id=store_id, bill_id=bill_id)
    lines = session.exec(select(BillLine).where(
        BillLine.bill_id == bill.id, BillLine.merchant_id == merchant_id,
        BillLine.store_id == store_id,
    ).order_by(BillLine.created_at, BillLine.id)).all()
    return bill, list(lines)


def list_bills(session: Session, *, merchant_id: str, store_id: str,
               limit: int = 30) -> list[Bill]:
    if not 1 <= limit <= 100:
        raise BillingError("bill limit must be between 1 and 100")
    return list(session.exec(select(Bill).where(
        Bill.merchant_id == merchant_id, Bill.store_id == store_id,
    ).order_by(Bill.created_at.desc()).limit(limit)).all())


def set_line(session: Session, *, merchant_id: str, store_id: str, bill_id: str,
             product_id: str, quantity) -> tuple[Bill, BillLine]:
    bill = _bill(session, merchant_id=merchant_id, store_id=store_id, bill_id=bill_id)
    if bill.state != "DRAFT":
        raise BillingError("only a draft bill can be edited")
    qty = _quantity(quantity)
    found = lookup_product(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id)
    if found is None:
        raise InventoryNotFound("product not found")
    product, balance = found
    if product.status != "ACTIVE":
        raise BillingError("archived products cannot be added to a bill")
    line = session.exec(select(BillLine).where(
        BillLine.bill_id == bill_id, BillLine.product_id == product_id,
        BillLine.merchant_id == merchant_id, BillLine.store_id == store_id,
    )).first()
    previous_quantity = line.quantity if line else Decimal("0")
    if not product.is_service and balance.available + previous_quantity < qty:
        raise InventoryConflict("insufficient available stock for this bill")
    if line is None:
        line = BillLine(
            merchant_id=merchant_id, store_id=store_id, bill_id=bill.id, product_id=product.id,
            product_name=product.name, sku=product.sku, unit=product.unit, quantity=qty,
            unit_price_paise=product.unit_price_paise,
            line_total_paise=_line_total(qty, product.unit_price_paise),
        )
    else:
        line.product_name, line.sku, line.unit = product.name, product.sku, product.unit
        line.quantity, line.unit_price_paise = qty, product.unit_price_paise
        line.line_total_paise = _line_total(qty, product.unit_price_paise)
    session.add(line)
    session.flush()
    _recalculate(session, bill)
    return bill, line


def remove_line(session: Session, *, merchant_id: str, store_id: str,
                bill_id: str, line_id: str) -> Bill:
    bill = _bill(session, merchant_id=merchant_id, store_id=store_id, bill_id=bill_id)
    if bill.state != "DRAFT":
        raise BillingError("only a draft bill can be edited")
    line = session.exec(select(BillLine).where(
        BillLine.id == line_id, BillLine.bill_id == bill_id,
        BillLine.merchant_id == merchant_id, BillLine.store_id == store_id,
    )).first()
    if line is None:
        raise InventoryNotFound("bill line not found")
    session.delete(line)
    session.flush()
    return _recalculate(session, bill)


def issue_bill(session: Session, *, merchant_id: str, store_id: str, bill_id: str) -> Bill:
    bill = _bill(session, merchant_id=merchant_id, store_id=store_id, bill_id=bill_id)
    if bill.state == "ISSUED":
        return bill
    if bill.state != "DRAFT":
        raise BillingError("cancelled bills cannot be issued")
    lines = session.exec(select(BillLine).where(
        BillLine.bill_id == bill.id, BillLine.merchant_id == merchant_id,
        BillLine.store_id == store_id,
    )).all()
    if not lines:
        raise BillingError("add at least one product before issuing a bill")
    for line in lines:
        found = lookup_product(session, merchant_id=merchant_id, store_id=store_id, product_id=line.product_id)
        if found is None:
            raise InventoryNotFound("a bill product is no longer available in this store")
        product, balance = found
        if not product.is_service and balance.available < line.quantity:
            raise InventoryConflict(f"insufficient available stock for {line.product_name}")
        # Price and label are re-read from the canonical catalogue at issue time.
        line.product_name, line.sku, line.unit = product.name, product.sku, product.unit
        line.unit_price_paise = product.unit_price_paise
        line.line_total_paise = _line_total(line.quantity, product.unit_price_paise)
        session.add(line)
        if not product.is_service:
            reserve_stock(
                session, merchant_id=merchant_id, store_id=store_id, product_id=product.id,
                quantity=line.quantity, reservation_id=f"counter:{bill.id}:{product.id}",
                source_ref=bill.id, source="counter_bill",
            )
    _recalculate(session, bill)
    bill.state = "ISSUED"
    bill.issued_at = datetime.now(timezone.utc)
    bill.revision += 1
    session.add(bill)
    session.flush()
    return bill


def cancel_draft(session: Session, *, merchant_id: str, store_id: str, bill_id: str) -> Bill:
    bill = _bill(session, merchant_id=merchant_id, store_id=store_id, bill_id=bill_id)
    if bill.state == "CANCELLED":
        return bill
    if bill.state == "ISSUED":
        if bill.payment_state in {"PAID", "PENDING"}:
            raise BillingError("a paid or unresolved bill cannot be cancelled")
        active = session.exec(select(Payment.id).where(
            Payment.merchant_id == merchant_id, Payment.store_id == store_id,
            Payment.source_type == "COUNTER_BILL", Payment.source_id == bill.id,
            Payment.status.in_(("INIT_UNKNOWN", "PENDING", "PENDING_RECONCILIATION")),
        )).first()
        if active:
            raise BillingError("a pending payment attempt must be reconciled before cancelling this bill")
        credit = session.exec(select(KhataLedgerEntry.id).where(
            KhataLedgerEntry.merchant_id == merchant_id, KhataLedgerEntry.store_id == store_id,
            KhataLedgerEntry.source_type == "counter_bill", KhataLedgerEntry.source_id == bill.id,
            KhataLedgerEntry.entry_type == "CREDIT_GIVEN",
        )).first()
        if credit:
            raise BillingError("a bill on Khata must be corrected through the ledger")
        lines = session.exec(select(BillLine).where(
            BillLine.bill_id == bill.id, BillLine.merchant_id == merchant_id,
            BillLine.store_id == store_id,
        )).all()
        for line in lines:
            reservation_id = f"counter:{bill.id}:{line.product_id}"
            reservation = session.exec(select(InventoryReservation).where(
                InventoryReservation.id == reservation_id,
                InventoryReservation.merchant_id == merchant_id,
                InventoryReservation.store_id == store_id,
            )).first()
            if reservation and reservation.state == "HELD":
                release_stock(session, merchant_id=merchant_id, store_id=store_id,
                              reservation_id=reservation_id, source="counter_bill_cancelled")
    elif bill.state != "DRAFT":
        raise BillingError("this bill cannot be cancelled from its current state")
    bill.state = "CANCELLED"
    bill.updated_at = datetime.now(timezone.utc)
    session.add(bill)
    session.flush()
    return bill
