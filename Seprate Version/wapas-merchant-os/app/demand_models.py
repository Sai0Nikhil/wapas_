"""Privacy-minimized evidence for public storefront demand searches."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class DemandEvent(SQLModel, table=True):
    __tablename__ = "demandevent"
    __table_args__ = (UniqueConstraint("merchant_id", "store_id", "event_key", name="uq_demand_event_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    query_text: str = Field(max_length=100, index=True)
    outcome: str = Field(max_length=24, index=True)  # NO_MATCH | OUT_OF_STOCK
    source: str = "public-store-search"
    event_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
