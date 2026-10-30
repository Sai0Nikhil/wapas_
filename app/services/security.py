"""Signed, expiring tokens for one-tap owner approvals."""
import hashlib
import hmac
import time

from app.config import get_settings


def _sig(msg: str) -> str:
    key = get_settings().approval_signing_secret.encode()
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()[:32]


def make_token(case_id: int, decision: str, ttl_s: int = 3600) -> str:
    exp = int(time.time()) + ttl_s
    msg = f"{case_id}.{decision}.{exp}"
    return f"{msg}.{_sig(msg)}"


def verify_token(token: str) -> tuple[int, str] | None:
    try:
        case_id, decision, exp, sig = token.split(".")
        if not hmac.compare_digest(sig, _sig(f"{case_id}.{decision}.{exp}")):
            return None
        if int(exp) < time.time():
            return None
        return int(case_id), decision
    except Exception:  # noqa: BLE001
        return None
