"""Turn a failed payment event into a Case. Used by the webhook and the dev simulator."""
from sqlmodel import Session, select

from app.models import Case, Customer, EvidenceLog, Merchant, Payment


def register_failure(
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
        merchant_id=merchant.id, customer_id=customer.id, order_id=order_id, txn_id=txn_id,
        amount_paise=amount_paise, status="TXN_FAILURE", bank=bank, resp_code=resp_code, resp_msg=resp_msg,
    )
    session.add(payment)
    session.flush()

    case = Case(merchant_id=merchant.id, customer_id=customer.id, payment_id=payment.id)
    session.add(case)
    session.flush()
    session.add(EvidenceLog(case_id=case.id, kind="signal",
                            detail=f"Failed payment {order_id}: {amount_paise/100:.2f} INR, bank={bank}, msg={resp_msg}"))
    session.commit()
    session.refresh(case)
    return case
