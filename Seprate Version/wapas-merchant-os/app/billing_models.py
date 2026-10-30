"""Persistent Counter drafts and immutable issued bill snapshots."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DDL, Numeric, UniqueConstraint, event
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class Bill(SQLModel, table=True):
    __tablename__ = "bill"
    __table_args__ = (
        UniqueConstraint("merchant_id", "store_id", "bill_number", name="uq_bill_scope_number"),
        UniqueConstraint("merchant_id", "store_id", "idempotency_key", name="uq_bill_store_idempotency"),
        CheckConstraint("subtotal_paise >= 0", name="ck_bill_subtotal_nonnegative"),
        CheckConstraint("discount_paise >= 0", name="ck_bill_discount_nonnegative"),
        CheckConstraint("tax_paise >= 0", name="ck_bill_tax_nonnegative"),
        CheckConstraint("total_paise >= 0", name="ck_bill_total_nonnegative"),
    )

    id: str = Field(default_factory=lambda: "bill_" + uuid4().hex, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    bill_number: str = Field(index=True)
    state: str = "DRAFT"  # DRAFT | ISSUED | CANCELLED; payment is separate
    payment_state: str = "NOT_RECORDED"  # NOT_RECORDED | PENDING | PAID | FAILED
    payment_id: Optional[str] = Field(default=None, index=True)
    revision: int = 1
    customer_name: str = ""
    customer_phone: str = ""
    subtotal_paise: int = 0
    discount_paise: int = 0
    tax_paise: int = 0
    total_paise: int = 0
    idempotency_key: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)
    issued_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None


class BillLine(SQLModel, table=True):
    __tablename__ = "billline"
    __table_args__ = (
        UniqueConstraint("bill_id", "product_id", name="uq_billline_product"),
        CheckConstraint("quantity > 0", name="ck_billline_positive_quantity"),
        CheckConstraint("unit_price_paise >= 0", name="ck_billline_price_nonnegative"),
        CheckConstraint("line_total_paise >= 0", name="ck_billline_total_nonnegative"),
    )

    id: str = Field(default_factory=lambda: "line_" + uuid4().hex, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    bill_id: str = Field(foreign_key="bill.id", index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    product_name: str
    sku: str
    unit: str
    quantity: Decimal = Field(sa_type=Numeric(14, 3))
    unit_price_paise: int
    line_total_paise: int
    created_at: datetime = Field(default_factory=now)


event.listen(
    Bill.__table__, "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS bill_issued_no_update BEFORE UPDATE ON bill
          WHEN OLD.state <> 'DRAFT' AND (
            (OLD.state IS NOT NEW.state AND NOT (OLD.state = 'ISSUED' AND NEW.state = 'CANCELLED')) OR
            OLD.merchant_id IS NOT NEW.merchant_id OR OLD.store_id IS NOT NEW.store_id OR
            OLD.bill_number IS NOT NEW.bill_number OR
            OLD.revision IS NOT NEW.revision OR OLD.customer_name IS NOT NEW.customer_name OR
            OLD.customer_phone IS NOT NEW.customer_phone OR OLD.subtotal_paise IS NOT NEW.subtotal_paise OR
            OLD.discount_paise IS NOT NEW.discount_paise OR OLD.tax_paise IS NOT NEW.tax_paise OR
            OLD.total_paise IS NOT NEW.total_paise OR OLD.idempotency_key IS NOT NEW.idempotency_key OR
            OLD.issued_at IS NOT NEW.issued_at OR OLD.created_at IS NOT NEW.created_at
          )
          BEGIN SELECT RAISE(ABORT, 'issued bills are immutable'); END""").execute_if(dialect="sqlite"),
)
event.listen(
    Bill.__table__, "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS bill_issued_no_delete BEFORE DELETE ON bill
          WHEN OLD.state <> 'DRAFT'
          BEGIN SELECT RAISE(ABORT, 'issued bills are immutable'); END""").execute_if(dialect="sqlite"),
)
event.listen(
    BillLine.__table__, "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS billline_issued_no_update BEFORE UPDATE ON billline
          WHEN (SELECT state FROM bill WHERE id=OLD.bill_id) <> 'DRAFT'
          BEGIN SELECT RAISE(ABORT, 'issued bill lines are immutable'); END""").execute_if(dialect="sqlite"),
)
event.listen(
    BillLine.__table__, "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS billline_issued_no_delete BEFORE DELETE ON billline
          WHEN (SELECT state FROM bill WHERE id=OLD.bill_id) <> 'DRAFT'
          BEGIN SELECT RAISE(ABORT, 'issued bill lines are immutable'); END""").execute_if(dialect="sqlite"),
)
