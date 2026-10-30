import sqlite3

from app import db
from app.models import Customer, Merchant, Store


def test_legacy_customer_rows_are_backfilled_and_migration_is_repeatable(tmp_path, monkeypatch):
    from app.config import get_settings

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE customer (
            id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, phone VARCHAR NOT NULL,
            language VARCHAR NOT NULL, opted_out BOOLEAN NOT NULL,
            on_time_count INTEGER NOT NULL, late_count INTEGER NOT NULL,
            vip BOOLEAN NOT NULL
        )""")
        conn.execute("INSERT INTO customer VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-customer", "Asha Rao", "9876543210", "te", 0, 7, 2, 1))

    monkeypatch.setattr(get_settings(), "database_url", f"sqlite:///{path}")
    db.reset_engine()
    db.init_db()
    db.init_db()

    with db.session() as session:
        customer = session.get(Customer, "legacy-customer")
        merchant = session.get(Merchant, "merchant_default")
        store = session.get(Store, "store_default")
        assert (customer.name, customer.phone, customer.language) == ("Asha Rao", "9876543210", "te")
        assert (customer.on_time_count, customer.late_count, customer.vip) == (7, 2, True)
        assert customer.merchant_id == "merchant_default"
        assert merchant is not None and store.merchant_id == merchant.id

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM customer").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=1").fetchone()[0] == 1
        fks = conn.execute("PRAGMA foreign_key_list(customer)").fetchall()
        assert any(row[2] == "merchant" and row[3] == "merchant_id" for row in fks)
