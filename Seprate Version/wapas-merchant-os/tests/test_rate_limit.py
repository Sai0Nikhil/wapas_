from datetime import datetime, timezone

from app import db
from app.rate_limit import allow


def test_checkout_rate_limit_survives_engine_restart(db):
    now = datetime.now(timezone.utc)
    for _ in range(5):
        assert allow("phone:9000000001", limit=5, window_seconds=600, now=now)
    assert not allow("phone:9000000001", limit=5, window_seconds=600, now=now)

    db.reset_engine()
    db.init_db()
    assert not allow("phone:9000000001", limit=5, window_seconds=600, now=now)
