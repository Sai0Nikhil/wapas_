import asyncio

import pytest

from app.config import get_settings
from app.gateway import get_gateway


def test_production_cannot_select_fake_gateway(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "production")
    monkeypatch.setattr(cfg, "gateway", "fake")
    get_gateway.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="cannot run in WAPAS_ENV=production"):
            get_gateway()
    finally:
        get_gateway.cache_clear()


def test_production_fake_rejection_happens_before_database_initialization(monkeypatch):
    from app import main

    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "production")
    monkeypatch.setattr(cfg, "gateway", "fake")
    monkeypatch.setattr(main, "init_db", lambda: pytest.fail("database initialization must not run"))
    get_gateway.cache_clear()

    async def start():
        async with main.lifespan(main.app):
            pytest.fail("production must not start with the fake gateway")

    try:
        with pytest.raises(RuntimeError, match="cannot run in WAPAS_ENV=production"):
            asyncio.run(start())
    finally:
        get_gateway.cache_clear()


def test_unknown_gateway_name_fails_closed(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "test")
    monkeypatch.setattr(cfg, "gateway", "paytm_typo")
    get_gateway.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="GATEWAY must be exactly"):
            get_gateway()
    finally:
        get_gateway.cache_clear()


def test_fake_gateway_remains_available_only_for_isolated_nonproduction_modes(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "app_env", "test")
    monkeypatch.setattr(cfg, "gateway", "fake")
    get_gateway.cache_clear()
    try:
        assert get_gateway().name == "fake"
    finally:
        get_gateway.cache_clear()
