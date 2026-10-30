"""Fail-closed policy engine. Plain Python, no AI. The AI only proposes."""
from dataclasses import dataclass

from app.config import get_settings
from app.models import Verdict

BLOCKED_KINDS = {"refund", "reversal", "dispute"}


@dataclass
class PolicyInput:
    amount_paise: int
    confidence: float
    case_kind: str = "failed_payment"   # failed_payment | refund | reversal | dispute
    opted_out: bool = False
    reminder_count: int = 0
    loyal_high_value: bool = False
    paytm_api_error: bool = False


@dataclass
class PolicyDecision:
    verdict: Verdict
    reason: str


def _evaluate(p: PolicyInput) -> PolicyDecision:
    s = get_settings()
    if p.case_kind in BLOCKED_KINDS:
        return PolicyDecision(Verdict.BLOCK, f"{p.case_kind} is never automatic")
    if p.paytm_api_error:
        return PolicyDecision(Verdict.BLOCK, "Paytm API error: paused, nothing sent")
    if p.opted_out:
        return PolicyDecision(Verdict.BLOCK, "customer opted out")
    if p.reminder_count >= s.max_reminders:
        return PolicyDecision(Verdict.BLOCK, "reminder limit reached")
    if p.amount_paise > s.auto_limit_inr * 100:
        return PolicyDecision(Verdict.ASK_OWNER, "above owner's auto-limit")
    if p.confidence < s.min_confidence:
        return PolicyDecision(Verdict.ASK_OWNER, "low confidence in diagnosis")
    if p.loyal_high_value:
        return PolicyDecision(Verdict.ASK_OWNER, "loyal, high-value customer")
    return PolicyDecision(Verdict.ALLOW, "within limit, clear cause, no blockers")


def evaluate(p: PolicyInput) -> PolicyDecision:
    """Any exception => BLOCK (fail closed)."""
    try:
        return _evaluate(p)
    except Exception as exc:  # noqa: BLE001
        return PolicyDecision(Verdict.BLOCK, f"policy error, failing closed: {exc}")
