from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    s = get_settings()
    return {
        "ok": True,
        "env": s.app_env,
        "configured": {
            "paytm": bool(s.paytm_mid and s.paytm_merchant_key),
            "sarvam": bool(s.sarvam_api_key),
            "telegram": bool(s.telegram_bot_token and s.telegram_owner_chat_id),
        },
    }
