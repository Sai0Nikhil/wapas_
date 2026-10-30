"""Sarvam client. TODO (hours 2-4): strict-JSON diagnosis + Hindi/Telugu message drafting."""
from app.config import get_settings


async def diagnose(case_context: dict) -> dict:
    """Return {cause, confidence, action, language}. Add one retry + deterministic fallback."""
    raise NotImplementedError
