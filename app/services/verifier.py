"""Paytm Verifier.
Rule:
Case is marked RECOVERED *only* upon positive Paytm transaction status check.
The AI agent can never directly set RECOVERED.
"""
from datetime import datetime, timezone
import logging
from sqlmodel import Session

from app.models import Case, CaseStatus, EvidenceLog, Payment
from app.services import paytm

logger = logging.getLogger(__name__)


async def verify_recovery_status(session: Session, case_id: int) -> dict:
    case = session.get(Case, case_id)
    if not case:
        return {"error": "case_not_found"}

    payment = session.get(Payment, case.payment_id)
    if not payment:
        return {"error": "payment_not_found"}

    # Call Paytm Transaction Status API
    status_resp = await paytm.transaction_status(payment.order_id)
    body = status_resp.get("body", {})
    result_info = body.get("resultInfo", {})
    txn_status = body.get("status") or result_info.get("resultStatus")

    if txn_status == "TXN_SUCCESS":
        case.status = CaseStatus.RECOVERED
        case.updated_at = datetime.now(timezone.utc)
        session.add(case)
        session.add(
            EvidenceLog(
                case_id=case.id,
                kind="verification",
                detail=f"Paytm status check verified TXN_SUCCESS for order {payment.order_id}. Case marked RECOVERED.",
            )
        )
        session.commit()
        return {"result": "RECOVERED", "order_id": payment.order_id, "amount_paise": payment.amount_paise}

    return {"result": "PENDING_OR_UNPAID", "paytm_status": txn_status, "order_id": payment.order_id}
