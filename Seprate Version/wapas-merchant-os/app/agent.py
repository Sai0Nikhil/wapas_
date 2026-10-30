"""The agent: one structured decision per case.

It reads a context bundle and weighs four fixed options. It never calls a
gateway and never writes customer text (it picks a template id). Output is
validated; invalid output becomes a zero-confidence decision, which the
policy then routes to the owner.
"""
import json
import threading
import time
from contextlib import contextmanager
import logging
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlmodel import select

from . import detect
from .config import get_settings
from .models import Case, Customer, Outcome, Payment
from .templates import fmt_inr

log = logging.getLogger("wapas.agent")

OPTION_ACTIONS = ("retry_now", "payment_link", "ask_owner", "no_action")


class OptionOut(BaseModel):
    action: Literal["retry_now", "payment_link", "ask_owner", "no_action"]
    verdict: Literal["chosen", "rejected"]
    why: str = Field(min_length=3, max_length=140)


class ChosenOut(BaseModel):
    action: Literal["payment_link", "no_action"]
    send_after: Literal["now", "bank_recovered", "later"]  # later = after AGENT_DELAY_SECONDS
    template: Literal["bank_issue_v1", "retry_later_v1"]


class DecisionOut(BaseModel):
    diagnosis: Literal["bank_side", "customer_side"]
    evidence: list[str] = Field(min_length=1, max_length=4)
    options: list[OptionOut] = Field(min_length=4, max_length=4)
    chosen: ChosenOut
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _consistent(self):
        acts = [o.action for o in self.options]
        if sorted(acts) != sorted(OPTION_ACTIONS):
            raise ValueError("options must be exactly retry_now, payment_link, ask_owner, no_action")
        chosen = [o for o in self.options if o.verdict == "chosen"]
        if len(chosen) != 1 or chosen[0].action != self.chosen.action:
            raise ValueError("exactly one option must be chosen and match 'chosen.action'")
        return self


@dataclass
class Bundle:
    case_id: str
    order_id: str
    amount_paise: int
    bank: str
    failure_code: str
    customer_name: str
    language: str
    on_time: int
    late: int
    vip: bool
    past_recovered: int
    past_stopped: int
    health: detect.BankHealth
    diagnosis: str
    diag_confidence: float
    evidence: list[str] = field(default_factory=list)
    learning: dict = field(default_factory=dict)
    memory: list = field(default_factory=list)
    auto_limit_paise: int = 500000

    def for_llm(self) -> dict:
        return {
            "case_id": self.case_id, "amount_inr": self.amount_paise / 100, "bank": self.bank,
            "failure_code": self.failure_code,
            "customer": {"on_time_payments": self.on_time, "late_payments": self.late, "loyal_high_value": self.vip,
                         "past_recoveries": self.past_recovered, "past_no_response": self.past_stopped},
            "bank_health": {"failures_last_15_min": self.health.recent_failures,
                            "attempts_last_15_min": self.health.recent_attempts,
                            "normal_failure_rate": round(self.health.baseline_rate, 4),
                            "degraded_now": self.health.degraded},
            "detector_evidence": self.evidence,
        }


@dataclass
class AgentDecision:
    out: DecisionOut
    reasoner: str
    raw: str = ""
    valid: bool = True
    error: str = ""
    trace: list = field(default_factory=list)


def build_bundle(s, case: Case) -> Bundle:
    pay = s.get(Payment, case.payment_id)
    cust = s.get(Customer, pay.customer_id)
    health = detect.bank_health(s, pay.bank, now=None)
    diag, conf, evidence = detect.diagnose(health, pay.failure_code)
    from .learning import evidence_for_agent, is_research
    # Memory = Wapas's own verified outcome store, with provenance. Same environment only:
    # a live case never sees simulated outcomes, and a research case only its own batch.
    same_env = (Case.batch == case.batch) if is_research(case.batch) else (~Case.batch.startswith("eval-"))
    past_rows = s.exec(select(Case.id, Outcome.result, Outcome.verified_at, Case.batch)
                       .join(Outcome, Outcome.case_id == Case.id)
                       .join(Payment, Payment.id == Case.payment_id)
                       .where(Payment.customer_id == cust.id, Case.id != case.id, same_env)
                       .order_by(Outcome.verified_at.desc())).all()
    past = [r for _, r, _, _ in past_rows]
    memory = [{"case_id": cid, "result": r, "at": at.isoformat() if at else None,
               "environment": "research" if is_research(bt) else "live"} for cid, r, at, bt in past_rows[:5]]
    learn = evidence_for_agent(s, diag, case.batch)
    from .policy import load_policy
    limit = load_policy(get_settings().policy_file).auto_max_amount_paise
    return Bundle(auto_limit_paise=limit, case_id=case.id, order_id=pay.order_id, amount_paise=pay.amount_paise, bank=pay.bank, learning=learn,
                  failure_code=pay.failure_code, customer_name=cust.name, language=cust.language,
                  on_time=cust.on_time_count, late=cust.late_count, vip=cust.vip,
                  past_recovered=sum(1 for r in past if r == "RECOVERED"),
                  past_stopped=sum(1 for r in past if r == "STOPPED"), memory=memory,
                  health=health, diagnosis=diag, diag_confidence=conf, evidence=evidence)


