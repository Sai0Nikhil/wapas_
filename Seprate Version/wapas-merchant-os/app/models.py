"""Wapas merchant and revenue-recovery records. Money in paise. Times in UTC."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel
from .tenant_context import tenant_default_merchant, tenant_default_store


def now() -> datetime:
    return datetime.now(timezone.utc)


class Merchant(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=now)


class Store(SQLModel, table=True):
    id: str = Field(primary_key=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    name: str
    slug: str = Field(unique=True, index=True)
    timezone: str = "Asia/Kolkata"
    created_at: datetime = Field(default_factory=now)


class Customer(SQLModel, table=True):
    id: str = Field(primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    name: str
    phone: str
    language: str = "hi"          # hi, kn, ta, te, en
    opted_out: bool = False
    on_time_count: int = 0
    late_count: int = 0
    vip: bool = False


class Payment(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("merchant_id", "store_id", "idempotency_key",
                                       name="uq_payment_scope_idempotency"),)

    id: str = Field(primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    store_id: str = Field(default_factory=tenant_default_store, foreign_key="store.id", index=True)
    order_id: str = Field(index=True)
    customer_id: str = Field(foreign_key="customer.id", index=True)
    amount_paise: int
    currency: str = "INR"
    source_type: str = "RECOVERY"  # RECOVERY | COUNTER_BILL | SHOP_ORDER | KHATA_COLLECTION
    source_id: str = ""
    provider: str = "fake"         # fake | paytm
    provider_mid: str = ""
    provider_order_id: str = ""
    provider_link_id: str = ""
    provider_link_url: str = ""
    provider_transaction_id: str = ""
    idempotency_key: Optional[str] = Field(default=None, index=True)
    verified_at: Optional[datetime] = None
    bank: str
    method: str = "UPI"
    status: str                    # SUCCESS | FAILED | PENDING | PENDING_RECONCILIATION | INIT_UNKNOWN | INIT_FAILED
    failure_code: str = ""
    created_at: datetime = Field(default_factory=now, index=True)
    status_checks: int = 0         # reconciler: how many times Paytm's status API was asked
    next_check_at: Optional[datetime] = None


class Case(SQLModel, table=True):
    id: str = Field(primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    payment_id: str = Field(foreign_key="payment.id", index=True)
    batch: str = "live"            # live | eval-<n>
    group: str = "TREATED"         # TREATED | HOLDOUT
    diagnosis: str = ""            # bank_side | customer_side
    confidence: float = 0.0
    state: str = "NEW"
    messages_sent: int = 0
    owner_approved: bool = False
    send_not_before: Optional[datetime] = None
    stop_reason: str = ""
    opened_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Decision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    case_id: str = Field(foreign_key="case.id", index=True)
    diagnosis: str
    evidence_json: str
    options_json: str
    chosen_action: str
    send_after: str = "now"        # now | bank_recovered | later
    language: str = "hi"
    template: str = "bank_issue_v1"
    confidence: float = 0.0
    reasoner: str = "rules"        # rules | llm:<model>
    timing_arm: str = "now"        # now | wait  (chosen by the learning loop)
    trace_json: str = "[]"         # agent tool calls, for the UI
    raw_output: str = ""
    created_at: datetime = Field(default_factory=now)


class PolicyResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    case_id: str = Field(foreign_key="case.id", index=True)
    decision_id: int = Field(foreign_key="decision.id")
    outcome: str                   # ALLOW | ASK_OWNER | BLOCK | HOLD
    rule_hit: str
    policy_version: str
    created_at: datetime = Field(default_factory=now)


class ActionRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    case_id: str = Field(foreign_key="case.id", index=True)
    kind: str                      # payment_link | reminder
    idempotency_key: str = Field(unique=True, index=True)
    link_id: str = ""
    short_url: str = ""
    attempt_no: int = 1
    state: str = "PENDING"         # PENDING | SENT | FAILED
    error: str = ""
    created_at: datetime = Field(default_factory=now)
    sent_at: Optional[datetime] = None


class Outcome(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    case_id: str = Field(foreign_key="case.id", unique=True, index=True)
    result: str                    # RECOVERED | STOPPED | BLOCKED | UNKNOWN
    txn_id: str = ""
    amount_paise: int = 0
    detail: str = ""
    verified_at: datetime = Field(default_factory=now)


class Message(SQLModel, table=True):
    """Demo inbox: every customer-facing message, as the customer would see it."""
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    case_id: str = Field(foreign_key="case.id", index=True)
    customer_id: str
    direction: str = "out"         # out | in
    language: str = "hi"
    text: str
    channel: str = "sms"
    created_at: datetime = Field(default_factory=now)


class Evidence(SQLModel, table=True):
    """Machine-readable proof: what an external system actually said, when, in which environment.
    Secrets are redacted before storage. This is what 'verified' claims point to."""
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    case_id: str = Field(default="", index=True)
    kind: str                      # link_created | status_check | checkout_callback | link_callback | owner_decision | ...
    environment: str               # paytm-staging | paytm-production | fake-gateway | research
    source: str = ""               # which API / channel produced it
    ok: bool = True
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=now, index=True)


class Event(SQLModel, table=True):
    """Human-readable timeline shown in the owner app (not an audit log)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    case_id: str = Field(default="", index=True)
    kind: str
    text: str
    created_at: datetime = Field(default_factory=now, index=True)


class AuditEvent(SQLModel, table=True):
    """Append-only record of consequential work and its durable business references."""
    __table_args__ = (UniqueConstraint("merchant_id", "idempotency_key", name="uq_audit_merchant_idempotency"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(default_factory=tenant_default_merchant, foreign_key="merchant.id", index=True)
    store_id: str = Field(default_factory=tenant_default_store, foreign_key="store.id", index=True)
    actor_type: str = "system"       # merchant | customer | system
    actor_id: str = ""
    task_id: str = ""
    action: str
    entity_type: str
    entity_id: str
    source: str = ""
    idempotency_key: Optional[str] = Field(default=None, index=True)
    payload_hash: str = ""
    before_ref: str = ""
    after_ref: str = ""
    details_json: str = "{}"         # redacted, structured metadata only
    created_at: datetime = Field(default_factory=now, index=True)
