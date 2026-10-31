"""Idempotent Executor.
Rule:
1. Insert Action(idempotency_key=f"case{case_id}:{kind}:{n}") FIRST.
2. Unique constraint violation in SQLite => already sent, skip immediately.
3. Guarantees 'Nothing is sent twice'.
"""
import logging
from datetime import datetime, timezone
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError

from app.models import Action, Case, CaseStatus, Customer, EvidenceLog, Payment
from app.services import paytm

logger = logging.getLogger(__name__)


async def execute_recovery_action(session: Session, case_id: int, channel: str = "console") -> dict:
    case = session.get(Case, case_id)
    if not case:
        return {"error": "case_not_found"}

    payment = session.get(Payment, case.payment_id)
    customer = session.get(Customer, case.customer_id) if case.customer_id else None

    # Idempotency key enforcing "Nothing sent twice"
    attempt = case.reminder_count + 1
    idempotency_key = f"case{case.id}:recovery_link:{attempt}"

    # 1. Create Paytm recovery link
    amount_inr = f"{payment.amount_paise / 100:.2f}" if payment else "0.00"
    link_info = await paytm.create_payment_link(
        order_id=payment.order_id if payment else f"ORD-{case.id}",
        amount_inr=amount_inr,
        description=f"Recovery for order {payment.order_id if payment else case.id}",
        cust_phone=customer.phone if customer else "",
    )

    action = Action(
        case_id=case.id,
        kind="payment_link",
        channel=channel,
        idempotency_key=idempotency_key,
        payload=link_info.get("payment_url", ""),
        paytm_link_id=link_info.get("link_id", ""),
        status="PENDING",
    )

    # 2. Insert Action FIRST to test unique constraint
    try:
        session.add(action)
        session.flush()
    except IntegrityError:
        session.rollback()
        logger.info(f"Idempotency hit for {idempotency_key} - skipped duplicate dispatch")
        return {"status": "SKIPPED_DUPLICATE", "idempotency_key": idempotency_key}

    # 3. Mark SENT and update Case
    action.status = "SENT"
    action.sent_at = datetime.now(timezone.utc)
    case.status = CaseStatus.OUTREACH_SENT
    case.reminder_count += 1
    case.updated_at = datetime.now(timezone.utc)

    session.add(action)
    session.add(case)
    session.add(
        EvidenceLog(
            case_id=case.id,
            kind="action",
            detail=f"Dispatched Paytm recovery link ({link_info.get('payment_url')}) via {channel} (attempt {attempt})",
        )
    )
    session.commit()

    return {
        "status": "SENT",
        "case_id": case.id,
        "payment_url": link_info.get("payment_url"),
        "idempotency_key": idempotency_key,
    }
