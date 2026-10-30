"""Merchant-scoped, append-only Khata ledger models."""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DDL, UniqueConstraint, event
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class KhataAccount(SQLModel, table=True):
    __tablename__ = "khataaccount"
    __table_args__ = (
        UniqueConstraint("merchant_id", "store_id", "customer_id", name="uq_khata_customer_scope"),
    )

    id: str = Field(default_factory=lambda: "khata_" + uuid4().hex, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    customer_id: str = Field(foreign_key="customer.id", index=True)
    # Cached projection for atomic repayment guards; the immutable ledger remains the source of truth.
    balance_paise: int = 0
    reminder_consent: bool = False
    status: str = "ACTIVE"
    created_at: datetime = Field(default_factory=now, index=True)


class KhataLedgerEntry(SQLModel, table=True):
    __tablename__ = "khataledgerentry"
    __table_args__ = (
        CheckConstraint("delta_paise != 0", name="ck_khata_entry_nonzero_delta"),
        UniqueConstraint("merchant_id", "store_id", "idempotency_key", name="uq_khata_entry_idempotency"),
        UniqueConstraint("reverses_entry_id", name="uq_khata_entry_single_reversal"),
    )

    id: str = Field(default_factory=lambda: "kentry_" + uuid4().hex, primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    account_id: str = Field(foreign_key="khataaccount.id", index=True)
    entry_type: str  # CREDIT_GIVEN | REPAYMENT | OPENING_BALANCE | ADJUSTMENT | REVERSAL
    # Positive means the customer owes more; negative means the customer owes less.
    delta_paise: int
    source_type: str
    source_id: str = ""
    idempotency_key: str
    payment_method: str = ""
    reverses_entry_id: Optional[str] = Field(default=None, foreign_key="khataledgerentry.id")
    due_at: Optional[datetime] = None
    note: str = ""
    recording_basis: str = "LEDGER"
    created_at: datetime = Field(default_factory=now, index=True)


event.listen(
    KhataLedgerEntry.__table__, "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS khata_entry_no_update BEFORE UPDATE ON khataledgerentry
          BEGIN SELECT RAISE(ABORT, 'Khata ledger entries are immutable'); END""").execute_if(dialect="sqlite"),
)
event.listen(
    KhataLedgerEntry.__table__, "after_create",
    DDL("""CREATE TRIGGER IF NOT EXISTS khata_entry_no_delete BEFORE DELETE ON khataledgerentry
          BEGIN SELECT RAISE(ABORT, 'Khata ledger entries are immutable'); END""").execute_if(dialect="sqlite"),
)

event.listen(
    KhataLedgerEntry.__table__, "after_create",
    DDL("""
        CREATE OR REPLACE FUNCTION khata_entry_raise_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Khata ledger entries are immutable';
        END;
        $$ LANGUAGE plpgsql;

        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'khata_entry_no_update') THEN
                CREATE TRIGGER khata_entry_no_update BEFORE UPDATE ON khataledgerentry
                FOR EACH ROW EXECUTE FUNCTION khata_entry_raise_immutable();
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'khata_entry_no_delete') THEN
                CREATE TRIGGER khata_entry_no_delete BEFORE DELETE ON khataledgerentry
                FOR EACH ROW EXECUTE FUNCTION khata_entry_raise_immutable();
            END IF;
        END $$;
    """).execute_if(dialect="postgresql"),
)
