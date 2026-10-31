import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.db import get_session
from app.models import WebhookEvent
from app.services import intake, paytm

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/paytm")
async def paytm_webhook(request: Request, session: Session = Depends(get_session)):
    ctype = request.headers.get("content-type", "")
    if "json" in ctype:
        data = await request.json()
    else:
        data = dict(await request.form())

    if not paytm.verify_callback_checksum(data):
        raise HTTPException(status_code=400, detail="bad checksum")

    order_id = str(data.get("ORDERID") or data.get("orderId") or "")
    txn_id = str(data.get("TXNID") or data.get("txnId") or "")
    status = str(data.get("STATUS") or data.get("status") or "")
    if not order_id:
        raise HTTPException(status_code=400, detail="missing order id")

    event_key = f"{order_id}:{txn_id}:{status}"
    if session.exec(select(WebhookEvent).where(WebhookEvent.event_key == event_key)).first():
        return {"result": "duplicate_ignored"}
    session.add(WebhookEvent(event_key=event_key, raw=json.dumps(data, default=str)))
    session.commit()

    if status == "TXN_FAILURE":
        amount_paise = int(Decimal(str(data.get("TXNAMOUNT") or "0")) * 100)
        case = await intake.register_failure(
            session, order_id=order_id, txn_id=txn_id, amount_paise=amount_paise,
            bank=str(data.get("BANKNAME") or ""), resp_code=str(data.get("RESPCODE") or ""),
            resp_msg=str(data.get("RESPMSG") or ""), customer_ref=str(data.get("CUSTID") or "unknown"),
        )
        return {"result": "case_created", "case_id": case.id}
    return {"result": "stored", "status": status}
