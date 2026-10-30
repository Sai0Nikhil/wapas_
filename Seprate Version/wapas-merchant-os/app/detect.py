"""Spike detection and bank health.

A bank is 'degraded' when its failure rate over the last 15 minutes is at
least 3x its 7-day baseline with at least 5 failures. Diagnosis per case is
bank_side when its bank is degraded and the failure code is technical.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from .models import Payment

WINDOW = timedelta(minutes=15)
BASELINE = timedelta(days=7)
TECHNICAL_CODES = {"BANK_TIMEOUT", "BANK_UNAVAILABLE", "NPCI_TIMEOUT", "BANK_DECLINED", "SYSTEM_ERROR"}
CUSTOMER_CODES = {"INSUFFICIENT_FUNDS", "WRONG_PIN", "USER_DROPPED", "LIMIT_EXCEEDED", "WRONG_VPA"}

# Bank health overrides. In the demo the transaction stream is simulated, so
# "the bank recovered" is an event we can also set explicitly.
_recovered_at: dict[str, datetime] = {}


@dataclass
class BankHealth:
    bank: str
    recent_attempts: int
    recent_failures: int
    recent_rate: float
    baseline_rate: float
    degraded: bool

    @property
    def multiple(self) -> float:
        return self.recent_rate / self.baseline_rate if self.baseline_rate > 0 else float("inf")


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def bank_health(s, bank: str, now: datetime | None = None) -> BankHealth:
    now = now or datetime.now(timezone.utc)
    rows = s.exec(select(Payment).where(Payment.bank == bank, Payment.created_at >= now - BASELINE)).all()
    recent = [p for p in rows if _utc(p.created_at) >= now - WINDOW]
    older = [p for p in rows if _utc(p.created_at) < now - WINDOW]
    rf = sum(1 for p in recent if p.status == "FAILED")
    ra = len(recent)
    bf = sum(1 for p in older if p.status == "FAILED")
    ba = len(older)
    recent_rate = rf / ra if ra else 0.0
    base_rate = max(bf / ba, 0.005) if ba else 0.02
    degraded = rf >= 5 and recent_rate >= 3 * base_rate
    rec = _recovered_at.get(bank)
    if rec and rec <= now:
        degraded = False
    return BankHealth(bank, ra, rf, recent_rate, base_rate, degraded)


def mark_recovered(bank: str) -> None:
    _recovered_at[bank] = datetime.now(timezone.utc)


def clear_recovery(bank: str | None = None) -> None:
    if bank:
        _recovered_at.pop(bank, None)
    else:
        _recovered_at.clear()


def is_degraded(s, bank: str) -> bool:
    return bank_health(s, bank).degraded


def diagnose(health: BankHealth, failure_code: str) -> tuple[str, float, list[str]]:
    """Return (diagnosis, confidence, evidence)."""
    if failure_code in CUSTOMER_CODES:
        return "customer_side", 0.84, [f"Failure code {failure_code} is a customer-side decline"]
    if health.degraded and failure_code in TECHNICAL_CODES:
        mult = "many" if health.multiple == float("inf") else f"{health.multiple:.0f}x"
        return "bank_side", 0.9, [
            f"{health.bank}: {health.recent_failures} of {health.recent_attempts} payments failed in 15 min",
            f"That is {mult} its normal failure rate ({health.baseline_rate:.1%})",
        ]
    if failure_code in TECHNICAL_CODES:
        return "bank_side", 0.8, [f"Technical failure code {failure_code}, no wider spike at {health.bank}"]
    return "customer_side", 0.7, [f"Unclear failure code {failure_code or 'none'}"]
