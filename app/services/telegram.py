"""Owner channel: Telegram notifications and signed one-tap buttons."""
import logging
import httpx
from app.config import get_settings
from app.services.security import make_token

logger = logging.getLogger(__name__)


async def notify_owner(text: str, case_id: int | None = None) -> None:
    s = get_settings()
    if not (s.telegram_bot_token and s.telegram_owner_chat_id):
        logger.info(f"[Console Owner Alert] {text}")
        return

    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": s.telegram_owner_chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    if case_id:
        approve_token = make_token(case_id, "approve")
        skip_token = make_token(case_id, "skip")
        base = s.public_base_url
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve Link", "url": f"{base}/approvals/{approve_token}"},
                    {"text": "❌ Skip", "url": f"{base}/approvals/{skip_token}"},
                ]
            ]
        }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.warning(f"Telegram notification failed: {exc}")
