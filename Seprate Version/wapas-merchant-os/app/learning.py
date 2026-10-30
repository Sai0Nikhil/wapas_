"""The Learn step, split into two environments that never mix.

LIVE (real customers, real merchant traffic):
    observe -> verify outcome (Paytm) -> store -> aggregate -> evidence -> recommend.
    Passive only. Nothing here chooses an action for a live customer, and no
    randomness ever touches live traffic. Timing on live cases is decided by
    the agent and the policy, deterministically.

RESEARCH (evaluation batches of simulated customers, ids "eval-*"):
    observe -> experiment -> measure -> learn.
    Thompson sampling on *when* to send the first message ("now" vs "wait"),
    with a 20% exploration floor. Each batch starts from flat priors and
    learns only from its own simulated outcomes.

`choose_arm` refuses to run on anything that is not a research batch.
"""
import math
import random

from sqlmodel import select

from .models import Case, Decision, Outcome

ARMS = ("now", "wait")
EXPLORE = 0.2  # research only: share of choices made uniformly at random
_rng = random.Random()


class LiveExperimentError(RuntimeError):
    """Raised if anything tries to run an experiment on live traffic."""


def is_research(batch: str) -> bool:
    return bool(batch) and batch.startswith("eval-")


def set_seed(seed: int | None) -> None:
    """Make research arm choices reproducible."""
    global _rng
    _rng = random.Random(seed)


def arm_stats(s, diagnosis: str, batch: str) -> dict[str, dict]:
    rows = s.exec(select(Decision.timing_arm, Outcome.result)
                  .join(Case, Case.id == Decision.case_id)
                  .join(Outcome, Outcome.case_id == Case.id)
                  .where(Case.diagnosis == diagnosis, Case.group == "TREATED", Case.batch == batch,
                         Outcome.result.in_(["RECOVERED", "STOPPED"]))).all()
    stats = {a: {"paid": 0, "unpaid": 0} for a in ARMS}
    for arm, result in rows:
        if arm in stats:
            stats[arm]["paid" if result == "RECOVERED" else "unpaid"] += 1
    for a in ARMS:
        p, u = stats[a]["paid"], stats[a]["unpaid"]
        stats[a]["n"] = p + u
        stats[a]["mean"] = (1 + p) / (2 + p + u)
    return stats


def choose_arm(s, diagnosis: str, rng: random.Random | None = None, *, batch: str) -> tuple[str, dict]:
    """Research only. Live batches raise: real customers are never randomised."""
    if not is_research(batch):
        raise LiveExperimentError(f"exploration refused for batch '{batch}': experiments run on research batches only")
    rng = rng or _rng
    stats = arm_stats(s, diagnosis, batch)
    draws = {a: rng.betavariate(1 + stats[a]["paid"], 1 + stats[a]["unpaid"]) for a in ARMS}
    best = max(draws, key=draws.get)
    # Batched feedback plus an unlucky first wave can starve an arm, so research keeps exploring.
    explored = rng.random() < EXPLORE
    if explored:
        best = rng.choice(ARMS)
    return best, {"stats": stats, "draws": {a: round(v, 3) for a, v in draws.items()}, "explored": explored}


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def live_evidence(s) -> dict:
    """Passive evidence from live cases: verified outcomes after contact, per diagnosis.
    Read-only. It informs the agent's context and the owner; it never picks an action."""
    rows = s.exec(select(Case.diagnosis, Outcome.result)
                  .join(Outcome, Outcome.case_id == Case.id)
                  .where(Case.batch == "live", Case.group == "TREATED",
                         Outcome.result.in_(["RECOVERED", "STOPPED"]))).all()
    out = {}
    for d in ("bank_side", "customer_side"):
        k = sum(1 for dg, r in rows if dg == d and r == "RECOVERED")
        n = sum(1 for dg, _ in rows if dg == d)
        lo, hi = _wilson(k, n)
        out[d] = {"contacted_closed": n, "verified_paid": k, "rate": (k / n) if n else None,
                  "ci95": [round(lo, 3), round(hi, 3)] if n else None}
    return out


def research_summary(s, batch: str) -> dict:
    return {d: arm_stats(s, d, batch) for d in ("bank_side", "customer_side")}


def evidence_for_agent(s, diagnosis: str, batch: str) -> dict:
    """What the agent's get_learning_stats tool returns: live evidence for live cases,
    the batch's own arm statistics for research cases."""
    if is_research(batch):
        st = arm_stats(s, diagnosis, batch)
        return {"environment": "research (simulated)", **{a: {"paid": v["paid"], "unpaid": v["unpaid"]} for a, v in st.items()}}
    ev = live_evidence(s)[diagnosis]
    return {"environment": "live (passive evidence only)", **ev}
