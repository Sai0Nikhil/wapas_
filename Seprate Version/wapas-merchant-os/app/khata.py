"""Append-only Khata ledger operations. Positive deltas increase customer debt."""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, update
from sqlmodel import Session, select

from .billing_models import Bill, BillLine
from .merchant_os_models import InventoryReservation
from . import inventory
from .khata_models import KhataAccount, KhataLedgerEntry, now
from .models import Customer


class KhataError(Exception):
    """Safe, user-facing Khata operation error."""


def _account(session: Session, *, merchant_id: str, store_id: str, account_id: str) -> KhataAccount:
    account = session.exec(select(KhataAccount).where(
        KhataAccount.id == account_id, KhataAccount.merchant_id == merchant_id,
        KhataAccount.store_id == store_id,
    )).first()
    if account is None:
        raise KhataError("Khata account not found")
    return account


def balance_paise(session: Session, *, merchant_id: str, store_id: str, account_id: str) -> int:
    value = session.exec(select(func.coalesce(func.sum(KhataLedgerEntry.delta_paise), 0)).where(
        KhataLedgerEntry.merchant_id == merchant_id, KhataLedgerEntry.store_id == store_id,
        KhataLedgerEntry.account_id == account_id,
    )).one()
    return int(value or 0)


def _assert_projection(session: Session, account: KhataAccount) -> int:
    ledger_balance = balance_paise(session, merchant_id=account.merchant_id,
                                   store_id=account.store_id, account_id=account.id)
    if account.balance_paise != ledger_balance:
        account.balance_paise = ledger_balance
        session.add(account)
        session.flush()
    return ledger_balance


def _customer_account(session: Session, *, merchant_id: str, store_id: str,
                      phone: str, name: str = "") -> KhataAccount:
    cleaned_phone = re.sub(r"\D", "", phone or "")
    if cleaned_phone.startswith("91") and len(cleaned_phone) == 12:
        cleaned_phone = cleaned_phone[2:]
    elif cleaned_phone.startswith("0") and len(cleaned_phone) == 11:
        cleaned_phone = cleaned_phone[1:]
    if not re.fullmatch(r"[6-9]\d{9}", cleaned_phone):
        if not cleaned_phone and name.strip():
            # Voice/quick input fallback: generate stable 10-digit mobile
            cleaned_phone = f"98{abs(hash(name.strip())) % 100000000:08d}"
        else:
            raise KhataError("A valid 10-digit customer phone is required for Khata")
    phone = cleaned_phone
    customer = session.exec(select(Customer).where(
        Customer.merchant_id == merchant_id, Customer.phone == phone,
    ).order_by(Customer.id)).first()
    if customer is None:
        customer = Customer(id="customer_" + uuid.uuid4().hex, merchant_id=merchant_id,
                            name=(name.strip() or phone), phone=phone)
        session.add(customer)
        session.flush()
    elif name.strip() and customer.name == customer.phone:
        customer.name = name.strip()
        session.add(customer)
        session.flush()
    account = session.exec(select(KhataAccount).where(
        KhataAccount.merchant_id == merchant_id, KhataAccount.store_id == store_id,
        KhataAccount.customer_id == customer.id,
    )).first()
    if account is None:
        account = KhataAccount(merchant_id=merchant_id, store_id=store_id, customer_id=customer.id)
        session.add(account)
        session.flush()
    return account


