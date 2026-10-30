"""Owner approval tokens.

A button in Telegram carries `ap:<case>:<expiry>:<sig>` (or `sk:` to skip). The
signature is an HMAC over the verb, the case, the expiry AND the id of the
decision the owner was shown. So a token:
  - cannot be forged without the server secret,
  - stops working when it expires,
  - stops working if Wapas re-decided the case after the message was sent,
  - does nothing on replay (the case is no longer waiting for the owner).
The text of a Telegram message is never treated as authorization.
"""
import base64
import hashlib
import hmac
import secrets
import time

from .config import get_settings

_RUN_SECRET = secrets.token_bytes(32)


def _secret() -> bytes:
    s = get_settings().approval_secret
    return s.encode() if s else _RUN_SECRET


def _b36(n: int) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = chars[r] + out
        if n == 0:
            return out


def _sig(verb: str, case_id: str, exp: str, decision_id: int) -> str:
    mac = hmac.new(_secret(), f"{verb}|{case_id}|{exp}|{decision_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac)[:12].decode()


def make(verb: str, case_id: str, decision_id: int, ttl_seconds: float | None = None, now: float | None = None) -> str:
    """Telegram callback_data (max 64 bytes)."""
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().approval_ttl_hours * 3600
    exp = _b36(int((now or time.time()) + ttl))
    data = f"{verb}:{case_id}:{exp}:{_sig(verb, case_id, exp, decision_id)}"
    if len(data.encode()) > 64:
        raise ValueError("approval token longer than Telegram's 64-byte callback_data limit")
    return data


def parse(data: str) -> tuple[str, str, str, str] | None:
    parts = (data or "").split(":")
    if len(parts) != 4 or parts[0] not in ("ap", "sk"):
        return None
    return parts[0], parts[1], parts[2], parts[3]


def check(data: str, decision_id: int | None, now: float | None = None) -> tuple[bool, str]:
    p = parse(data)
    if not p:
        return False, "malformed approval token"
    verb, case_id, exp, sig = p
    if decision_id is None:
        return False, "no decision on record for this case"
    if not hmac.compare_digest(sig, _sig(verb, case_id, exp, decision_id)):
        return False, "approval token is not valid for this case's current decision"
    try:
        if int(exp, 36) < (now or time.time()):
            return False, "approval token expired"
    except ValueError:
        return False, "malformed expiry"
    return True, "ok"
