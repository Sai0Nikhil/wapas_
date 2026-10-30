import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlmodel import SQLModel

from app import db
from app.config import get_settings


def test_sqlite_guard_ignores_postgresql_urls():
    pg_url = "postgresql://wapas_user:secret@db.render.com:5432/wapas_staging"
    assert db._sqlite_database_path(pg_url) is None


def test_postgresql_ddl_compilation_all_models():
    """Verify that every SQLModel table compiles cleanly to valid PostgreSQL DDL."""
    from app import (
        models,
        merchant_os_models,
        billing_models,
        commerce_models,
        khata_models,
        auth_models,
        rate_limit_models,
        sound_models,
        demand_models,
        sarkar_models,
    )

    dialect = postgresql.dialect()
    for table in SQLModel.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert f'CREATE TABLE {table.name}' in ddl.replace('"', "")
        for idx in table.indexes:
            idx_ddl = str(CreateIndex(idx).compile(dialect=dialect))
            assert "CREATE" in idx_ddl


def test_postgresql_trigger_definitions_contain_plpgsql_guards():
    """Verify the PL/pgSQL trigger strings in db.py and khata_models.py."""
    with open("app/db.py", "r", encoding="utf-8") as f:
        db_code = f.read()
    with open("app/khata_models.py", "r", encoding="utf-8") as f:
        khata_code = f.read()

    assert "CREATE OR REPLACE FUNCTION bill_raise_immutable()" in db_code
    assert "RAISE EXCEPTION 'issued bills are immutable';" in db_code
    assert "CREATE OR REPLACE FUNCTION auditevent_raise_immutable()" in db_code
    assert "RAISE EXCEPTION 'audit events are immutable';" in db_code
    assert "CREATE OR REPLACE FUNCTION khata_entry_raise_immutable()" in khata_code
    assert "RAISE EXCEPTION 'Khata ledger entries are immutable';" in khata_code


def test_psycopg2_driver_installed_and_importable():
    import psycopg2
    assert hasattr(psycopg2, "__version__")
