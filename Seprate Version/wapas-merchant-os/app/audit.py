"""Small append-only audit writer for business mutations."""
import hashlib
import json

from sqlmodel import Session, select

from .models import AuditEvent
from .redact import redact_obj
from .tenant_context import current_merchant_id, current_store_id, tenant_default_merchant, tenant_default_store


def record(session: Session, *, action: str, entity_type: str, entity_id: str,
           merchant_id: str | None = None, store_id: str | None = None,
           actor_type: str = "system", actor_id: str = "", task_id: str = "",
           source: str = "", idempotency_key: str | None = None,
           payload: dict | None = None, before_ref: str = "", after_ref: str = "") -> AuditEvent:
    """Append one redacted event; callers commit it with the business mutation."""
    merchant_id = merchant_id or current_merchant_id() or tenant_default_merchant()
    store_id = store_id or current_store_id() or tenant_default_store()
    if idempotency_key:
        prior = session.exec(select(AuditEvent).where(
            AuditEvent.merchant_id == merchant_id,
            AuditEvent.idempotency_key == idempotency_key,
        )).first()
        if prior:
            return prior
    safe = redact_obj(payload or {})
    details = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(details.encode("utf-8")).hexdigest()
    event = AuditEvent(
        merchant_id=merchant_id, store_id=store_id, actor_type=actor_type, actor_id=actor_id,
        task_id=task_id, action=action, entity_type=entity_type, entity_id=str(entity_id),
        source=source, idempotency_key=idempotency_key, payload_hash=digest,
        before_ref=before_ref, after_ref=after_ref, details_json=details,
    )
    session.add(event)
    session.flush()
    return event
