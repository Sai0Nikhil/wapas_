import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import with_loader_criteria
from sqlmodel import Session, SQLModel, create_engine

from .config import ROOT, get_settings

_engine = None
log = logging.getLogger("wapas.db")
PROTECTED_DATABASE = (ROOT / "wapas.db").resolve()
PROTECTED_DATABASE_FILES = (
    PROTECTED_DATABASE,
    Path(str(PROTECTED_DATABASE) + "-wal"),
    Path(str(PROTECTED_DATABASE) + "-shm"),
    Path(str(PROTECTED_DATABASE) + "-journal"),
)


def _sqlite_database_path(url: str) -> Path | None:
    """Resolve an SQLite URL the same way the local app does, without opening it."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        return None
    raw = parsed.database
    if raw in {":memory:", "file::memory:"}:
        return None
    if raw.startswith("file:"):
        # SQLite URI filenames can spell the same local file several ways. Normalize
        # them before comparing with the protected installation database; otherwise
        # `file:///D:/.../wapas.db?mode=rwc&uri=true` bypasses the path guard.
        uri = urlsplit(raw)
        if uri.scheme != "file" or uri.netloc.casefold() not in {"", "localhost"}:
            raise RuntimeError("Unsupported SQLite file URI; database safety cannot be established")
        if dict(parsed.query).get("mode") == "memory":
            return None
        raw = unquote(uri.path)
        if os.name == "nt" and re.match(r"^/*[A-Za-z]:/", raw):
            raw = raw.lstrip("/")
    elif "mode" in parsed.query and parsed.query["mode"] == "memory":
        return None
    # SQLAlchemy accepts both sqlite:///D:/... and sqlite:////D:/... spellings
    # on Windows; Path otherwise interprets the latter as a relative rooted path.
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", raw):
        raw = raw[1:].replace("/", "\\")
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _assert_database_target_is_safe(url: str | None = None) -> None:
    """Refuse a normal writable ORM engine for the protected populated database."""
    settings = get_settings()
    target = _sqlite_database_path(url or settings.database_url)
    same_path = False
    if target is not None:
        for protected_file in PROTECTED_DATABASE_FILES:
            if os.path.normcase(str(target)) == os.path.normcase(str(protected_file)):
                same_path = True
                break
            if target.exists() and protected_file.exists():
                try:
                    if target.samefile(protected_file):
                        same_path = True
                        break
                except OSError:
                    pass
    if same_path and not settings.allow_protected_database_writes:
        raise RuntimeError(
            f"Refusing writable application access to protected database {PROTECTED_DATABASE}. "
            "Use a disposable SQLite database for tests and local verification. "
            "An approved maintenance operation must explicitly set "
            "WAPAS_ALLOW_PROTECTED_DB_WRITES=true."
        )


@event.listens_for(Session, "do_orm_execute")
def _scope_orm_queries(execute_state):
    """Apply the request's merchant predicate to every ORM entity that carries one."""
    from .tenant_context import current_merchant_id

    merchant_id = current_merchant_id()
    if not merchant_id or not execute_state.is_select:
        return
    from .models import (ActionRecord, AuditEvent, Case, Customer, Decision, Event, Evidence,
                         Message, Outcome, Payment, PolicyResult, Store)
    from .merchant_os_models import InventoryBalance, InventoryMovement, InventoryReservation, Product
    from .billing_models import Bill, BillLine
    from .commerce_models import StoreOrder, StoreOrderLine, StoreQR
    from .khata_models import KhataAccount, KhataLedgerEntry
    from .sound_models import SoundDevice, SoundEvent
    from .demand_models import DemandEvent
    from .sarkar_models import SarkarAction

    for model in (ActionRecord, AuditEvent, Case, Customer, Decision, Event, Evidence, Message,
                  Outcome, Payment, PolicyResult, Store, InventoryBalance, InventoryMovement,
                  InventoryReservation, Product, Bill, BillLine, StoreOrder, StoreOrderLine, StoreQR,
                  KhataAccount, KhataLedgerEntry, SoundDevice, SoundEvent, DemandEvent, SarkarAction):
        execute_state.statement = execute_state.statement.options(with_loader_criteria(
            model, lambda entity: entity.merchant_id == merchant_id, include_aliases=True,
        ))


def engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        _assert_database_target_is_safe(url)
        args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=args, pool_pre_ping=True)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _pragmas(conn, _):  # the worker, the API and the reconciler read while one writes
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.close()
    return _engine


