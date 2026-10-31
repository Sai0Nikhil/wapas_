"""Khata Voice-to-Ledger API endpoints powered by Sarvam AI."""
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.sarvam import parse_spoken_khata_entry

router = APIRouter(prefix="/khata", tags=["khata"])


class CustomerInfo(BaseModel):
    id: Optional[str] = None
    name: str
    phone: Optional[str] = None
    totalDue: Optional[float] = 0.0


class VoiceParseRequest(BaseModel):
    text: str
    existing_customers: Optional[List[CustomerInfo]] = None


class VoiceParseResponse(BaseModel):
    customer_name: str
    debit_amount: float
    credit_amount: float
    net_amount: float
    note: str
    matched_existing_customer: Optional[str] = None
    is_existing_match: bool = False
    match_confidence: float = 0.85
    clarification_prompt: Optional[str] = None


@router.post("/voice-parse", response_model=VoiceParseResponse)
async def parse_khata_voice(req: VoiceParseRequest):
    """Takes natural merchant speech or text, diagnoses debit/credit via Sarvam AI,
    and runs entity duplicate checks against existing khata accounts.
    """
    customers_dicts = [c.model_dump() for c in (req.existing_customers or [])]
    result = await parse_spoken_khata_entry(req.text, customers_dicts)
    return VoiceParseResponse(**result)