def add_bill_to_khata(session: Session, *, merchant_id: str, store_id: str, bill_id: str,
                      due_at: datetime | None = None, note: str = "") -> tuple[KhataAccount, KhataLedgerEntry]:
    bill = session.exec(select(Bill).where(
        Bill.id == bill_id, Bill.merchant_id == merchant_id, Bill.store_id == store_id,
    )).first()
    if bill is None:
        raise KhataError("Bill not found")
    if bill.state != "ISSUED":
        raise KhataError("Only an issued bill can be added to Khata")
    if bill.payment_state in {"PAID", "PENDING"}:
        raise KhataError("A paid or pending bill cannot be added to Khata")
    if bill.total_paise <= 0:
        raise KhataError("Bill total must be greater than zero")
    account = _customer_account(session, merchant_id=merchant_id, store_id=store_id,
                                phone=bill.customer_phone, name=bill.customer_name)
    idempotency_key = "khata:bill:" + bill.id
    existing = session.exec(select(KhataLedgerEntry).where(
        KhataLedgerEntry.merchant_id == merchant_id, KhataLedgerEntry.store_id == store_id,
        KhataLedgerEntry.idempotency_key == idempotency_key,
    )).first()
    if existing:
        if existing.account_id != account.id or existing.delta_paise != bill.total_paise:
            raise KhataError("This bill was already recorded with different Khata details")
        return account, existing
    _assert_projection(session, account)
    entry = KhataLedgerEntry(
        merchant_id=merchant_id, store_id=store_id, account_id=account.id,
        entry_type="CREDIT_GIVEN", delta_paise=bill.total_paise,
        source_type="counter_bill", source_id=bill.id, idempotency_key=idempotency_key,
        due_at=due_at, note=note.strip(), recording_basis="MERCHANT_SELECTED_CREDIT",
    )
    session.add(entry)
    session.flush()
    result = session.exec(update(KhataAccount).where(
        KhataAccount.id == account.id, KhataAccount.merchant_id == merchant_id,
        KhataAccount.store_id == store_id,
    ).values(balance_paise=KhataAccount.balance_paise + bill.total_paise))
    if result.rowcount != 1:
        raise KhataError("Khata account could not be updated")
    lines = session.exec(select(BillLine).where(
        BillLine.bill_id == bill.id, BillLine.merchant_id == merchant_id,
        BillLine.store_id == store_id,
    )).all()
    try:
        with session.begin_nested():
            for line in lines:
                found = inventory.lookup_product(session, merchant_id=merchant_id,
                                                 store_id=store_id, product_id=line.product_id)
                if found is None:
                    raise inventory.InventoryNotFound("Counter product is no longer available")
                if found[0].is_service:
                    continue
                reservation_id = f"counter:{bill.id}:{line.product_id}"
                reservation = session.exec(select(InventoryReservation).where(
                    InventoryReservation.id == reservation_id,
                    InventoryReservation.merchant_id == merchant_id,
                    InventoryReservation.store_id == store_id,
                )).first()
                if reservation and reservation.state == "HELD":
                    inventory.complete_reservation(session, merchant_id=merchant_id, store_id=store_id,
                                                   reservation_id=reservation_id)
                elif reservation and reservation.state == "CONSUMED":
                    continue
                else:
                    inventory.sell_stock(
                        session, merchant_id=merchant_id, store_id=store_id,
                        product_id=line.product_id, quantity=line.quantity, source_ref=bill.id,
                        source="counter_khata", idempotency_key=f"counter-khata-sale:{bill.id}:{line.id}",
                    )
    except inventory.InventoryError as exc:
        raise KhataError("The bill could not be added to Khata because its stock is no longer available") from exc
    return account, entry


def record_repayment(session: Session, *, merchant_id: str, store_id: str, account_id: str,
                     amount_paise: int, method: str, idempotency_key: str, note: str = "",
                     received: bool = False) -> tuple[KhataLedgerEntry, int]:
    if not received:
        raise KhataError("Confirm that you received this repayment before recording it")
    if amount_paise <= 0:
        raise KhataError("Repayment amount must be greater than zero")
    if method not in {"CASH", "OTHER"}:
        raise KhataError("Choose cash or another merchant-recorded collection method")
    if len(idempotency_key) < 8:
        raise KhataError("A unique repayment request key is required")
    account = _account(session, merchant_id=merchant_id, store_id=store_id, account_id=account_id)
    existing = session.exec(select(KhataLedgerEntry).where(
        KhataLedgerEntry.merchant_id == merchant_id, KhataLedgerEntry.store_id == store_id,
        KhataLedgerEntry.idempotency_key == idempotency_key,
    )).first()
    if existing:
        if (existing.account_id != account.id or existing.entry_type != "REPAYMENT"
                or existing.delta_paise != -amount_paise or existing.payment_method != method):
            raise KhataError("This repayment key was already used for a different operation")
        return existing, balance_paise(session, merchant_id=merchant_id, store_id=store_id,
                                       account_id=account.id)
    balance = _assert_projection(session, account)
    if amount_paise > balance:
        raise KhataError("Repayment cannot exceed the current outstanding balance")
    # A conditional UPDATE serializes competing collections on the account row.
    changed = session.exec(update(KhataAccount).where(
        KhataAccount.id == account.id, KhataAccount.merchant_id == merchant_id,
        KhataAccount.store_id == store_id, KhataAccount.balance_paise >= amount_paise,
    ).values(balance_paise=KhataAccount.balance_paise - amount_paise))
    if changed.rowcount != 1:
        raise KhataError("Repayment exceeds the latest outstanding balance; refresh and try again")
    entry = KhataLedgerEntry(
        merchant_id=merchant_id, store_id=store_id, account_id=account.id,
        entry_type="REPAYMENT", delta_paise=-amount_paise, source_type="merchant_recorded_collection",
        source_id=uuid.uuid4().hex, idempotency_key=idempotency_key,
        payment_method=method, note=note.strip(), recording_basis="MERCHANT_CONFIRMED_RECEIPT",
    )
    session.add(entry)
    session.flush()
    return entry, balance - amount_paise


