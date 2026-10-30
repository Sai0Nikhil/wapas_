"""Keep secrets out of logs, the console, evidence and error messages."""
import logging
import re

from .config import get_settings

_BOT = re.compile(r"bot\d{5,}:[A-Za-z0-9_-]{20,}")
_QS_TOKEN = re.compile(r"([?&]token=)[^&\s\"']+")
_KEYS = ("CHECKSUMHASH", "signature", "api-subscription-key", "Authorization", "token", "txnToken",
         "paytm_merchant_key", "merchant_key", "api_key")


def _secrets() -> list[str]:
    c = get_settings()
    vals = [c.paytm_merchant_key, c.llm_api_key, c.sarvam_api_key, c.telegram_bot_token, c.admin_token,
            c.approval_secret]
    return [v for v in vals if v and len(v) >= 6]


def redact(text) -> str:
    t = str(text)
    t = _BOT.sub("bot<redacted>", t)
    t = _QS_TOKEN.sub(r"\1<redacted>", t)
    for v in _secrets():
        t = t.replace(v, "<redacted>")
    return t


def redact_obj(o):
    if isinstance(o, dict):
        return {k: ("<redacted>" if any(k.lower() == x.lower() for x in _KEYS) else redact_obj(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact_obj(v) for v in o]
    if isinstance(o, str):
        return redact(o)
    return o


class RedactingFilter(logging.Filter):
    """Redacts the message and each argument in place (keeps the arg structure that
    formatters such as uvicorn's access formatter unpack)."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: (redact(v) if isinstance(v, str) else v) for k, v in record.args.items()}
            if record.exc_info and record.exc_info[1] is not None:
                record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
                record.exc_info = None
        except Exception:  # noqa: BLE001  (a log line must never crash the app)
            pass
        return True


def install_logging_redaction() -> None:
    """httpx logs full request URLs at INFO, and Telegram puts the bot token in the URL."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    f = RedactingFilter()
    loggers = [logging.getLogger()] + [l for l in logging.root.manager.loggerDict.values() if isinstance(l, logging.Logger)]
    for lg in loggers:  # includes uvicorn.access, which would otherwise print /?token=<ADMIN_TOKEN>
        for h in lg.handlers:
            if not any(isinstance(x, RedactingFilter) for x in h.filters):
                h.addFilter(f)
