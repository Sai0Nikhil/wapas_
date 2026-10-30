"""Hold-out evaluation on a synthetic batch.

The method is real: a random hold-out that Wapas never contacts, recovery
counted only on a gateway-confirmed payment, uplift with a 95% Newcombe
interval. The customer behaviour is simulated (fake gateway only), so the
rates demonstrate the method; they are not evidence about real merchants.
"""
import json
import math
import random
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from . import executor, learning
from .gateway import get_gateway
from .models import ActionRecord, Case, Customer, Outcome, Payment, PolicyResult
from .ports import CaseState
from .timeline import log_event

CODES = [("BANK_TIMEOUT", 40), ("INSUFFICIENT_FUNDS", 25), ("WRONG_PIN", 15), ("USER_DROPPED", 20)]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def newcombe(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """Difference p1 - p2 with Newcombe's hybrid score interval (method 10)."""
    p1, p2 = (k1 / n1 if n1 else 0.0), (k2 / n2 if n2 else 0.0)
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def _pick(rng, weighted):
    r, acc = rng.randint(1, sum(w for _, w in weighted)), 0
    for v, w in weighted:
        acc += w
        if r <= acc:
            return v
    return weighted[-1][0]


def _amount(rng) -> int:
    """Assumed small-merchant ticket mix: 70% ₹200-2,000, 20% ₹2,000-5,000, 10% ₹5,000-15,000 (paise)."""
    r = rng.random()
    lo, hi = (200, 2000) if r < 0.7 else (2000, 5000) if r < 0.9 else (5000, 15000)
    return rng.randint(lo, hi) * 100


def _organic_p(c: Customer) -> float:
    return min(0.45, max(0.05, 0.12 + 0.02 * min(c.on_time_count, 10) - 0.05 * c.late_count))


# Simulated truth for the batch (unknown to Wapas): extra pay probability when contacted, by arm.
TRUE_LIFT = {("bank_side", "now"): 0.25, ("bank_side", "wait"): 0.18,
             ("customer_side", "now"): 0.10, ("customer_side", "wait"): 0.20}


def run_batch(s, n: int = 400, holdout_share: float = 0.25, seed: int = 42, wave: int = 50) -> dict:
    from .agent import rules_only
    with rules_only():  # measures policy + execution + learning; no per-case LLM spend on 300 simulated cases
        return _run_batch(s, n, holdout_share, seed, wave)


def _run_batch(s, n: int, holdout_share: float, seed: int, wave: int) -> dict:
    gw = get_gateway()
    if gw.name != "fake":
        raise RuntimeError("The evaluation batch simulates customers, so it runs on the fake gateway only")
    rng = random.Random(seed)
    learning.set_seed(seed + 1)  # arm choices are reproducible for a given seed
    batch = f"eval-{int(datetime.now(timezone.utc).timestamp() * 1000)}"  # ms: two quick runs never collide
    pool = [c for c in s.exec(select(Customer).where(Customer.id.startswith("cu"))).all()]
    when = datetime.now(timezone.utc) - timedelta(days=1)
    log_event(s, "eval", f"Evaluation batch {batch}: {n} synthetic failed payments, {holdout_share:.0%} random hold-out, waves of {wave}")
    waves = []
    for w0 in range(0, n, wave):
        cases = []
        for i in range(w0, min(n, w0 + wave)):
            cust = rng.choice(pool)
            code = _pick(rng, CODES)
            pid = f"{batch}-p{i:03d}"
            s.add(Payment(id=pid, order_id=f"E{i:03d}{batch[-4:]}", customer_id=cust.id,
                          amount_paise=_amount(rng), bank=rng.choice(["Bank B", "Bank C", "Bank D"]),
                          status="FAILED", failure_code=code, created_at=when + timedelta(minutes=i)))
            holdout = rng.random() < holdout_share
            c = Case(id=f"{batch}-c{i:03d}", payment_id=pid, batch=batch, group="HOLDOUT" if holdout else "TREATED",
                     state=CaseState.HOLDOUT.value if holdout else CaseState.NEW.value)
            s.add(c)
            cases.append((c.id, cust, holdout))
        s.commit()
        # Wapas works the treated cases through the real pipeline; the simulated owner approves escalations.
        executor.tick(s)
        for cid, _, holdout in cases:
            if not holdout and s.get(Case, cid).state == CaseState.WAITING_OWNER.value:
                executor.owner_approve(s, cid)
        for cid, _, holdout in cases:  # simulated time passes for the "wait" arm and agent-recommended delays
            c = s.get(Case, cid)
            if c.stop_reason in ("learning_wait", "agent_later"):
                c.send_not_before = datetime.now(timezone.utc) - timedelta(seconds=1)
                s.add(c)
        s.commit()
        executor.tick(s)
        arms = {"now": 0, "wait": 0}
        for cid, cust, holdout in cases:
            case = s.get(Case, cid)
            p0 = _organic_p(cust)
            if holdout:
                case.stop_reason = "paid_on_own" if rng.random() < p0 else "unpaid"
                s.add(case)
                continue
            rec = executor.link_of(s, case.id)
            if rec is None:
                continue
            arm = executor.latest_decision(s, case.id).timing_arm
            arms[arm] = arms.get(arm, 0) + 1
            if rng.random() < min(0.9, p0 + TRUE_LIFT.get((case.diagnosis, arm), 0.15)):
                gw.pay(rec.link_id)
                executor.verify(s, case, source="eval")
            else:  # simulated: reminders ran out without payment
                executor._set_state(s, case, CaseState.STOPPED, "reminder_cap")
                executor._close(s, case, "STOPPED", "No payment after reminders (simulated)")
        s.commit()
        waves.append({"wave": len(waves) + 1, "now": arms["now"], "wait": arms["wait"]})
    m = metrics(s, batch)
    m["waves"] = waves
    m["reasoner"] = "rules (the batch never calls the LLM)"
    log_event(s, "eval", f"Batch {batch}: treated {m['treated_rate']:.0%} vs hold-out {m['holdout_rate']:.0%}")
    s.commit()
    return m


def metrics(s, batch: str) -> dict:
    cases = s.exec(select(Case).where(Case.batch == batch)).all()
    treated = [c for c in cases if c.group == "TREATED"]
    hold = [c for c in cases if c.group == "HOLDOUT"]
    ids = {c.id for c in treated}
    outs = {o.case_id: o for o in s.exec(select(Outcome).where(Outcome.case_id.in_(ids))).all()} if ids else {}
    rec = [c for c in treated if outs.get(c.id) and outs[c.id].result == "RECOVERED"]
    k1, n1 = len(rec), len(treated)
    k2, n2 = sum(1 for c in hold if c.stop_reason == "paid_on_own"), len(hold)
    d, lo, hi = newcombe(k1, n1, k2, n2)
    sent_msgs = s.exec(select(ActionRecord).where(ActionRecord.case_id.in_(ids), ActionRecord.state == "SENT")).all() if ids else []
    links = [a for a in sent_msgs if a.kind == "payment_link"]
    per_case: dict[str, int] = {}
    for a in links:
        per_case[a.case_id] = per_case.get(a.case_id, 0) + 1
    duplicates = sum(1 for v in per_case.values() if v > 1)
    prs = s.exec(select(PolicyResult).where(PolicyResult.case_id.in_(ids))).all() if ids else []
    escalated = {p.case_id for p in prs if p.outcome == "ASK_OWNER"}
    allowed = {p.case_id for p in prs if p.outcome == "ALLOW"}
    breaches = sum(1 for cid in per_case if cid not in allowed)
    verified_paise = sum(outs[c.id].amount_paise for c in rec)
    return {
        "batch": batch, "treated_n": n1, "treated_recovered": k1, "treated_rate": k1 / n1 if n1 else 0.0,
        "holdout_n": n2, "holdout_paid": k2, "holdout_rate": k2 / n2 if n2 else 0.0,
        "uplift": d, "uplift_ci": [lo, hi], "verified_inr": verified_paise / 100,
        "outreach_per_recovery": (len(sent_msgs) / k1) if k1 else None,
        "escalation_rate": len(escalated) / n1 if n1 else 0.0,
        "duplicates": duplicates, "breaches": breaches,
        "learning": learning.research_summary(s, batch),
        "note": ("Simulated customers on the fake gateway (ticket mix 70% under ₹2,000, 10% above ₹5,000; "
                 "pay chances from app/evaluate.py). The method is real; the rates are not evidence."),
        "true_lift": {f"{d}:{a}": v for (d, a), v in TRUE_LIFT.items()},
    }


def latest(s) -> dict | None:
    c = s.exec(select(Case).where(Case.batch.startswith("eval-")).order_by(Case.opened_at.desc())).first()
    return metrics(s, c.batch) if c else None
