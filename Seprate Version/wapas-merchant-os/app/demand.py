"""Small evidence service for storefront search outcomes; never estimates revenue."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlmodel import select

from .demand_models import DemandEvent


def normalize_query(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())[:100]


def record_outcome(session, *, merchant_id: str, store_id: str, query: str,
                   outcome: str, event_key: str) -> DemandEvent | None:
    normalized = normalize_query(query)
    if len(normalized) < 2 or outcome not in {"NO_MATCH", "OUT_OF_STOCK"}:
        return None
    prior = session.exec(select(DemandEvent).where(
        DemandEvent.merchant_id == merchant_id, DemandEvent.store_id == store_id,
        DemandEvent.event_key == event_key,
    )).first()
    if prior:
        return prior
    event = DemandEvent(merchant_id=merchant_id, store_id=store_id, query_text=normalized,
                        outcome=outcome, event_key=event_key)
    session.add(event)
    session.flush()
    return event


def business_metrics(session, *, merchant_id: str, store_id: str, days: int = 30,
                     now: datetime | None = None, since: datetime | None = None) -> dict:
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    if now is None:
        now = datetime.now(timezone.utc)
    if since is None:
        since = now - timedelta(days=days)

    from . import inventory
    from .billing_models import Bill
    from .commerce_models import StoreOrder
    from .khata_models import KhataAccount
    from .models import Payment

    # 1. Low stock summary: products at or below threshold
    try:
        products_and_balances = inventory.list_products(session, merchant_id=merchant_id, store_id=store_id, active_only=True)
        low_stock_count = sum(1 for p, b in products_and_balances if b.available <= p.low_stock_threshold)
    except Exception:
        low_stock_count = 0

    # 2. Sales summary: verified Paytm payments within window
    paytm_payments = session.exec(select(Payment).where(
        Payment.merchant_id == merchant_id,
        Payment.store_id == store_id,
        Payment.provider == "paytm",
        Payment.status == "SUCCESS",
        Payment.verified_at.is_not(None),
        Payment.verified_at >= since,
    )).all()
    sales_count = len(paytm_payments)
    sales_total_paise = sum(p.amount_paise for p in paytm_payments)

    # 3. Khata summary: total outstanding Khata balance and customer count
    accounts = session.exec(select(KhataAccount).where(
        KhataAccount.merchant_id == merchant_id,
        KhataAccount.store_id == store_id,
        KhataAccount.status == "ACTIVE",
    )).all()
    khata_customers_with_balance = [acc for acc in accounts if acc.balance_paise > 0]
    khata_outstanding_paise = sum(acc.balance_paise for acc in khata_customers_with_balance)
    khata_customer_count = len(khata_customers_with_balance)

    # 4. Pending fulfillment summary: paid orders awaiting fulfillment
    pending_orders = session.exec(select(StoreOrder).where(
        StoreOrder.merchant_id == merchant_id,
        StoreOrder.store_id == store_id,
        StoreOrder.status == "PAID",
        StoreOrder.fulfillment_state == "UNFULFILLED",
    )).all()
    pending_fulfillment_count = len(pending_orders)
    pending_fulfillment_paise = sum(o.amount_paise for o in pending_orders)

    # 5. Financial breakdown: gross bills, verified collected, outstanding credit, pending
    bills = session.exec(select(Bill).where(
        Bill.merchant_id == merchant_id,
        Bill.store_id == store_id,
        Bill.state == "ISSUED",
        Bill.issued_at.is_not(None),
        Bill.issued_at >= since,
    )).all()
    gross_bill_count = len(bills)
    gross_bill_total_paise = sum(b.total_paise for b in bills)

    pending_payments = session.exec(select(Payment).where(
        Payment.merchant_id == merchant_id,
        Payment.store_id == store_id,
        Payment.status.in_(["PENDING", "PENDING_RECONCILIATION"]),
        Payment.created_at >= since,
    )).all()
    pending_payment_count = len(pending_payments)
    pending_payment_paise = sum(p.amount_paise for p in pending_payments)

    return {
        "low_stock_summary": {
            "low_stock_count": low_stock_count,
            "provenance": "saved inventory balances and thresholds",
        },
        "sales_summary": {
            "verified_payment_count": sales_count,
            "verified_total_paise": sales_total_paise,
            "window_days": days,
            "provenance": "persisted server-verified Paytm payments",
        },
        "khata_summary": {
            "customer_count": khata_customer_count,
            "outstanding_total_paise": khata_outstanding_paise,
            "provenance": "append-only Khata ledger accounts",
        },
        "pending_fulfillment_summary": {
            "pending_count": pending_fulfillment_count,
            "pending_total_paise": pending_fulfillment_paise,
            "provenance": "paid storefront orders with unfulfilled status",
        },
        "financial_breakdown": {
            "gross_bill_issued_total_paise": gross_bill_total_paise,
            "gross_bill_issued_count": gross_bill_count,
            "verified_collected_total_paise": sales_total_paise,
            "verified_collected_count": sales_count,
            "outstanding_credit_total_paise": khata_outstanding_paise,
            "outstanding_credit_customer_count": khata_customer_count,
            "pending_payment_total_paise": pending_payment_paise,
            "pending_payment_count": pending_payment_count,
            "window_days": days,
            "provenance": "factual persisted store records without synthetic estimates or projected uplift",
        },
    }


def opportunity_pulse(session, *, merchant_id: str, store_id: str, days: int = 30) -> dict:
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    counts = session.exec(select(
        DemandEvent.query_text, DemandEvent.outcome,
        func.count(DemandEvent.id), func.min(DemandEvent.created_at), func.max(DemandEvent.created_at),
    ).where(
        DemandEvent.merchant_id == merchant_id, DemandEvent.store_id == store_id,
        DemandEvent.created_at >= since,
    ).group_by(DemandEvent.query_text, DemandEvent.outcome)
      .order_by(func.count(DemandEvent.id).desc(), DemandEvent.query_text).limit(50)).all()
    insights = []
    for query, outcome, count, first_seen, last_seen in counts:
        # One-off searches are too weak to call an opportunity.
        if count < 2:
            continue
        insights.append({
            "query": query,
            "outcome": outcome,
            "sample_count": int(count),
            "window_days": days,
            "first_seen": first_seen.isoformat() if first_seen else None,
            "last_seen": last_seen.isoformat() if last_seen else None,
            "provenance": "persisted public storefront search outcomes",
            "uncertainty": "Searches indicate interest, not a purchase or guaranteed demand.",
            "suggested_next_action": (
                "Review availability and record a restock only if the merchant confirms it."
                if outcome == "OUT_OF_STOCK" else
                "Review whether this product belongs in the catalogue; no product was added automatically."
            ),
        })
        if len(insights) >= 10:
            break
    metrics = business_metrics(session, merchant_id=merchant_id, store_id=store_id, days=days, now=now, since=since)
    return {
        "status": "AVAILABLE" if insights else "INSUFFICIENT_DATA",
        "message": "Recorded repeat search outcomes are shown below." if insights else "Not enough data yet.",
        "window_days": days,
        "as_of": now.isoformat(),
        "insights": insights,
        **metrics,
    }
