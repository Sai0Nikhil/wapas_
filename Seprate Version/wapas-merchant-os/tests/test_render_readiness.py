from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app import health
from app.config import Settings, get_settings
from app.main import app


def test_render_external_url_is_the_default_public_base_url(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://wapas-staging.onrender.com")

    settings = Settings(_env_file=None)

    assert settings.public_base_url == "https://wapas-staging.onrender.com"


def test_explicit_public_base_url_overrides_render_url(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://shop.example.test")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://wapas-staging.onrender.com")

    settings = Settings(_env_file=None)

    assert settings.public_base_url == "https://shop.example.test"


def test_staging_blueprint_uses_postgres_and_safe_readiness_probe():
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    service = next(item for item in blueprint["services"] if item["name"] == "wapas-staging")
    database = next(item for item in blueprint["databases"] if item["name"] == "wapas-staging-db")
    env = {item["key"]: item for item in service["envVars"]}

    assert service["healthCheckPath"] == "/healthz"
    assert database["plan"] == "0.5c-1g"
    assert env["DATABASE_URL"]["fromDatabase"]["name"] == database["name"]
    assert env["PAYTM_LIVE_ENABLED"]["value"] == "false"


def test_readiness_is_public_minimal_and_requires_worker_heartbeat(db, monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "staging")
    monkeypatch.setitem(health.WORKER, "last_tick", datetime.now(timezone.utc).isoformat())
    client = TestClient(app)

    ready = client.get("/healthz")
    private_api = client.get("/api/state")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert private_api.status_code == 401
    assert private_api.json() == {"detail": "Sign in to access this merchant workspace"}

    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    monkeypatch.setitem(health.WORKER, "last_tick", stale)
    not_ready = client.get("/healthz")
    assert not_ready.status_code == 503
    assert not_ready.json() == {"status": "not_ready"}
