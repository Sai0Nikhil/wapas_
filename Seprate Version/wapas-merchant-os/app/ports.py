"""Shared vocabulary and the contracts between modules.

Rule of the house: the agent proposes, the policy decides, the executor acts,
Paytm confirms. The agent module never imports a gateway.
Money is integer paise everywhere.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class Action(str, Enum):
    PAYMENT_LINK = "payment_link"
    RETRY_NOW = "retry_now"
    ASK_OWNER = "ask_owner"
    NO_ACTION = "no_action"
    REFUND = "refund"  # never allowed; listed so the policy can name it


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    ASK_OWNER = "ASK_OWNER"
    BLOCK = "BLOCK"
    HOLD = "HOLD"  # quiet hours: try again later, not a refusal


class CaseState(str, Enum):
    NEW = "NEW"
    DECIDED = "DECIDED"
    WAITING_OWNER = "WAITING_OWNER"
    SCHEDULED = "SCHEDULED"      # allowed, waiting for send_after (bank recovery / quiet hours)
    SENT = "SENT"
    RECOVERED = "RECOVERED"
    STOPPED = "STOPPED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    HOLDOUT = "HOLDOUT"          # evaluation control group: never contacted


TERMINAL = {CaseState.RECOVERED, CaseState.STOPPED, CaseState.BLOCKED}


class PayStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"  # we could not get an answer (timeout, 5xx); maps to UNKNOWN


@dataclass
class LinkResult:
    ok: bool
    link_id: str = ""
    short_url: str = ""
    error: str = ""


@dataclass
class StatusResult:
    status: PayStatus
    txn_id: str = ""
    amount_paise: int = 0
    raw: Optional[dict] = None


class Gateway(Protocol):
    name: str

    def create_link(self, *, idempotency_key: str, amount_paise: int, customer_name: str,
                    customer_phone: str, description: str, callback_url: str) -> LinkResult: ...

    def link_status(self, link_id: str) -> StatusResult: ...

    def verify_callback(self, payload: dict) -> bool: ...
