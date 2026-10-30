"""Evidence records: the raw answer of an external system, redacted, with its environment.

A capability is only called VERIFIED when an Evidence row shows the real system
answering in the expected way. Everything the console shows as proof points here.
"""
import json

from .config import get_settings
from .models import Evidence
from .redact import redact_obj


def environment(case_id: str = "") -> str:
    if case_id.startswith("eval-"):
        return "research"
    cfg = get_settings()
    if cfg.gateway != "paytm":
        return "fake-gateway"
    return "paytm-staging" if "stage" in cfg.paytm_host else "paytm-production"


def record(s, kind: str, payload, *, case_id: str = "", source: str = "", ok: bool = True) -> None:
    if case_id.startswith("eval-"):
        return  # research batches are summarised, not evidenced row by row
    body = json.dumps(redact_obj(payload), ensure_ascii=False, default=str)[:6000]
    s.add(Evidence(case_id=case_id, kind=kind, environment=environment(case_id), source=source, ok=ok, payload_json=body))