def record_verified_paytm_repayment(session: Session, *, merchant_id: str, store_id: str,
                                    account_id: str, amount_paise: int, payment_id: str,
                                    note: str = "") -> tuple[KhataLedgerEntry, int]:
    """Reduce debt only for a payment already verified against its stored Paytm attempt."""
    if amount_paise <= 0 or not payment_id:
        raise KhataError("Verified collection needs a positive amount and payment reference")
    account = _account(session, merchant_id=merchant_id, store_id=store_id, account_id=account_id)
    key = "paytm-payment:" + payment_id
    existing = session.exec(select(KhataLedgerEntry).where(
        KhataLedgerEntry.merchant_id == merchant_id, KhataLedgerEntry.store_id == store_id,
        KhataLedgerEntry.idempotency_key == key,
    )).first()
    if existing:
        if (existing.account_id != account.id or existing.entry_type != "REPAYMENT"
                or existing.delta_paise != -amount_paise or existing.recording_basis != "PAYTM_VERIFIED"):
            raise KhataError("This Paytm payment was already applied to a different collection")
        return existing, balance_paise(session, merchant_id=merchant_id, store_id=store_id,
                                       account_id=account.id)
    balance = _assert_projection(session, account)
    if amount_paise > balance:
        raise KhataError("Verified payment exceeds the latest Khata balance; owner reconciliation is required")
    changed = session.exec(update(KhataAccount).where(
        KhataAccount.id == account.id, KhataAccount.merchant_id == merchant_id,
        KhataAccount.store_id == store_id, KhataAccount.balance_paise >= amount_paise,
    ).values(balance_paise=KhataAccount.balance_paise - amount_paise))
    if changed.rowcount != 1:
        raise KhataError("Khata balance changed during Paytm settlement; owner reconciliation is required")
    entry = KhataLedgerEntry(
        merchant_id=merchant_id, store_id=store_id, account_id=account.id,
        entry_type="REPAYMENT", delta_paise=-amount_paise, source_type="paytm_verified_collection",
        source_id=payment_id, idempotency_key=key, payment_method="PAYTM",
        note=note.strip(), recording_basis="PAYTM_VERIFIED",
    )
    session.add(entry)
    session.flush()
    return entry, balance - amount_paise


def reverse_entry(session: Session, *, merchant_id: str, store_id: str, entry_id: str,
                  reason: str) -> tuple[KhataLedgerEntry, int]:
    original = session.exec(select(KhataLedgerEntry).where(
        KhataLedgerEntry.id == entry_id, KhataLedgerEntry.merchant_id == merchant_id,
        KhataLedgerEntry.store_id == store_id,
    )).first()
    if original is None:
        raise KhataError("Khata entry not found")
    if original.entry_type == "REVERSAL":
        raise KhataError("A reversal cannot itself be reversed")
    prior = session.exec(select(KhataLedgerEntry).where(
        KhataLedgerEntry.reverses_entry_id == original.id,
        KhataLedgerEntry.merchant_id == merchant_id, KhataLedgerEntry.store_id == store_id,
    )).first()
    if prior:
        return prior, balance_paise(session, merchant_id=merchant_id, store_id=store_id,
                                    account_id=original.account_id)
    balance = balance_paise(session, merchant_id=merchant_id, store_id=store_id,
                            account_id=original.account_id)
    account = _account(session, merchant_id=merchant_id, store_id=store_id, account_id=original.account_id)
    balance = _assert_projection(session, account)
    new_balance = balance - original.delta_paise
    if new_balance < 0:
        raise KhataError("Reversal would create a negative outstanding balance")
    changed = session.exec(update(KhataAccount).where(
        KhataAccount.id == account.id, KhataAccount.merchant_id == merchant_id,
        KhataAccount.store_id == store_id,
        KhataAccount.balance_paise >= (original.delta_paise if original.delta_paise > 0 else 0),
    ).values(balance_paise=KhataAccount.balance_paise - original.delta_paise))
    if changed.rowcount != 1:
        raise KhataError("Khata balance changed; refresh and retry the correction")
    reversal = KhataLedgerEntry(
        merchant_id=merchant_id, store_id=store_id, account_id=original.account_id,
        entry_type="REVERSAL", delta_paise=-original.delta_paise, source_type="reversal",
        source_id=original.id, idempotency_key="khata:reverse:" + original.id,
        reverses_entry_id=original.id, note=reason.strip(), recording_basis="MERCHANT_CONFIRMED_CORRECTION",
    )
    session.add(reversal)
    session.flush()
    return reversal, new_balance