def rules_reasoner(b: Bundle) -> DecisionOut:
    """Deterministic fallback with the same output contract as the LLM."""
    new_customer = b.on_time == 0 and b.late == 0
    poor_payer = b.late > 0 and b.late > b.on_time // 3
    good_payer = b.on_time >= 3 and not poor_payer
    amount = f"₹{fmt_inr(b.amount_paise)}"
    history = "New customer, no payment history" if new_customer else \
        f"{b.on_time} on-time payments before" + (f", {b.late} late" if b.late else "")
    ev = list(b.evidence) + [history]
    conf = b.diag_confidence - (0.05 if poor_payer else 0.0)  # no history is not bad history
    if b.diagnosis == "bank_side":
        opts = [
            OptionOut(action="retry_now", verdict="rejected",
                      why="Rejected: bank still degraded" if b.health.degraded else "Rejected: a link lets the customer choose another bank"),
            OptionOut(action="payment_link", verdict="chosen",
                      why="Chosen: brief outage, good payer" if good_payer else "Chosen: brief outage"),
            OptionOut(action="ask_owner", verdict="rejected",
                      why=f"Not needed: under ₹{fmt_inr(b.auto_limit_paise)} limit" if b.amount_paise <= b.auto_limit_paise else f"Policy decides: {amount} is above the auto limit"),
            OptionOut(action="no_action", verdict="rejected", why="Rejected: likely a lost sale"),
        ]
        chosen = ChosenOut(action="payment_link", send_after="bank_recovered" if b.health.degraded else "now",
                           template="bank_issue_v1")
    else:
        opts = [
            OptionOut(action="retry_now", verdict="rejected", why="Rejected: the customer must act; a retry would fail again"),
            OptionOut(action="payment_link", verdict="chosen", why="Chosen: gentle link, pay when convenient"),
            OptionOut(action="ask_owner", verdict="rejected",
                      why=f"Not needed: under ₹{fmt_inr(b.auto_limit_paise)} limit" if b.amount_paise <= b.auto_limit_paise else f"Policy decides: {amount} is above the auto limit"),
            OptionOut(action="no_action", verdict="rejected", why="Rejected: likely a lost sale"),
        ]
        dropped = b.failure_code == "USER_DROPPED"
        if dropped:
            opts[1] = OptionOut(action="payment_link", verdict="chosen", why="Chosen: link later; they left checkout just now")
        chosen = ChosenOut(action="payment_link", send_after="later" if dropped else "now", template="retry_later_v1")
    return DecisionOut(diagnosis=b.diagnosis, evidence=ev[:4], options=opts, chosen=chosen, confidence=round(conf, 2))


SYSTEM_PROMPT = """You are Wapas, the payment-recovery teammate of a small Indian merchant on Paytm.
For ONE failed payment you decide what to do. You never move money and never write customer messages.
Use the tools to look at the customer's history, the bank's health and what has worked before. Then decide.
Rules for your decision:
- Weigh exactly these four options: retry_now, payment_link, ask_owner, no_action. Mark exactly one "chosen".
- chosen.action must be payment_link or no_action. A separate policy engine (not you) decides when the owner must approve.
- send_after: "bank_recovered" if the failure is bank-side AND the bank is still degraded; "later" if the customer
  left the checkout themselves moments ago (give them time to come back on their own); else "now".
- template: "bank_issue_v1" for bank-side failures, "retry_later_v1" for customer-side ones.
- Each "why" is one short phrase starting with "Chosen:", "Rejected:" or "Not needed:".
- evidence: 1-4 short facts you actually read from the tools. confidence: 0-1, lower it when facts conflict."""

DECISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["diagnosis", "evidence", "options", "chosen", "confidence"],
    "properties": {
        "diagnosis": {"type": "string", "enum": ["bank_side", "customer_side"]},
        "evidence": {"type": "array", "items": {"type": "string", "maxLength": 200}, "minItems": 1, "maxItems": 4},
        "options": {"type": "array", "minItems": 4, "maxItems": 4, "items": {
            "type": "object", "additionalProperties": False, "required": ["action", "verdict", "why"],
            "properties": {"action": {"type": "string", "enum": list(OPTION_ACTIONS)},
                           "verdict": {"type": "string", "enum": ["chosen", "rejected"]},
                           "why": {"type": "string", "maxLength": 140}}}},
        "chosen": {"type": "object", "additionalProperties": False, "required": ["action", "send_after", "template"],
                   "properties": {"action": {"type": "string", "enum": ["payment_link", "no_action"]},
                                  "send_after": {"type": "string", "enum": ["now", "bank_recovered", "later"]},
                                  "template": {"type": "string", "enum": ["bank_issue_v1", "retry_later_v1"]}}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

TOOL_NAMES = ("get_customer_history", "get_bank_health", "get_learning_stats")  # read-only; no tool moves money
TOOLS = [
    {"type": "function", "function": {"name": "get_customer_history", "description": "Payment history and past recovery outcomes of this customer.",
                                      "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "get_bank_health", "description": "Failure rate of the payer's bank in the last 15 minutes vs its normal rate.",
                                      "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "get_learning_stats", "description": "Verified recovery results so far for this kind of failure, by send timing.",
                                      "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
]


def run_tool(b: "Bundle", name: str) -> dict:
    if name == "get_customer_history":
        return {"on_time_payments": b.on_time, "late_payments": b.late, "loyal_high_value": b.vip,
                "past_recoveries": b.past_recovered, "past_no_response": b.past_stopped, "language": b.language,
                "past_cases": b.memory or []}
    if name == "get_bank_health":
        h = b.health
        return {"bank": h.bank, "failures_last_15_min": h.recent_failures, "attempts_last_15_min": h.recent_attempts,
                "normal_failure_rate": round(h.baseline_rate, 4), "degraded_now": h.degraded,
                "detector_evidence": b.evidence}
    if name == "get_learning_stats":
        return b.learning or {"note": "no verified outcomes yet"}
    return {"error": f"'{name}' is not an allowed tool; nothing was executed", "allowed": list(TOOL_NAMES)}


def rules_trace(b: "Bundle") -> list[dict]:
    """The rule reasoner reads the same facts deterministically; the trace says so (no model was involved)."""
    return [{"tool": n, "result": run_tool(b, n), "caller": "rules"} for n in TOOL_NAMES]


_local = threading.local()


@contextmanager
def rules_only():
    """Force the rule reasoner on this thread (the evaluation batch: 300+ cases, no per-case LLM spend)."""
    prev = getattr(_local, "rules", False)
    _local.rules = True
    try:
        yield
    finally:
        _local.rules = prev


def _chat(body: dict) -> dict:
    cfg = get_settings()
    headers = {"Authorization": f"Bearer {cfg.llm_api_key}"}
    if "sarvam" in cfg.llm_base_url:
        headers["api-subscription-key"] = cfg.llm_api_key
        if "reasoning_effort" not in body:  # an explicit value (even null) wins
            eff = (cfg.llm_reasoning_effort or "").strip().lower()
            # Sarvam reasons by default when the field is absent, so "off" must be sent as null.
            body = {**body, "reasoning_effort": eff if eff in ("low", "medium", "high") else None}
        if "max_tokens" not in body:  # thinking shares the budget with the answer
            body = {**body, "max_tokens": 4096 if body.get("reasoning_effort") else 1024}
    url = cfg.llm_base_url.rstrip("/") + "/chat/completions"
    timeout = 90.0 if body.get("reasoning_effort") else 45.0
    for attempt in range(4):  # rate limits are expected when many cases are decided at once
        r = httpx.post(url, json=body, timeout=timeout, headers=headers)
        if r.status_code in (429, 503) and attempt < 3 and "quota" not in r.text.lower():
            try:
                wait = min(float(r.headers.get("retry-after", "")), 10.0)
            except ValueError:
                wait = 2.0 * (2 ** attempt)  # 2, 4, 8 s
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]


def _parse(text: str) -> DecisionOut:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t.strip("`")
        t = t.rsplit("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    return DecisionOut.model_validate(json.loads(t[i:j + 1] if i >= 0 else t))


def llm_reasoner(b: "Bundle") -> tuple[DecisionOut | None, str, str, list[dict]]:
    """Tool-using agent. Returns (decision or None, raw text, error, trace)."""
    cfg = get_settings()
    facts = {"case_id": b.case_id, "amount_inr": b.amount_paise / 100, "bank": b.bank, "failure_code": b.failure_code}
    msgs = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Failed payment:\n" + json.dumps(facts, ensure_ascii=False)}]
    trace: list[dict] = []
    try:
        for _ in range(4):  # at most 4 tool rounds
            m = _chat({"model": cfg.llm_model, "temperature": 0, "messages": msgs, "tools": TOOLS, "tool_choice": "auto"})
            calls = m.get("tool_calls") or []
            if not calls:
                break
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
            for c in calls:
                name = str(c.get("function", {}).get("name", ""))[:60]
                result = run_tool(b, name)
                entry = {"tool": name, "result": result, "caller": "model"}
                if name not in TOOL_NAMES:
                    entry["rejected"] = True  # hallucinated or disallowed tool: refused, nothing executed
                trace.append(entry)
                msgs.append({"role": "tool", "tool_call_id": c.get("id", name), "content": json.dumps(result, ensure_ascii=False)})
    except httpx.HTTPStatusError as e:
        if e.response.status_code not in (400, 404, 422):  # only a rejected request means "no tool support"
            raise
        trace.append({"tool": "(provider refused tools; continuing without)", "result": {"status": e.response.status_code}})
        for n in ("get_customer_history", "get_bank_health", "get_learning_stats"):
            r = run_tool(b, n)
            trace.append({"tool": n, "result": r})
            msgs.append({"role": "user", "content": f"{n}: " + json.dumps(r, ensure_ascii=False)})
    msgs.append({"role": "user", "content": "Now give your decision as JSON only, matching the schema."})
    # Sarvam rejects a request that carries tool messages without the tool list (400, seen live), so the
    # final call repeats the tools and forbids using them.
    no_more_tools = {"tools": TOOLS, "tool_choice": "none"} if any(x.get("role") == "tool" for x in msgs) else {}
    try:
        m = _chat({"model": cfg.llm_model, "temperature": 0, "messages": msgs, **no_more_tools,
                   "response_format": {"type": "json_schema", "json_schema": {"name": "decision", "schema": DECISION_SCHEMA, "strict": True}}})
    except httpx.HTTPStatusError as e:
        if e.response.status_code not in (400, 404, 422):
            raise
        m = _chat({"model": cfg.llm_model, "temperature": 0, "messages": msgs, **no_more_tools,
                   "response_format": {"type": "json_object"}})
    raw = m.get("content") or ""
    try:
        return _parse(raw), raw, "", trace
    except (ValidationError, ValueError, KeyError) as e:
        return None, raw, str(e)[:500], trace


def decide(b: "Bundle") -> AgentDecision:
    cfg = get_settings()
    if cfg.llm_enabled and not getattr(_local, "rules", False):
        try:
            out, raw, err, trace = llm_reasoner(b)
        except Exception as e:  # noqa: BLE001  (LLM down -> rules, and say so)
            log.warning("LLM unavailable, using rules: %s", e)
            return AgentDecision(rules_reasoner(b), "rules (LLM unavailable)", error=str(e)[:200], trace=rules_trace(b))
        if out is None:
            safe = rules_reasoner(b)
            safe.confidence = 0.0  # invalid model output -> owner decides
            safe.evidence = (["Agent output failed validation; routed to the owner"] + safe.evidence)[:4]
            return AgentDecision(safe, f"llm:{cfg.llm_model}", raw=raw, valid=False, error=err, trace=trace)
        return AgentDecision(calibrate(out, b), f"llm:{cfg.llm_model}", raw=raw, trace=trace)
    return AgentDecision(rules_reasoner(b), "rules", trace=rules_trace(b))


def calibrate(out: DecisionOut, b: "Bundle") -> DecisionOut:
    """A model's self-reported confidence is not evidence. It may never exceed what the detector's
    evidence supports, and disagreeing with the detector sends the case to the owner (via the policy floor)."""
    if out.diagnosis == b.diagnosis:
        out.confidence = round(min(out.confidence, b.diag_confidence), 2)
    else:
        out.confidence = round(min(out.confidence, 0.6), 2)
        out.evidence = ([f"Model says {out.diagnosis.replace('_', '-')}, detector says {b.diagnosis.replace('_', '-')}: owner decides"]
                        + out.evidence)[:4]
    return out
