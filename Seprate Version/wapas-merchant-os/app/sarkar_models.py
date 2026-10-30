"""Session-bound, one-time confirmations for typed Sarkar operations."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class SarkarAction(SQLModel, table=True):
    __tablename__ = "sarkaraction"
    __table_args__ = (Index("ix_sarkaraction_scope_status", "merchant_id", "store_id", "status"),)

    id: str = Field(primary_key=True, max_length=80)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    actor_id: str = Field(index=True)
    session_hash: str = Field(max_length=64, index=True)
    action_type: str = Field(max_length=48)
    payload_json: str
    payload_hash: str = Field(max_length=64)
    confirmation_hash: str = Field(max_length=64)
    status: str = "OPEN"  # OPEN | EXECUTED | EXPIRED | INVALIDATED
    result_json: str = "{}"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    expires_at: datetime = Field(index=True)
    executed_at: Optional[datetime] = None