def list_accounts(session: Session, *, merchant_id: str, store_id: str, limit: int = 100) -> list[dict]:
    accounts = session.exec(select(KhataAccount).where(
        KhataAccount.merchant_id == merchant_id, KhataAccount.store_id == store_id,
        KhataAccount.status == "ACTIVE",
    ).order_by(KhataAccount.created_at.desc()).limit(limit)).all()
    result = []
    for account in accounts:
        customer = session.get(Customer, account.customer_id)
        if customer is None:
            customer = session.exec(select(Customer).where(Customer.merchant_id == merchant_id, Customer.id == account.customer_id)).first()
        
        if customer:
            name = customer.name
            phone = customer.phone
        else:
            clean_name = account.customer_id.replace("cust_", "").replace("cast_", "").replace("cu", "").replace("_", " ").title()
            name = f"Customer {clean_name}"
            phone = ""

        cur_balance = balance_paise(session, merchant_id=merchant_id, store_id=store_id, account_id=account.id)
        result.append({
            "id": account.id, "customer_id": account.customer_id,
            "name": name,
            "phone": phone,
            "outstanding_paise": cur_balance,
            "reminder_consent": account.reminder_consent,
            "created_at": account.created_at,
        })
    return result


def account_history(session: Session, *, merchant_id: str, store_id: str,
                    account_id: str) -> tuple[KhataAccount, Customer, list[KhataLedgerEntry], int]:
    account = _account(session, merchant_id=merchant_id, store_id=store_id, account_id=account_id)
    customer = session.get(Customer, account.customer_id)
    if customer is None or customer.merchant_id != merchant_id:
        customer = session.exec(select(Customer).where(Customer.merchant_id == merchant_id, Customer.id == account.customer_id)).first()
    if customer is None:
        customer = Customer(id=account.customer_id, merchant_id=merchant_id, name="Customer", phone="")
        session.add(customer)
        session.flush()
    entries = session.exec(select(KhataLedgerEntry).where(
        KhataLedgerEntry.account_id == account.id, KhataLedgerEntry.merchant_id == merchant_id,
        KhataLedgerEntry.store_id == store_id,
    ).order_by(KhataLedgerEntry.created_at, KhataLedgerEntry.id)).all()
    return account, customer, list(entries), balance_paise(session, merchant_id=merchant_id,
                                                            store_id=store_id, account_id=account.id)


