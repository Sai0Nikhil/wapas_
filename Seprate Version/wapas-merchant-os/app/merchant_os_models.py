"""Canonical merchant-scoped catalogue and inventory records."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, DDL, Index, Numeric, UniqueConstraint, event, text
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


def _quantity_column(default: Decimal = Decimal("0")) -> Column:
    return Column(Numeric(14, 3), nullable=False, default=default)


class Product(SQLModel, table=True):
    __tablename__ = "product"
    __table_args__ = (
        UniqueConstraint("merchant_id", "store_id", "sku", name="uq_product_merchant_store_sku"),
        CheckConstraint("unit_price_paise >= 0", name="ck_product_nonnegative_price"),
        Index("ix_product_merchant_store_name", "merchant_id", "store_id", "name"),
        Index("uq_product_merchant_store_barcode", "merchant_id", "store_id", "barcode", unique=True,
              sqlite_where=text("barcode <> ''"), postgresql_where=text("barcode <> ''")),
    )

    id: str = Field(primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    name: str
    category: str = ""
    sku: str
    barcode: str = ""
    image_url: str = ""
    unit: str = "each"
    unit_price_paise: int
    is_service: bool = False
    low_stock_threshold: Decimal = Field(default=Decimal("0"), sa_column=_quantity_column())
    status: str = "ACTIVE"  # ACTIVE | ARCHIVED
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)

    @property
    def active(self) -> bool:
        return self.status == "ACTIVE"


class InventoryBalance(SQLModel, table=True):
    __tablename__ = "inventorybalance"
    __table_args__ = (
        UniqueConstraint("merchant_id", "store_id", "product_id", name="uq_inventory_scope_product"),
        CheckConstraint("on_hand >= 0", name="ck_inventory_on_hand_nonnegative"),
        CheckConstraint("reserved >= 0", name="ck_inventory_reserved_nonnegative"),
        CheckConstraint("reserved <= on_hand", name="ck_inventory_reserved_within_on_hand"),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    on_hand: Decimal = Field(default=Decimal("0"), sa_column=_quantity_column())
    reserved: Decimal = Field(default=Decimal("0"), sa_column=_quantity_column())
    low_stock_threshold: Decimal = Field(default=Decimal("0"), sa_column=_quantity_column())
    updated_at: datetime = Field(default_factory=now)

    @property
    def available(self) -> Decimal:
        return self.on_hand - self.reserved


class InventoryReservation(SQLModel, table=True):
    """A durable hold so order cancellation and fulfillment can be idempotent."""
    __tablename__ = "inventoryreservation"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inventory_reservation_positive_quantity"),
        Index("ix_inventory_reservation_scope", "merchant_id", "store_id", "product_id", "state"),
    )

    id: str = Field(primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    quantity: Decimal = Field(sa_column=_quantity_column())
    source: str
    source_ref: str
    state: str = "HELD"  # HELD | RELEASED | CONSUMED
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class InventoryMovement(SQLModel, table=True):
    """Append-only stock ledger. Deltas are signed; quantity is the absolute magnitude."""
    __tablename__ = "inventorymovement"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inventory_movement_positive_quantity"),
        Index("ix_inventory_movement_scope_time", "merchant_id", "store_id", "created_at"),
        Index("ix_inventory_movement_product_time", "product_id", "created_at"),
        Index("uq_inventory_movement_idempotency", "idempotency_key", unique=True,
              sqlite_where=text("idempotency_key IS NOT NULL"),
              postgresql_where=text("idempotency_key IS NOT NULL")),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    kind: str
    quantity: Decimal = Field(sa_column=_quantity_column())
    on_hand_delta: Decimal = Field(sa_column=_quantity_column())
    reserved_delta: Decimal = Field(sa_column=_quantity_column())
    source: str
    source_ref: str
    reason: str = ""
    idempotency_key: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=now, index=True)


# Protect append-only evidence even if a future caller bypasses this service.
@event.listens_for(InventoryMovement, "before_update")
def _reject_movement_update(_mapper, _connection, _target):
    raise ValueError("inventory movements are append-only")


@event.listens_for(InventoryMovement, "before_delete")
def _reject_movement_delete(_mapper, _connection, _target):
    raise ValueError("inventory movements are append-only")


event.listen(
    InventoryMovement.__table__,
    "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS inventorymovement_no_update
          BEFORE UPDATE ON inventorymovement
          BEGIN SELECT RAISE(ABORT, 'inventory movements are append-only'); END""").execute_if(dialect="sqlite"),
)
event.listen(
    InventoryMovement.__table__,
    "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS inventorymovement_no_delete
          BEFORE DELETE ON inventorymovement
          BEGIN SELECT RAISE(ABORT, 'inventory movements are append-only'); END""").execute_if(dialect="sqlite"),
)
