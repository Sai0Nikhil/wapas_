from functools import lru_cache

from ..config import get_settings
from ..ports import Gateway


@lru_cache
def get_gateway() -> Gateway:
    s = get_settings()
    mode = (s.gateway or "").strip().lower()
    if mode not in {"fake", "paytm"}:
        raise RuntimeError("GATEWAY must be exactly 'fake' or 'paytm'; refusing an unknown payment provider.")
    if s.app_env.lower() == "production" and mode == "fake":
        raise RuntimeError(
            "The fake payment gateway cannot run in WAPAS_ENV=production. "
            "Use Paytm configuration or explicitly run an isolated development/test environment."
        )
    if mode == "paytm":
        from .paytm import PaytmGateway
        return PaytmGateway(s)
    from .fake import FakeGateway
    return FakeGateway(s)