def add_manual_entry(
    session: Session,
    *,
    merchant_id: str,
    store_id: str,
    account_id: str | None = None,
    customer_phone: str | None = None,
    customer_name: str | None = None,
    entry_type: str,  # "CREDIT_GIVEN" (Udhaar) or "REPAYMENT" (Jama)
    amount_paise: int,
    note: str = "",
    payment_method: str = "CASH",
    idempotency_key: str | None = None,
) -> tuple[KhataAccount, KhataLedgerEntry, int]:
    """Manually add an Udhaar (credit given) or Jama (repayment) ledger entry."""
    if amount_paise <= 0:
        raise KhataError("Amount must be greater than zero")

    if account_id:
        account = _account(session, merchant_id=merchant_id, store_id=store_id, account_id=account_id)
        if customer_name and customer_name.strip():
            cust = session.get(Customer, account.customer_id)
            if cust and cust.name in (cust.phone, "Customer", ""):
                cust.name = customer_name.strip()
                session.add(cust)
                session.flush()
    elif customer_phone or customer_name:
        account = _customer_account(session, merchant_id=merchant_id, store_id=store_id,
                                    phone=customer_phone or "", name=customer_name or "")
    else:
        raise KhataError("Either account_id, customer_phone, or customer_name is required")

    key = idempotency_key or f"khata:manual:{uuid.uuid4().hex}"
    existing = session.exec(select(KhataLedgerEntry).where(
        KhataLedgerEntry.merchant_id == merchant_id,
        KhataLedgerEntry.store_id == store_id,
        KhataLedgerEntry.idempotency_key == key,
    )).first()
    if existing:
        return account, existing, balance_paise(session, merchant_id=merchant_id, store_id=store_id, account_id=account.id)

    balance = _assert_projection(session, account)
    norm_type = entry_type.upper()

    if norm_type in ("CREDIT_GIVEN", "DEBIT", "UDHAAR"):
        new_balance = balance + amount_paise
        account.balance_paise = new_balance
        session.add(account)
        entry = KhataLedgerEntry(
            merchant_id=merchant_id,
            store_id=store_id,
            account_id=account.id,
            entry_type="CREDIT_GIVEN",
            delta_paise=amount_paise,
            source_type="manual_credit",
            source_id="manual_" + uuid.uuid4().hex[:8],
            idempotency_key=key,
            payment_method=payment_method or "MANUAL",
            note=note.strip() or "Manual Udhaar Credit",
            recording_basis="MERCHANT_SELECTED_CREDIT",
        )
        session.add(entry)
        session.flush()
        return account, entry, new_balance

    elif norm_type in ("REPAYMENT", "CREDIT", "JAMA"):
        new_balance = max(0, balance - amount_paise)
        account.balance_paise = new_balance
        session.add(account)
        entry = KhataLedgerEntry(
            merchant_id=merchant_id,
            store_id=store_id,
            account_id=account.id,
            entry_type="REPAYMENT",
            delta_paise=-amount_paise,
            source_type="manual_repayment",
            source_id="manual_" + uuid.uuid4().hex[:8],
            idempotency_key=key,
            payment_method=payment_method or "CASH",
            note=note.strip() or "Manual Khata Repayment",
            recording_basis="MERCHANT_CONFIRMED_RECEIPT",
        )
        session.add(entry)
        session.flush()
        return account, entry, new_balance
    else:
        raise KhataError(f"Unsupported entry_type: {entry_type}. Must be CREDIT_GIVEN or REPAYMENT.")


def calculate_aging(session: Session, *, merchant_id: str, store_id: str) -> dict:
    """Calculate debt aging across 0-30, 31-60, 61-90, and 90+ day brackets."""
    accounts = session.exec(select(KhataAccount).where(
        KhataAccount.merchant_id == merchant_id, KhataAccount.store_id == store_id,
        KhataAccount.status == "ACTIVE", KhataAccount.balance_paise > 0,
    ).order_by(KhataAccount.balance_paise.desc())).all()

    now_utc = datetime.now(timezone.utc)
    summary = {
        "total_outstanding_paise": 0,
        "current_paise": 0,
        "days_31_60_paise": 0,
        "days_61_90_paise": 0,
        "days_over_90_paise": 0,
        "account_count": len(accounts),
        "accounts": [],
    }

    for account in accounts:
        customer = session.get(Customer, account.customer_id)
        bal = account.balance_paise
        summary["total_outstanding_paise"] += bal

        entries = session.exec(select(KhataLedgerEntry).where(
            KhataLedgerEntry.account_id == account.id,
            KhataLedgerEntry.merchant_id == merchant_id,
            KhataLedgerEntry.store_id == store_id,
        ).order_by(KhataLedgerEntry.created_at.asc())).all()

        oldest_unpaid_age_days = 0
        rem = bal
        for e in reversed(entries):
            if e.delta_paise > 0:
                created = e.created_at.replace(tzinfo=timezone.utc) if e.created_at.tzinfo is None else e.created_at
                age_days = max(0, (now_utc - created).days)
                oldest_unpaid_age_days = max(oldest_unpaid_age_days, age_days)
                rem -= e.delta_paise
                if rem <= 0:
                    break

        if oldest_unpaid_age_days <= 30:
            summary["current_paise"] += bal
            bracket = "0-30"
        elif oldest_unpaid_age_days <= 60:
            summary["days_31_60_paise"] += bal
            bracket = "31-60"
        elif oldest_unpaid_age_days <= 90:
            summary["days_61_90_paise"] += bal
            bracket = "61-90"
        else:
            summary["days_over_90_paise"] += bal
            bracket = "90+"

        summary["accounts"].append({
            "account_id": account.id,
            "customer_id": account.customer_id,
            "name": customer.name if customer else "Customer",
            "phone": customer.phone if customer else "",
            "balance_paise": bal,
            "balance_fmt": f"{bal // 100:,}.{bal % 100:02d}",
            "oldest_debt_days": oldest_unpaid_age_days,
            "aging_bracket": bracket,
            "reminder_consent": account.reminder_consent,
        })

    return summary
