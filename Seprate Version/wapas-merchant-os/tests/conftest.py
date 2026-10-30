import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GATEWAY", "fake")
os.environ["WAPAS_ENV"] = "test"
os.environ["LLM_BASE_URL"] = ""
os.environ["SARVAM_API_KEY"] = ""
os.environ["N8N_WEBHOOK_URL"] = ""


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from app import db as dbm, detect, executor
    from app.config import get_settings
    from app.gateway import get_gateway
    cfg = get_settings()
    monkeypatch.setattr(cfg, "database_url", f"sqlite:///{tmp_path/'t.db'}")
    monkeypatch.setattr(cfg, "clock_override", "14:00")
    monkeypatch.setattr(cfg, "reminder_after_seconds", 3600)
    monkeypatch.setattr(cfg, "status_poll_seconds", 0.0)
    monkeypatch.setattr(cfg, "gateway", "fake")
    monkeypatch.setattr(cfg, "learning", False)
    monkeypatch.setattr(cfg, "llm_base_url", "")
    monkeypatch.setattr(cfg, "telegram_bot_token", "", raising=False)
    get_gateway.cache_clear()
    executor.policy.cache_clear()
    executor._last_check.clear()
    detect.clear_recovery()
    dbm.reset_engine()
    dbm.init_db(drop=True)
    with dbm.session() as s:
        from app import seed
        seed.seed(s)
    yield dbm
    dbm.reset_engine()
