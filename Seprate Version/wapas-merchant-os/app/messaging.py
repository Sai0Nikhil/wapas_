"""Outbound customer messages: render a fixed template, store it in the demo
inbox, and (optionally) hand it to n8n for real delivery."""
import logging

import httpx

from .config import get_settings
from .models import Message
from .templates import LANG_NAMES, render
from . import telegram

log = logging.getLogger("wapas.messaging")


def send(s, *, case_id: str, customer, template: str, amount_paise: int, link: str = "") -> Message:
    cfg = get_settings()
    text = render(template, customer.language, name=customer.name, amount_paise=amount_paise,
                  merchant=cfg.merchant_name, link=link)
    research = case_id.startswith("eval-")
    # Customer channel (never the owner's): the demo customer phone on Telegram if configured, else the console inbox.
    channel = "research-sim" if research else ("telegram-demo-customer" if cfg.telegram_customer_chat_id and cfg.telegram_bot_token
                                                else "console-inbox")
    msg = Message(case_id=case_id, customer_id=customer.id, language=customer.language, text=text, channel=channel)
    s.add(msg)
    if research:
        return msg  # simulated customers: nothing leaves the building
    telegram.customer_message(case_id, customer.name, LANG_NAMES.get(customer.language, customer.language), text)
    if cfg.n8n_webhook_url:
        try:
            httpx.post(cfg.n8n_webhook_url, timeout=5.0, json={
                "case_id": case_id, "customer": customer.name, "phone": customer.phone,
                "language": customer.language, "template": template, "text": text, "link": link})
        except Exception as e:  # noqa: BLE001  (delivery is best effort; the inbox is the record)
            log.warning("n8n delivery failed: %s", e)
    return msg
