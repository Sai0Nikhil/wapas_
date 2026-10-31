"""Turn a failed payment event into an analyzed, policy-governed Case."""
from sqlmodel import Session, select

from app.models import Case, CaseStatus, Customer, EvidenceLog, Merchant, Payment
from app.services import policy, sarvam


async def register_failure(
    session: Session,
    *,
    order_id: str,
    txn_id: str,
    amount_paise: int,
    bank: str = "",
    resp_code: str = "",
    resp_msg: str = "",
    customer_ref: str = "unknown",
    merchant_id: int | None = None,
) -> Case:
    merchant = session.get(Merchant, merchant_id) if merchant_id else session.exec(select(Merchant)).first()
    if merchant is None:
        raise RuntimeError("No merchant found. Run: python -m scripts.seed")

    customer = session.exec(
        select(Customer).where(Customer.merchant_id == merchant.id, Customer.external_ref == customer_ref)
    ).first()
    if customer is None:
        customer = Customer(merchant_id=merchant.id, external_ref=customer_ref)
        session.add(customer)
        session.flush()

    payment = Payment(
        merchant_id=merchant.id,
        customer_id=customer.id,
        order_id=order_id,
        txn_id=txn_id,
        amount_paise=amount_paise,
        status="TXN_FAILURE",
        bank=bank,
        resp_code=resp_code,
        resp_msg=resp_msg,
    )
    session.add(payment)
    session.flush()

    case = Case(merchant_id=merchant.id, customer_id=customer.id, payment_id=payment.id)
    session.add(case)
    session.flush()

    session.add(
        EvidenceLog(
            case_id=case.id,
            kind="signal",
            detail=f"Payment failure received: order={order_id}, amount=₹{amount_paise/100:.2f}, bank={bank}, reason={resp_msg}",
        )
    )

    # 1. AI Proposes (Sarvam Diagnosis)
    diag = await sarvam.diagnose({
        "bank": bank,
        "resp_msg": resp_msg,
        "amount_inr": amount_paise / 100,
        "language": customer.language,
        "customer_name": customer.name or customer_ref,
    })

    case.cause = diag.get("cause", "")
    case.confidence = diag.get("confidence", 0.8)
    case.planned_action = diag.get("action", "")
    case.language = diag.get("language", customer.language)

    session.add(
        EvidenceLog(
            case_id=case.id,
            kind="diagnosis",
            detail=f"Sarvam AI diagnosis: cause='{case.cause}', confidence={case.confidence:.2f}, lang={case.language}",
        )
    )

    # 2. Policy Authorizes (Deterministic Fail-Closed Engine)
    p_input = policy.PolicyInput(
        amount_paise=amount_paise,
        confidence=case.confidence,
        opted_out=customer.opted_out,
        reminder_count=case.reminder_count,
        loyal_high_value=(customer.lifetime_value_paise > 100_000),
    )
    decision = policy.evaluate(p_input)
    case.verdict = decision.verdict
    case.verdict_reason = decision.reason

    session.add(
        EvidenceLog(
            case_id=case.id,
            kind="policy",
            detail=f"Policy decision: {decision.verdict} (reason: {decision.reason})",
        )
    )

    if decision.verdict == policy.Verdict.ALLOW:
        case.status = CaseStatus.PLANNED
    elif decision.verdict == policy.Verdict.ASK_OWNER:
        case.status = CaseStatus.AWAITING_OWNER
    else:
        case.status = CaseStatus.BLOCKED

    session.add(case)
    session.commit()
    session.refresh(case)
    return case
