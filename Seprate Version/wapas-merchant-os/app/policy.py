"""Deterministic, fail-closed policy gate.

The agent's output is only an *input* here. Nothing reaches a gateway
without an ALLOW from `evaluate`.
"""
from dataclasses import dataclass
from datetime import time
from pathlib import Path

import yaml

from .ports import Action, Verdict

REQUIRED = {"version", "allowed_actions", "never_automatic", "limits", "quiet_hours", "ask_owner_for_vip"}
LIMIT_KEYS = {"auto_max_amount_inr", "min_confidence", "max_reminders", "duplicate_window_minutes"}


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Policy:
    version: str
    allowed_actions: frozenset
    never_automatic: frozenset
    auto_max_amount_paise: int
    min_confidence: float
    max_reminders: int
    duplicate_window_minutes: int
    quiet_start: time
    quiet_end: time
    ask_owner_for_vip: bool


def _parse_time(v) -> time:
    try:
        h, m = str(v).split(":")
        return time(int(h), int(m))
    except Exception as e:  # noqa: BLE001
        raise PolicyError(f"bad time {v!r}") from e


def load_policy(path: str | Path) -> Policy:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise PolicyError(f"cannot read policy: {e}") from e
    if not isinstance(raw, dict):
        raise PolicyError("policy must be a mapping")
    keys = set(raw)
    if keys != REQUIRED:
        raise PolicyError(f"policy keys mismatch: missing={REQUIRED - keys} unknown={keys - REQUIRED}")
    lim = raw["limits"]
    if not isinstance(lim, dict) or set(lim) != LIMIT_KEYS:
        raise PolicyError(f"limits keys must be exactly {sorted(LIMIT_KEYS)}")
    valid_actions = {a.value for a in Action}
    allowed = set(raw["allowed_actions"] or [])
    never = set(raw["never_automatic"] or [])
    if not allowed <= valid_actions or not never <= valid_actions:
        raise PolicyError("unknown action name in policy")
    if allowed & never:
        raise PolicyError("an action cannot be both allowed and never_automatic")
    if Action.REFUND.value in allowed:
        raise PolicyError("refund may never be allowlisted")
    amount = lim["auto_max_amount_inr"]
    conf = lim["min_confidence"]
    if not (isinstance(amount, (int, float)) and amount > 0):
        raise PolicyError("auto_max_amount_inr must be > 0")
    if not (isinstance(conf, (int, float)) and 0 < conf <= 1):
        raise PolicyError("min_confidence must be in (0, 1]")
    if not (isinstance(lim["max_reminders"], int) and lim["max_reminders"] >= 0):
        raise PolicyError("max_reminders must be an int >= 0")
    return Policy(
        version=str(raw["version"]),
        allowed_actions=frozenset(allowed),
        never_automatic=frozenset(never),
        auto_max_amount_paise=int(round(float(amount) * 100)),
        min_confidence=float(conf),
        max_reminders=int(lim["max_reminders"]),
        duplicate_window_minutes=int(lim["duplicate_window_minutes"]),
        quiet_start=_parse_time(raw["quiet_hours"]["start"]),
        quiet_end=_parse_time(raw["quiet_hours"]["end"]),
        ask_owner_for_vip=bool(raw["ask_owner_for_vip"]),
    )


@dataclass(frozen=True)
class PolicyContext:
    action: str
    amount_paise: int
    confidence: float
    opted_out: bool
    reminders_sent: int
    recent_open_link_same_order: bool
    local_time: time
    is_reminder: bool = False
    vip: bool = False
    owner_approved: bool = False  # set when the owner tapped Approve


@dataclass(frozen=True)
class PolicyDecision:
    verdict: Verdict
    rule: str
    reason: str
    version: str


def _in_quiet_hours(t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= t < end
    return t >= start or t < end  # window crosses midnight


def evaluate(p: Policy, c: PolicyContext) -> PolicyDecision:
    def d(v, rule, reason):
        return PolicyDecision(v, rule, reason, p.version)

    if c.opted_out:
        return d(Verdict.BLOCK, "opted_out", "Customer opted out of messages")
    if c.action in p.never_automatic or c.action == Action.REFUND.value:
        return d(Verdict.BLOCK, "never_money_back", "Refunds and reversals are never automatic")
    if c.is_reminder and c.reminders_sent >= p.max_reminders:
        return d(Verdict.BLOCK, "reminder_cap", f"Link and {c.reminders_sent} reminders sent, no payment")
    if not c.is_reminder and c.recent_open_link_same_order:
        return d(Verdict.BLOCK, "duplicate", f"A link for this order was sent within {p.duplicate_window_minutes} min")
    if c.action not in p.allowed_actions:
        return d(Verdict.BLOCK, "not_allowlisted", f"Action '{c.action}' is not allowed")
    if c.action == Action.NO_ACTION.value:
        return d(Verdict.ALLOW, "default_allow", "No action needed")
    if _in_quiet_hours(c.local_time, p.quiet_start, p.quiet_end):
        return d(Verdict.HOLD, "quiet_hours", "Outside sending hours; held until morning")
    if not c.owner_approved:
        if c.amount_paise > p.auto_max_amount_paise:
            return d(Verdict.ASK_OWNER, "owner_amount", f"Above the ₹{p.auto_max_amount_paise // 100:,} auto limit")
        if c.confidence < p.min_confidence:
            return d(Verdict.ASK_OWNER, "owner_confidence", f"Confidence {c.confidence:.2f} below {p.min_confidence:.2f}")
        if c.vip and p.ask_owner_for_vip:
            return d(Verdict.ASK_OWNER, "owner_vip", "Loyal high-value customer")
    return d(Verdict.ALLOW, "default_allow", "Within the owner's limits" if not c.owner_approved else "Approved by the owner")
