"""Persistent storefront orders and customer-safe order status references."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DDL, Numeric, UniqueConstraint, event
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class StoreOrder(SQLModel, table=True):
    __tablename__ = "storeorder"
    __table_args__ = (
        UniqueConstraint("merchant_id", "store_id", "idempotency_key", name="uq_storeorder_idempotency"),
        CheckConstraint("amount_paise > 0", name="ck_storeorder_positive_amount"),
    )

    id: str = Field(primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    customer_id: str = Field(foreign_key="customer.id", index=True)
    payment_id: Optional[str] = Field(default=None, foreign_key="payment.id", index=True)
    idempotency_key: str
    token_hash: str = Field(unique=True, index=True)
    status: str = "PAYMENT_PENDING"  # PAYMENT_PENDING | PAID | PAYMENT_FAILED | CANCELLED | SIMULATED
    fulfillment_state: str = "UNFULFILLED"  # UNFULFILLED | FULFILLED
    amount_paise: int
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)
    paid_at: Optional[datetime] = None
    fulfilled_at: Optional[datetime] = None


class StoreOrderLine(SQLModel, table=True):
    __tablename__ = "storeorderline"
    __table_args__ = (
        UniqueConstraint("merchant_id", "store_id", "order_id", "product_id", name="uq_storeorderline_product"),
        CheckConstraint("quantity > 0", name="ck_storeorderline_positive_quantity"),
        CheckConstraint("unit_price_paise >= 0", name="ck_storeorderline_price_nonnegative"),
        CheckConstraint("line_total_paise >= 0", name="ck_storeorderline_total_nonnegative"),
    )

    id: str = Field(default_factory=lambda: "orderline_" + uuid4().hex, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    order_id: str = Field(foreign_key="storeorder.id", index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    product_name: str
    sku: str
    unit: str
    quantity: Decimal = Field(sa_type=Numeric(14, 3))
    unit_price_paise: int
    line_total_paise: int
    reservation_id: str = ""
    created_at: datetime = Field(default_factory=now)


class StoreQR(SQLModel, table=True):
    __tablename__ = "storeqr"
    __table_args__ = (UniqueConstraint("merchant_id", "store_id", name="uq_storeqr_scope"),)

    id: str = Field(default_factory=lambda: "qr_" + uuid4().hex, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    target_url: str
    verification_url: str
    status: str = "UNVERIFIED"  # UNVERIFIED | VERIFIED | DEGRADED
    verified_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=now)


event.listen(
    StoreOrderLine.__table__, "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS storeorderline_no_update BEFORE UPDATE ON storeorderline
          BEGIN SELECT RAISE(ABORT, 'store order lines are immutable'); END""").execute_if(dialect="sqlite"),
)
event.listen(
    StoreOrderLine.__table__, "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS storeorderline_no_delete BEFORE DELETE ON storeorderline
          BEGIN SELECT RAISE(ABORT, 'store order lines are immutable'); END""").execute_if(dialect="sqlite"),
)