def reset_engine(url: str | None = None):
    """Used by tests to point at a fresh database."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
    if url:
        get_settings().database_url = url


def init_db(drop: bool = False):
    from . import models  # noqa: F401  (register tables)
    from . import merchant_os_models  # noqa: F401  (register catalogue and inventory tables)
    from . import billing_models  # noqa: F401  (register Counter bills)
    from . import commerce_models  # noqa: F401  (register storefront orders)
    from . import khata_models  # noqa: F401  (register Khata ledger)
    from . import auth_models  # noqa: F401  (register users, memberships, and sessions)
    from . import rate_limit_models  # noqa: F401  (register durable public checkout throttles)
    from . import sound_models  # noqa: F401  (register verified-payment outbox and device cursors)
    from . import demand_models  # noqa: F401  (register public demand evidence)
    from . import sarkar_models  # noqa: F401  (register prepared session-bound merchant actions)
    if drop:
        with engine().begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS schema_migrations"))
        SQLModel.metadata.drop_all(engine())
    SQLModel.metadata.create_all(engine())
    _run_migrations(engine())
    _add_missing_columns(engine())
    with engine().begin() as conn:
        conn.execute(text("INSERT INTO checkoutlimiterlock(id) VALUES (1) ON CONFLICT (id) DO NOTHING"))
        if inspect(conn).has_table("bill"):
            if conn.dialect.name == "sqlite":
                conn.execute(text("DROP TRIGGER IF EXISTS bill_issued_no_update"))
                conn.execute(text(
                    "CREATE TRIGGER bill_issued_no_update BEFORE UPDATE ON bill "
                    "WHEN OLD.state <> 'DRAFT' AND ("
                    "(OLD.state IS NOT NEW.state AND NOT (OLD.state = 'ISSUED' AND NEW.state = 'CANCELLED')) OR "
                    "OLD.merchant_id IS NOT NEW.merchant_id OR OLD.store_id IS NOT NEW.store_id OR "
                    "OLD.bill_number IS NOT NEW.bill_number OR "
                    "OLD.revision IS NOT NEW.revision OR OLD.customer_name IS NOT NEW.customer_name OR "
                    "OLD.customer_phone IS NOT NEW.customer_phone OR OLD.subtotal_paise IS NOT NEW.subtotal_paise OR "
                    "OLD.discount_paise IS NOT NEW.discount_paise OR OLD.tax_paise IS NOT NEW.tax_paise OR "
                    "OLD.total_paise IS NOT NEW.total_paise OR OLD.idempotency_key IS NOT NEW.idempotency_key OR "
                    "OLD.issued_at IS NOT NEW.issued_at OR OLD.created_at IS NOT NEW.created_at) "
                    "BEGIN SELECT RAISE(ABORT, 'issued bills are immutable'); END"
                ))
            elif conn.dialect.name == "postgresql":
                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION bill_raise_immutable() RETURNS trigger AS $$
                    BEGIN
                        IF OLD.state <> 'DRAFT' AND (
                            (OLD.state IS DISTINCT FROM NEW.state AND NOT (OLD.state = 'ISSUED' AND NEW.state = 'CANCELLED')) OR
                            OLD.merchant_id IS DISTINCT FROM NEW.merchant_id OR OLD.store_id IS DISTINCT FROM NEW.store_id OR
                            OLD.bill_number IS DISTINCT FROM NEW.bill_number OR OLD.revision IS DISTINCT FROM NEW.revision OR
                            OLD.customer_name IS DISTINCT FROM NEW.customer_name OR OLD.customer_phone IS DISTINCT FROM NEW.customer_phone OR
                            OLD.subtotal_paise IS DISTINCT FROM NEW.subtotal_paise OR OLD.discount_paise IS DISTINCT FROM NEW.discount_paise OR
                            OLD.tax_paise IS DISTINCT FROM NEW.tax_paise OR OLD.total_paise IS DISTINCT FROM NEW.total_paise OR
                            OLD.idempotency_key IS DISTINCT FROM NEW.idempotency_key OR OLD.issued_at IS DISTINCT FROM NEW.issued_at OR
                            OLD.created_at IS DISTINCT FROM NEW.created_at
                        ) THEN
                            RAISE EXCEPTION 'issued bills are immutable';
                        END IF;
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;

                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'bill_issued_no_update') THEN
                            CREATE TRIGGER bill_issued_no_update BEFORE UPDATE ON bill
                            FOR EACH ROW EXECUTE FUNCTION bill_raise_immutable();
                        END IF;
                    END $$;
                """))
        if inspect(conn).has_table("payment"):
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_scope_idempotency "
                "ON payment (merchant_id, store_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
            ))


_DEFAULT_MERCHANT_ID = "merchant_default"
_DEFAULT_STORE_ID = "store_default"
_TENANT_TABLES = (
    "customer", "payment", "case", "decision", "policyresult", "actionrecord",
    "outcome", "message", "evidence", "event",
)


