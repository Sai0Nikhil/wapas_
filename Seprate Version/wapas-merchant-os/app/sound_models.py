"""Verified-payment notification outbox and per-browser delivery cursors."""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class SoundEvent(SQLModel, table=True):
    __tablename__ = "soundevent"
    __table_args__ = (
        UniqueConstraint("merchant_id", "idempotency_key", name="uq_sound_merchant_idempotency"),
        UniqueConstraint("payment_id", name="uq_sound_payment"),
        Index("ix_sound_scope_event", "merchant_id", "store_id", "id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    payment_id: str = Field(foreign_key="payment.id", index=True)
    source_type: str
    source_id: str
    provider_order_id: str
    provider_transaction_id: str
    amount_paise: int
    currency: str = "INR"
    idempotency_key: str = Field(index=True, max_length=120)
    verified_at: datetime = Field(default_factory=now, index=True)
    created_at: datetime = Field(default_factory=now, index=True)


class SoundDevice(SQLModel, table=True):
    __tablename__ = "sounddevice"
    __table_args__ = (
        UniqueConstraint("merchant_id", "store_id", "device_key", name="uq_sound_device_scope_key"),
        Index("ix_sound_device_scope", "merchant_id", "store_id"),
    )

    id: str = Field(default_factory=lambda: "snd_" + uuid4().hex, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    device_key: str = Field(max_length=80)
    last_event_id: int = 0
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)
