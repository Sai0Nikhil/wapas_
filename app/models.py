"""Money is always stored in paise (int). Never floats."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class CaseStatus(str, Enum):
    NEW = "NEW"
    PLANNED = "PLANNED"
    AWAITING_OWNER = "AWAITING_OWNER"
    OUTREACH_SENT = "OUTREACH_SENT"
    RECOVERED = "RECOVERED"        # only set after Paytm confirms
    BLOCKED = "BLOCKED"
    CLOSED_UNPAID = "CLOSED_UNPAID"
    PAUSED = "PAUSED"              # e.g. Paytm API error


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    ASK_OWNER = "ASK_OWNER"
    BLOCK = "BLOCK"


class Merchant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    paytm_mid: str = ""
    auto_limit_paise: int = 500_000
    owner_chat_id: str = ""


class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", index=True)
    external_ref: str = Field(index=True)  # Paytm CUSTID / phone
    name: str = ""
    phone: str = ""
    language: str = "hi"
    opted_out: bool = False
    on_time_payments: int = 0
    lifetime_value_paise: int = 0


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    order_id: str = Field(index=True)
    txn_id: str = ""
    amount_paise: int
    status: str = ""               # TXN_SUCCESS / TXN_FAILURE / PENDING
    bank: str = ""
    resp_code: str = ""
    resp_msg: str = ""
    created_at: datetime = Field(default_factory=now)


class Case(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    payment_id: int = Field(foreign_key="payment.id", unique=True)
    status: CaseStatus = CaseStatus.NEW
    # agent output (proposal only)
    cause: str = ""
    confidence: float = 0.0
    planned_action: str = ""
    language: str = "hi"
    # policy output (authority)
    verdict: Optional[Verdict] = None
    verdict_reason: str = ""
    reminder_count: int = 0
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Action(SQLModel, table=True):
    """Outbound side effects. The unique key makes 'send once' enforceable."""
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    kind: str                       # payment_link | reminder
    channel: str = "console"        # console | telegram | sms
    idempotency_key: str = Field(unique=True, index=True)
    payload: str = ""
    paytm_link_id: str = ""
    status: str = "PENDING"         # PENDING | SENT | FAILED
    created_at: datetime = Field(default_factory=now)
    sent_at: Optional[datetime] = None


class Approval(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    status: str = "PENDING"         # PENDING | APPROVED | SKIPPED | EXPIRED
    expires_at: datetime
    decided_at: Optional[datetime] = None


class EvidenceLog(SQLModel, table=True):
    """Append-only audit trail: why each decision was made."""
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    kind: str                       # signal | diagnosis | plan | policy | action | verify
    detail: str
    created_at: datetime = Field(default_factory=now)


class WebhookEvent(SQLModel, table=True):
    """Dedup of incoming Paytm events."""
    id: Optional[int] = Field(default=None, primary_key=True)
    event_key: str = Field(unique=True, index=True)
    raw: str = ""
    received_at: datetime = Field(default_factory=now)
