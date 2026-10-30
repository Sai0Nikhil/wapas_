"""Dev-only: create failures without Paytm. Also your sandbox fallback for the demo."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.services import intake

router = APIRouter(prefix="/dev", tags=["dev"])


class SimulateFailure(BaseModel):
    amount_inr: float = 2340
    customer_ref: str = "cust-rahul"
    bank: str = "HDFC"
    resp_msg: str = "Bank timeout"


@router.post("/simulate-failure")
def simulate_failure(body: SimulateFailure, session: Session = Depends(get_session)):
    if get_settings().app_env != "dev":
        raise HTTPException(404)
    case = intake.register_failure(
        session, order_id=f"SIM-{uuid.uuid4().hex[:8]}", txn_id=uuid.uuid4().hex[:10],
        amount_paise=round(body.amount_inr * 100), bank=body.bank,
        resp_msg=body.resp_msg, customer_ref=body.customer_ref,
    )
    return {"case_id": case.id}
