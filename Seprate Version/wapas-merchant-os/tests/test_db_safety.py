import pytest

from app import db
from app.config import ROOT, get_settings


def test_protected_installation_database_is_blocked_before_engine_creation(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "database_url", f"sqlite:///{ROOT / 'wapas.db'}")
    monkeypatch.setattr(cfg, "allow_protected_database_writes", False)
    db.reset_engine()
    try:
        with pytest.raises(RuntimeError, match="protected database"):
            db.engine()
        assert db._engine is None
    finally:
        db.reset_engine()


def test_guard_recognizes_relative_and_windows_uri_spellings(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert db._sqlite_database_path("sqlite:///./wapas.db") == (ROOT / "wapas.db").resolve()
    assert db._sqlite_database_path("sqlite:////D:/Wapas/wapas.db") == (ROOT / "wapas.db").resolve()


@pytest.mark.parametrize("url", [
    "sqlite:///file:///D:/Wapas/wapas.db?uri=true",
    "sqlite:///file:/D:/Wapas/wapas.db?mode=rwc&uri=true",
    "sqlite:///file:D:/Wapas/wapas.db?mode=rwc&uri=true",
    "sqlite:///file:///D%3A/Wapas/wapas.db?mode=rwc&uri=true",
    "sqlite:///file://localhost/D:/Wapas/wapas.db?mode=rwc&uri=true",
])
def test_guard_recognizes_protected_file_uri_spellings(url, monkeypatch):
    monkeypatch.chdir(ROOT)
    assert db._sqlite_database_path(url) == (ROOT / "wapas.db").resolve()
    cfg = get_settings()
    monkeypatch.setattr(cfg, "database_url", url)
    monkeypatch.setattr(cfg, "allow_protected_database_writes", False)
    with pytest.raises(RuntimeError, match="protected database"):
        db._assert_database_target_is_safe()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_protected_database_sidecars_are_blocked_without_opening_them(suffix, monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "database_url", f"sqlite:///{ROOT / ('wapas.db' + suffix)}")
    monkeypatch.setattr(cfg, "allow_protected_database_writes", False)
    with pytest.raises(RuntimeError, match="protected database"):
        db._assert_database_target_is_safe()


def test_disposable_database_and_memory_database_are_allowed(tmp_path, monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "allow_protected_database_writes", False)
    target = tmp_path / "isolated.db"
    monkeypatch.setattr(cfg, "database_url", f"sqlite:///{target}")
    db._assert_database_target_is_safe()
    assert db._sqlite_database_path("sqlite:///:memory:") is None


def test_protected_database_override_is_explicit_and_path_only(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "database_url", f"sqlite:///{ROOT / 'wapas.db'}")
    monkeypatch.setattr(cfg, "allow_protected_database_writes", True)
    # This only validates the explicit override. It does not open or initialize the DB.
    assert db._assert_database_target_is_safe() is None
