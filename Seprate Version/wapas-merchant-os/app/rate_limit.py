"""Cross-process checkout throttling backed by the configured database."""
import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text

from .db import engine
from .rate_limit_models import CheckoutAttempt


def _scope_hash(key: str) -> str:
    return hashlib.sha256(("wapas-checkout-rate:" + key).encode("utf-8")).hexdigest()


def allow(key: str, *, limit: int, window_seconds: float, now: datetime | None = None) -> bool:
    """Atomically record one attempt if its durable rolling-window count is below limit."""
    if limit <= 0 or window_seconds <= 0:
        return False
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    scope = _scope_hash(key)
    connection = engine().connect()
    try:
        if connection.dialect.name == "sqlite":
            # The first checkout write takes a database-wide RESERVED lock so two
            # workers cannot both pass a count check for the same final allowance.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            connection.begin()
            connection.execute(text("SELECT id FROM checkoutlimiterlock WHERE id=1 FOR UPDATE"))
        count = connection.execute(
            select(func.count()).select_from(CheckoutAttempt.__table__).where(
                CheckoutAttempt.scope_hash == scope,
                CheckoutAttempt.created_at >= cutoff,
            )
        ).scalar_one()
        if count >= limit:
            connection.commit()
            return False
        connection.execute(CheckoutAttempt.__table__.insert().values(scope_hash=scope, created_at=now))
        # Retain only one day of history; the phone is never stored, even transiently.
        connection.execute(delete(CheckoutAttempt.__table__).where(
            CheckoutAttempt.created_at < now - timedelta(days=1),
        ))
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
