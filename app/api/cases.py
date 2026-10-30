from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Case, EvidenceLog

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("")
def list_cases(session: Session = Depends(get_session)):
    return session.exec(select(Case).order_by(Case.id.desc())).all()


@router.get("/{case_id}")
def get_case(case_id: int, session: Session = Depends(get_session)):
    case = session.get(Case, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    evidence = session.exec(select(EvidenceLog).where(EvidenceLog.case_id == case_id)).all()
    return {"case": case, "evidence": evidence}
