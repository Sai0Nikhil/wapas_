"""Turns one case into the story a judge can follow: a timestamped job trace and a structured
INPUT -> DECISION -> REASON -> POLICY -> ACTION -> RESULT card. Structured evidence only; no
hidden chain-of-thought is stored or shown."""
import json

from sqlmodel import select

from . import evidence as ev
from .executor import latest_decision, local_time, policy
from .models import ActionRecord, Case, Customer, Evidence, Message, Outcome, Payment, PolicyResult
from .policy import _in_quiet_hours
from .templates import LANG_NAMES, fmt_inr

VERDICT = {"ALLOW": "AUTO", "ASK_OWNER": "OWNER", "BLOCK": "BLOCK", "HOLD": "HOLD"}


def source_of(pay: Payment, gateway: str) -> dict:
    if pay.id.startswith("pay_WAP"):
        if gateway == "paytm":
            return {"kind": "paytm", "label": "Paytm checkout (test environment)"}
        return {"kind": "store-fake", "label": "Store checkout · fake gateway"}
    return {"kind": "simulated", "label": "Simulated signal (demo data)"}


def _iso(dt):
    return dt.isoformat() if dt else None


def build(s, case_id: str, gateway: str) -> dict:
    c = s.get(Case, case_id)
    pay = s.get(Payment, c.payment_id)
    cust = s.get(Customer, pay.customer_id)
    dec = latest_decision(s, case_id)
    prs = s.exec(select(PolicyResult).where(PolicyResult.case_id == case_id).order_by(PolicyResult.id)).all()
    acts = s.exec(select(ActionRecord).where(ActionRecord.case_id == case_id).order_by(ActionRecord.id)).all()
    out = s.exec(select(Outcome).where(Outcome.case_id == case_id)).first()
    msgs = s.exec(select(Message).where(Message.case_id == case_id, Message.direction == "out").order_by(Message.id)).all()
    evs = s.exec(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.id)).all()
    src = source_of(pay, gateway)
    p = policy()
    trace = json.loads(dec.trace_json or "[]") if dec else []
    link = next((a for a in acts if a.kind == "payment_link" and a.state == "SENT"), None)
    failed_links = [a for a in acts if a.kind == "payment_link" and a.state == "FAILED"]
    reminders = [a for a in acts if a.kind == "reminder"]
    owner_ev = [e for e in evs if e.kind in ("owner_approved", "owner_skipped")]
    status_ev = [e for e in evs if e.kind == "status_check"]
    lang = LANG_NAMES.get(cust.language, cust.language)

    steps = []

    def step(at, title, detail, state="done"):
        steps.append({"at": _iso(at), "title": title, "detail": detail, "state": state})

    step(pay.created_at, "Signal detected",
         f"{pay.failure_code or 'payment failed'} · {pay.bank} · ₹{fmt_inr(pay.amount_paise)} · {src['label']}")
    if dec:
        tools = [t["tool"] + (" (refused)" if t.get("rejected") else "") for t in trace]
        by_model = any(t.get("caller") == "model" for t in trace)
        step(dec.created_at, "Context gathered",
             (("model called: " if by_model else "rule reasoner looked up (no model): ") + ", ".join(tools)) if tools else "no tools called")
        step(dec.created_at, "Cause diagnosed", f"{dec.diagnosis.replace('_', '-')} · {dec.confidence:.0%} confident")
        opts = json.loads(dec.options_json or "[]")
        chosen = next((o for o in opts if o.get("verdict") == "chosen"), {})
        step(dec.created_at, "Recovery options evaluated", f"{len(opts)} weighed · {chosen.get('why', '')}")
    else:
        step(None, "Agent decision", "waiting for the agent", "pending")
    if prs:
        last = prs[-1]
        step(last.created_at, f"Policy → {VERDICT.get(last.outcome, last.outcome)}",
             f"rule {last.rule_hit} · policy {last.policy_version}" + (f" · {len(prs)} checks" if len(prs) > 1 else ""),
             "failed" if last.outcome == "BLOCK" else "done")
    for e in owner_ev:
        d = json.loads(e.payload_json or "{}")
        step(e.created_at, "Owner approved" if e.kind == "owner_approved" else "Owner skipped", f"via {d.get('via', '?')}")
    for e in [x for x in evs if x.kind == "customer_reply"]:
        d = json.loads(e.payload_json or "{}")
        step(e.created_at, f"Customer replied → {d.get('intent', '?').replace('_', ' ')}",
             f"“{d.get('quote') or d.get('text', '')[:60]}” · understood by {d.get('reasoner')}"
             + (" · heard via Sarvam speech-to-text" if d.get("stt") else "") + f" · {d.get('action')}")
    for a in failed_links:
        step(a.created_at, "Paytm link attempt failed", (a.error or "")[:120], "failed")
    if link:
        step(link.sent_at, "Payment link created", f"{'Paytm' if gateway == 'paytm' else 'Fake gateway'} link {link.link_id} · "
                                                   f"idempotency key {link.idempotency_key}")
        if msgs:
            step(msgs[0].created_at, "Customer messaged", f"{lang} · channel {msgs[0].channel} · sent exactly once")
        if reminders:
            step(reminders[-1].sent_at, "Reminders", f"{len(reminders)} with the same link (cap {p.max_reminders})")
    elif c.state in ("SCHEDULED",):
        step(c.send_not_before or c.updated_at, "Waiting to send", c.stop_reason.replace("_", " "), "pending")
    if status_ev:
        d = json.loads(status_ev[-1].payload_json or "{}")
        ms = d.get("mapped_status")
        step(status_ev[-1].created_at, f"Payment status → {'PAID' if ms == 'SUCCESS' else ms}",
             status_ev[-1].source if status_ev[-1].source == status_ev[-1].environment else
             f"{status_ev[-1].source} · {status_ev[-1].environment}", "done" if ms in ("SUCCESS", "PENDING") else "failed")
    if out:
        label = {"RECOVERED": "Recovery verified", "STOPPED": "Stopped", "BLOCKED": "Blocked by policy"}.get(out.result, out.result)
        step(out.verified_at, label, (out.detail or "") + (f" · txn {out.txn_id}" if out.txn_id else ""),
             "done" if out.result == "RECOVERED" else "failed")
    elif c.state == "UNKNOWN":
        step(c.updated_at, "Unknown: not counted", c.stop_reason.replace("_", " ") or "status check failed", "failed")
    elif link:
        step(None, "Waiting for Paytm to confirm payment", "", "pending")

    steps.sort(key=lambda x: (x["at"] is None, x["at"] or ""))  # chronological; open items last

    # structured decision card
    health = trace_result(trace, "get_bank_health")
    hist = trace_result(trace, "get_customer_history")
    checks = [
        {"rule": f"amount ≤ ₹{fmt_inr(p.auto_max_amount_paise)} auto limit", "ok": pay.amount_paise <= p.auto_max_amount_paise},
        {"rule": f"confidence ≥ {p.min_confidence:.0%}", "ok": (dec.confidence >= p.min_confidence) if dec else None},
        {"rule": "customer has not opted out", "ok": not cust.opted_out},
        {"rule": "not a loyal customer the owner reviews", "ok": not (cust.vip and p.ask_owner_for_vip)},
        {"rule": f"outside quiet hours ({p.quiet_start}–{p.quiet_end})", "ok": not _in_quiet_hours(local_time(), p.quiet_start, p.quiet_end)},
        {"rule": "refunds are never automatic", "ok": True},
    ]
    card = None
    if dec:
        opts = json.loads(dec.options_json or "[]")
        chosen = next((o for o in opts if o.get("verdict") == "chosen"), {})
        timing = {"now": "now", "bank_recovered": "after the bank recovers", "later": "later (agent's judgment)"}.get(dec.send_after, dec.send_after)
        last = prs[-1] if prs else None
        result = (f"{out.result}" + (f" · verified by {'Paytm' if gateway == 'paytm' else 'fake gateway'} status check, txn {out.txn_id}"
                                     if out and out.result == "RECOVERED" else f" · {out.detail}" if out else "")) if out else \
            ("UNKNOWN · not counted" if c.state == "UNKNOWN" else "PENDING")
        card = {
            "input": [f"{pay.failure_code} on {pay.bank}, ₹{fmt_inr(pay.amount_paise)}",
                      f"bank: {health.get('failures_last_15_min', '?')}/{health.get('attempts_last_15_min', '?')} failed in 15 min"
                      + (" (degraded)" if health.get("degraded_now") else "") if health else "bank health: n/a",
                      f"customer: {hist.get('on_time_payments', cust.on_time_count)} on-time, {hist.get('late_payments', cust.late_count)} late, "
                      f"{len(hist.get('past_cases', []))} past cases in memory" if hist else "customer history: n/a"],
            "decision": f"{'one Paytm payment link' if dec.chosen_action == 'payment_link' else 'no action'} · send {timing} · "
                        f"{lang} template {dec.template}",
            "decided_by": dec.reasoner,
            "reason": chosen.get("why", ""),
            "evidence": json.loads(dec.evidence_json or "[]"),
            "policy": {"verdict": VERDICT.get(last.outcome, last.outcome) if last else "—", "rule": last.rule_hit if last else "",
                       "version": p.version, "checks": checks},
            "action": (f"executor sent exactly one link ({link.link_id}) under key {link.idempotency_key}" if link else
                       "nothing sent" + (f" ({c.stop_reason.replace('_', ' ')})" if c.stop_reason else "")),
            "result": result,
        }
    return {"source": src, "environment": ev.environment(case_id), "steps": steps, "card": card}


def trace_result(trace: list, tool: str) -> dict:
    for t in trace:
        if t.get("tool") == tool and isinstance(t.get("result"), dict):
            return t["result"]
    return {}


def evidence_bundle(s, case_id: str, gateway: str) -> dict:
    """Everything needed to independently check one case: decision, policy, actions, outcome and the raw
    (redacted) answers of every external system, with environments and timestamps."""
    view = build(s, case_id, gateway)
    rows = s.exec(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.id)).all()
    return {**view, "case_id": case_id,
            "evidence": [{"at": _iso(e.created_at), "kind": e.kind, "environment": e.environment, "source": e.source,
                          "ok": e.ok, "payload": json.loads(e.payload_json or "{}")} for e in rows]}
