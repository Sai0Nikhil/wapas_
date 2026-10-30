"""Durable public checkout rate-limit records. Scope keys are one-way hashes."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class CheckoutLimiterLock(SQLModel, table=True):
    __tablename__ = "checkoutlimiterlock"

    id: int = Field(primary_key=True, default=1)


class CheckoutAttempt(SQLModel, table=True):
    __tablename__ = "checkoutattempt"
    __table_args__ = (Index("ix_checkoutattempt_scope_time", "scope_hash", "created_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    scope_hash: str = Field(max_length=64, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