def _run_migrations(eng) -> None:
    """Apply additive, restart-safe schema migrations and seed the installation identity."""
    from .config import get_settings

    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at VARCHAR(40) NOT NULL)"
        ))
        # The original product is a single-merchant installation. Existing rows are
        # assigned to this stable identity without changing their business fields.
        if not conn.execute(text("SELECT 1 FROM merchant WHERE id=:id"), {"id": _DEFAULT_MERCHANT_ID}).first():
            conn.execute(text("INSERT INTO merchant (id, name, created_at) VALUES (:id, :name, :created)"), {
                "id": _DEFAULT_MERCHANT_ID, "name": get_settings().merchant_name,
                "created": datetime.now(timezone.utc),
            })
        if not conn.execute(text("SELECT 1 FROM store WHERE id=:id"), {"id": _DEFAULT_STORE_ID}).first():
            conn.execute(text("INSERT INTO store (id, merchant_id, name, slug, timezone, created_at) "
                              "VALUES (:id, :merchant, :name, :slug, :timezone, :created)"), {
                "id": _DEFAULT_STORE_ID, "merchant": _DEFAULT_MERCHANT_ID,
                "name": get_settings().merchant_name, "slug": "default-store",
                "timezone": get_settings().timezone, "created": datetime.now(timezone.utc),
            })

        applied = conn.execute(text("SELECT 1 FROM schema_migrations WHERE version=1")).first()
        if applied:
            _protect_audit_events(conn)
            return

        inspector = inspect(conn)
        for table in _TENANT_TABLES:
            if not inspector.has_table(table):
                continue
            columns = {column["name"] for column in inspect(conn).get_columns(table)}
            if "merchant_id" not in columns:
                # No default is placed on the new SQL column: we explicitly backfill
                # after creating the referenced merchant, then all ORM writes carry
                # the model's stable default tenant ID.
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "merchant_id" VARCHAR(64) '
                                  'REFERENCES merchant(id)'))
            conn.execute(text(f'UPDATE "{table}" SET merchant_id=:merchant '
                              'WHERE merchant_id IS NULL OR merchant_id=:empty'),
                         {"merchant": _DEFAULT_MERCHANT_ID, "empty": ""})
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS "ix_{table}_merchant_id" '
                              f'ON "{table}" (merchant_id)'))
        conn.execute(text("INSERT INTO schema_migrations(version, applied_at) VALUES (1, :at)"),
                     {"at": datetime.now(timezone.utc).isoformat()})
        _protect_audit_events(conn)


def _protect_audit_events(conn) -> None:
    """Guards make audit records insert-only, including against accidental ORM edits."""
    if not inspect(conn).has_table("auditevent"):
        return
    if conn.dialect.name == "sqlite":
        conn.execute(text("CREATE TRIGGER IF NOT EXISTS auditevent_no_update BEFORE UPDATE ON auditevent "
                          "BEGIN SELECT RAISE(ABORT, 'audit events are immutable'); END"))
        conn.execute(text("CREATE TRIGGER IF NOT EXISTS auditevent_no_delete BEFORE DELETE ON auditevent "
                          "BEGIN SELECT RAISE(ABORT, 'audit events are immutable'); END"))
    elif conn.dialect.name == "postgresql":
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION auditevent_raise_immutable() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit events are immutable';
            END;
            $$ LANGUAGE plpgsql;

            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'auditevent_no_update') THEN
                    CREATE TRIGGER auditevent_no_update BEFORE UPDATE ON auditevent
                    FOR EACH ROW EXECUTE FUNCTION auditevent_raise_immutable();
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'auditevent_no_delete') THEN
                    CREATE TRIGGER auditevent_no_delete BEFORE DELETE ON auditevent
                    FOR EACH ROW EXECUTE FUNCTION auditevent_raise_immutable();
                END IF;
            END $$;
        """))


def _add_missing_columns(eng) -> None:
    """A database from an older Wapas keeps working: new columns are added in place (never dropped)."""
    insp = inspect(eng)
    with eng.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                default = ""
                d = col.default.arg if col.default is not None and getattr(col.default, "is_scalar", False) else None
                if isinstance(d, bool):
                    default = f" DEFAULT {int(d)}" if eng.dialect.name == "sqlite" else f" DEFAULT {'TRUE' if d else 'FALSE'}"
                elif isinstance(d, (int, float)):
                    default = f" DEFAULT {d}"
                elif isinstance(d, str):
                    default = " DEFAULT '" + d.replace("'", "''") + "'"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" '
                                  f'{col.type.compile(dialect=eng.dialect)}{default}'))
                log.warning("database upgraded: added %s.%s", table.name, col.name)
            if table.name == "payment" and "store_id" in {c["name"] for c in inspect(conn).get_columns("payment")}:
                conn.execute(text(
                    "UPDATE payment SET store_id=(SELECT store.id FROM store "
                    "WHERE store.merchant_id=payment.merchant_id ORDER BY store.created_at, store.id LIMIT 1) "
                    "WHERE store_id IS NULL OR store_id=''"
                ))


@contextmanager
def session():
    with Session(engine(), expire_on_commit=False) as s:
        yield s
