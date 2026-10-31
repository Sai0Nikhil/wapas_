from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.models import Case, CaseStatus, EvidenceLog
from app.services.security import make_token, verify_token

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/token/{case_id}/{decision}")
def issue_token(case_id: int, decision: str):
    """Dev helper. In production the token is embedded in the Telegram button."""
    return {"token": make_token(case_id, decision)}


@router.post("/{token}")
async def decide(token: str, session: Session = Depends(get_session)):
    parsed = verify_token(token)
    if not parsed:
        raise HTTPException(400, "invalid or expired token")
    case_id, decision = parsed
    case = session.get(Case, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    if case.status != CaseStatus.AWAITING_OWNER:
        return {"result": "already_handled", "status": case.status}
    case.status = CaseStatus.PLANNED if decision == "approve" else CaseStatus.BLOCKED
    case.updated_at = datetime.now(timezone.utc)
    session.add(case)
    session.add(EvidenceLog(case_id=case.id, kind="policy", detail=f"owner decision: {decision}"))
    session.commit()
    if decision == "approve":
        from app.services import executor
        await executor.execute_recovery_action(session, case.id, channel="telegram")
    return {"result": decision, "case_id": case.id}
