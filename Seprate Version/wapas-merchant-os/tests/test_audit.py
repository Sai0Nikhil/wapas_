import pytest
from sqlalchemy.exc import IntegrityError

from app import audit
from app.models import AuditEvent


def test_audit_events_are_redacted_idempotent_and_immutable(db):
    with db.session() as session:
        first = audit.record(session, action="inventory.adjust", entity_type="product", entity_id="p1",
                             idempotency_key="adjust-1", payload={"quantity": 2, "api_key": "secret-value"})
        session.commit()
        event_id = first.id
        again = audit.record(session, action="inventory.adjust", entity_type="product", entity_id="p1",
                             idempotency_key="adjust-1", payload={"quantity": 2})
        assert again.id == event_id
        assert "secret-value" not in first.details_json
        assert first.payload_hash

        first.action = "changed"
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.delete(session.get(AuditEvent, event_id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with db.session() as session:
        persisted = session.get(AuditEvent, event_id)
        assert persisted.action == "inventory.adjust"
