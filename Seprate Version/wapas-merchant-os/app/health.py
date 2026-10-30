"""In-process heartbeat for the proof panel: is the worker alive, when did it last reconcile."""
from datetime import datetime, timezone

WORKER = {"started": None, "last_tick": None, "ticks": 0, "last_error": "", "last_reconcile": None,
          "reconcile": {}}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
