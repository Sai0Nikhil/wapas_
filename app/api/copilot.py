"""Sarkar AI Copilot endpoints powered by Sarvam-105B."""
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.sarvam import chat_with_copilot

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotChatRequest(BaseModel):
    message: str
    language: Optional[str] = "en"
    store_context: Optional[dict] = None


class CopilotChatResponse(BaseModel):
    reply: str
    headline_stat: Optional[str] = None
    suggestions: List[str] = []
    source: str = "Sarvam-105B AI"


@router.post("/chat", response_model=CopilotChatResponse)
async def copilot_chat(req: CopilotChatRequest):
    """Answers Kirana retail questions in merchant's selected language using Sarvam-105B."""
    result = await chat_with_copilot(req.message, req.language or "en", req.store_context)
    return CopilotChatResponse(**result)
