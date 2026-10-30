"""The loop: decide -> policy -> act once -> verify -> close.

Only this module talks to the gateway, and only after an ALLOW.
Every send uses an idempotency key that is unique in the database, so a
retry, a crash or a duplicate callback can never produce a second link.
"""
import json
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from sqlmodel import select

from . import agent, detect, evidence, learning, messaging, payment_events, telegram
from .config import get_settings
from .gateway import get_gateway
from .models import (ActionRecord, Case, Customer, Decision, Message, Outcome, Payment, PolicyResult)
from .policy import PolicyContext, evaluate, load_policy
from .ports import CaseState, PayStatus, Verdict
from .templates import LANG_NAMES, fmt_inr
from .timeline import log_event

LOCK = threading.RLock()  # one writer at a time (worker + API)
MAX_SEND_ATTEMPTS = 3


@lru_cache
def policy():
    return load_policy(get_settings().policy_file)  # fail-closed: raises on a bad file


def _now():
    return datetime.now(timezone.utc)


def _utc(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def local_time():
    cfg = get_settings()
    if cfg.clock_override:
        h, m = cfg.clock_override.split(":")
        return datetime.now().replace(hour=int(h), minute=int(m)).time()
    return datetime.now(ZoneInfo(cfg.timezone)).time()


_last_check: dict[str, datetime] = {}


def _due_for_check(case_id: str, force: bool = False) -> bool:
    now = _now()
    last = _last_check.get(case_id)
    if force or last is None or (now - last).total_seconds() >= get_settings().status_poll_seconds:
        _last_check[case_id] = now
        return True
    return False


def _set_state(s, case: Case, state: CaseState, reason: str = ""):
    case.state = state.value
    if reason:
        case.stop_reason = reason
    elif state in (CaseState.SENT, CaseState.RECOVERED, CaseState.UNKNOWN):
        case.stop_reason = ""  # the earlier wait reason no longer applies
    case.updated_at = _now()
    s.add(case)


def _close(s, case: Case, result: str, detail: str, txn: str = "", amount: int = 0):
    if s.exec(select(Outcome).where(Outcome.case_id == case.id)).first():
        return
    s.add(Outcome(case_id=case.id, result=result, detail=detail, txn_id=txn, amount_paise=amount))


def key_base(case: Case) -> str:
    """Idempotency keys include when the case opened, so a re-used case id
    (after a demo reset) can never collide with an earlier send."""
    return f"{case.id}@{int(_utc(case.opened_at).timestamp())}"


def latest_decision(s, case_id: str) -> Decision | None:
    return s.exec(select(Decision).where(Decision.case_id == case_id).order_by(Decision.id.desc())).first()


def _recent_link_same_order(s, case: Case, pay: Payment, minutes: int) -> bool:
    since = _now() - timedelta(minutes=minutes)
    rows = s.exec(select(ActionRecord, Case, Payment)
                  .join(Case, Case.id == ActionRecord.case_id)
                  .join(Payment, Payment.id == Case.payment_id)
                  .where(Payment.order_id == pay.order_id, ActionRecord.kind == "payment_link",
                         ActionRecord.state == "SENT", Case.id != case.id)).all()
    return any(_utc(a.sent_at) and _utc(a.sent_at) >= since for a, _, _ in rows)


def check_policy(s, case: Case, dec: Decision, *, owner_approved=False, is_reminder=False):
    pay = s.get(Payment, case.payment_id)
    cust = s.get(Customer, pay.customer_id)
    p = policy()
    ctx = PolicyContext(action=dec.chosen_action, amount_paise=pay.amount_paise, confidence=dec.confidence,
                        opted_out=cust.opted_out, reminders_sent=max(case.messages_sent - 1, 0),
                        is_reminder=is_reminder,
                        recent_open_link_same_order=_recent_link_same_order(s, case, pay, p.duplicate_window_minutes),
                        local_time=local_time(), vip=cust.vip, owner_approved=owner_approved)
    pd = evaluate(p, ctx)
    s.add(PolicyResult(case_id=case.id, decision_id=dec.id, outcome=pd.verdict.value,
                       rule_hit=pd.rule, policy_version=pd.version))
    return pd


# ---------------------------------------------------------------- deciding
def pending_bundles(s) -> list:
    """Bundles for new live cases, built without the lock so the slow model calls can run outside it."""
    q = select(Case).where(Case.state == CaseState.NEW.value, Case.group == "TREATED")
    return [agent.build_bundle(s, c) for c in s.exec(q).all() if not c.id.startswith("eval-")]


def think(bundles: list) -> dict:
    """Run the agent for many cases in parallel (network only; touches no database)."""
    if not bundles:
        return {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, min(get_settings().llm_parallel, len(bundles)))) as ex:
        return dict(zip((b.case_id for b in bundles), ex.map(agent.decide, bundles)))


def decide_case(s, case: Case, pre=None) -> Decision:
    b = agent.build_bundle(s, case)
    ad = pre or agent.decide(b)
    o = ad.out
    arm = "now"  # live: timing comes from the agent + policy, deterministically. Never randomised.
    if learning.is_research(case.batch) and get_settings().learning and o.chosen.action == "payment_link":
        arm, _ = learning.choose_arm(s, o.diagnosis, batch=case.batch)  # simulated customers only
    dec = Decision(case_id=case.id, diagnosis=o.diagnosis, evidence_json=json.dumps(o.evidence, ensure_ascii=False),
                   options_json=json.dumps([x.model_dump() for x in o.options], ensure_ascii=False),
                   chosen_action=o.chosen.action, send_after=o.chosen.send_after, language=b.language,
                   template=o.chosen.template, confidence=o.confidence, reasoner=ad.reasoner, timing_arm=arm,
                   trace_json=json.dumps(ad.trace, ensure_ascii=False, default=str)[:8000],
                   raw_output=(ad.raw or "")[:4000])
    s.add(dec)
    s.flush()
    case.diagnosis, case.confidence = o.diagnosis, o.confidence
    _set_state(s, case, CaseState.DECIDED)
    chosen_why = next((x.why for x in o.options if x.verdict == "chosen"), "")
    log_event(s, "decision", f"{b.customer_name}: {o.diagnosis.replace('_', '-')}, {chosen_why}", case.id)
    if not ad.valid:
        log_event(s, "agent", f"Agent output invalid ({ad.error[:80]}); owner will decide", case.id)
    return dec


def route(s, case: Case, dec: Decision, pd):
    name = _cust(s, case).name
    if pd.verdict == Verdict.BLOCK:
        _set_state(s, case, CaseState.BLOCKED, pd.rule)
        _close(s, case, "BLOCKED", pd.reason)
        log_event(s, "policy", f"BLOCK {name}: {pd.reason}", case.id)
    elif pd.verdict == Verdict.ASK_OWNER:
        _set_state(s, case, CaseState.WAITING_OWNER, pd.rule)
        log_event(s, "policy", f"ASK OWNER {name}: {pd.reason}", case.id)
        if not case.id.startswith("eval-"):
            pay = s.get(Payment, case.payment_id)
            cust = _cust(s, case)
            p = policy()
            lang = LANG_NAMES.get(cust.language, cust.language)
            risk = {"owner_amount": f"₹{fmt_inr(pay.amount_paise)} is above your ₹{fmt_inr(p.auto_max_amount_paise)} auto limit",
                    "owner_confidence": f"Wapas is only {dec.confidence:.0%} sure of the cause (floor {p.min_confidence:.0%})",
                    "owner_vip": "A loyal customer: a wrong message costs more than the payment"}.get(pd.rule, pd.reason)
            telegram.owner_request(case.id, dec.id, customer=name, amount_fmt=fmt_inr(pay.amount_paise), why=pd.reason,
                                   proposal=(f"one Paytm link in {lang}, sent once; at most {p.max_reminders} reminders "
                                             f"with the same link; then stop"), risk=risk)
    elif pd.verdict == Verdict.HOLD:
        if not (case.state == CaseState.SCHEDULED.value and case.stop_reason == pd.rule):
            log_event(s, "policy", f"HOLD {name}: {pd.reason}", case.id)
        _set_state(s, case, CaseState.SCHEDULED, pd.rule)
    else:
        if dec.chosen_action == "no_action":
            _set_state(s, case, CaseState.STOPPED, "agent_no_action")
            _close(s, case, "STOPPED", "Agent chose no action")
            return
        pay = s.get(Payment, case.payment_id)
        if detect.is_degraded(s, pay.bank):  # guard: never send into a live outage, whatever the agent said
            if case.stop_reason != "waiting_bank_recovery":
                log_event(s, "policy", f"ALLOW {name}: link queued until {pay.bank} recovers" if dec.send_after == "bank_recovered"
                          else f"GUARD {name}: agent said send {dec.send_after}, but {pay.bank} is still failing; queued", case.id)
            _set_state(s, case, CaseState.SCHEDULED, "waiting_bank_recovery")
        elif dec.timing_arm == "wait" and case.send_not_before is None:  # research batches only
            wait = get_settings().wait_arm_seconds
            case.send_not_before = _now() + timedelta(seconds=wait)
            _set_state(s, case, CaseState.SCHEDULED, "learning_wait")
            log_event(s, "learn", f"ALLOW {name}: research arm 'wait' ({wait}s) before the first message", case.id)
        elif dec.send_after == "later" and case.send_not_before is None and not learning.is_research(case.batch):
            # the agent's own judgment, deterministic (in research batches the timing arm alone decides)
            wait = get_settings().agent_delay_seconds
            case.send_not_before = _now() + timedelta(seconds=wait)
            _set_state(s, case, CaseState.SCHEDULED, "agent_later")
            log_event(s, "policy", f"ALLOW {name}: the agent recommended waiting {_dur(wait)} before the first message; "
                                   "policy allows it", case.id)
        else:
            log_event(s, "policy", f"ALLOW {name}: {pd.reason}", case.id)
            send_link(s, case, dec)


def _dur(sec: int) -> str:
    return f"{sec // 60} min" if sec >= 120 else f"{sec} s"


def _cust(s, case) -> Customer:
    return s.get(Customer, s.get(Payment, case.payment_id).customer_id)


# ---------------------------------------------------------------- acting
def send_link(s, case: Case, dec: Decision):
    key = f"{key_base(case)}:link"
    rec = s.exec(select(ActionRecord).where(ActionRecord.idempotency_key == key)).first()
    if rec and rec.state == "SENT":
        return  # already done; never twice
    if rec is None:
        rec = ActionRecord(case_id=case.id, kind="payment_link", idempotency_key=key)
        s.add(rec)
        s.flush()
    pay = s.get(Payment, case.payment_id)
    cust = s.get(Customer, pay.customer_id)
    cfg = get_settings()
    res = get_gateway().create_link(idempotency_key=key, amount_paise=pay.amount_paise, customer_name=cust.name,
                                    customer_phone=cust.phone, description=f"Order {pay.order_id}",
                                    callback_url=cfg.public_base_url.rstrip("/") + "/api/paytm/callback")
    evidence.record(s, "link_created" if res.ok else "link_create_failed",
                    {"idempotency_key": key, "ok": res.ok, "link_id": res.link_id, "short_url": res.short_url,
                     "error": res.error, "amount_paise": pay.amount_paise, "gateway": get_gateway().name},
                    case_id=case.id, source="paytm:/link/create" if get_gateway().name == "paytm" else "fake-gateway",
                    ok=res.ok)
    if not res.ok:
        rec.error = res.error[:300]
        rec.state = "FAILED"
        rec.attempt_no += 1
        if rec.attempt_no > MAX_SEND_ATTEMPTS:
            _set_state(s, case, CaseState.STOPPED, "gateway_unavailable")
            _close(s, case, "STOPPED", f"Paytm link could not be created: {rec.error}")
            log_event(s, "error", f"Gave up on {cust.name}: gateway unavailable, nothing was sent", case.id)
        else:
            _set_state(s, case, CaseState.SCHEDULED, "gateway_retry")
            log_event(s, "error", f"Paytm error for {cust.name} ({rec.error[:60]}); paused, will retry once safe", case.id)
        s.add(rec)
        return
    rec.state, rec.link_id, rec.short_url, rec.sent_at, rec.error = "SENT", res.link_id, res.short_url, _now(), ""
    s.add(rec)
    _recovery_payment_attempt(s, case, pay, rec, get_gateway().name)
    messaging.send(s, case_id=case.id, customer=cust, template=dec.template, amount_paise=pay.amount_paise,
                   link=res.short_url)
    case.messages_sent += 1
    _set_state(s, case, CaseState.SENT)
    log_event(s, "action", f"Sent one Paytm link to {cust.name} (₹{fmt_inr(pay.amount_paise)}, {cust.language})", case.id)


def link_of(s, case_id: str) -> ActionRecord | None:
    return s.exec(select(ActionRecord).where(ActionRecord.case_id == case_id, ActionRecord.kind == "payment_link",
                                             ActionRecord.state == "SENT")).first()


def _recovery_payment_attempt(s, case: Case, original: Payment, rec: ActionRecord, provider: str) -> Payment:
    """Persist the actual follow-up collection attempt separately from the original failed charge."""
    payment_id = "paylink_" + hashlib.sha256(rec.idempotency_key.encode("utf-8")).hexdigest()[:32]
    attempt = s.get(Payment, payment_id)
    if attempt is None:
        attempt = Payment(
            id=payment_id, merchant_id=original.merchant_id, store_id=original.store_id,
            order_id=f"{original.order_id}:recovery:{rec.attempt_no}", customer_id=original.customer_id,
            amount_paise=original.amount_paise, currency=original.currency,
            source_type="RECOVERY", source_id=case.id, provider=provider,
            provider_mid=get_settings().paytm_mid if provider == "paytm" else "",
            provider_link_id=rec.link_id, provider_link_url=rec.short_url,
            idempotency_key=rec.idempotency_key,
            bank=original.bank, method="PAYMENT_LINK", status="PENDING",
        )
    else:
        attempt.provider_link_id = rec.link_id
        attempt.provider_link_url = rec.short_url
        attempt.status = "PENDING" if attempt.status in {"INIT_UNKNOWN", "INIT_FAILED"} else attempt.status
    s.add(attempt)
    s.flush()
    return attempt


# ---------------------------------------------------------------- verifying
_last_evidenced: dict[str, str] = {}


def verify(s, case: Case, source: str = "poll") -> str:
    """Only Paytm's own status answer can credit a recovery, and only for the exact amount owed."""
    rec = link_of(s, case.id)
    if not rec:
        return "no-link"
    gw = get_gateway()
    st = gw.link_status(rec.link_id)
    cust = _cust(s, case)
    pay = s.get(Payment, case.payment_id)
    link_payment = s.exec(select(Payment).where(
        Payment.merchant_id == pay.merchant_id, Payment.store_id == pay.store_id,
        Payment.provider_link_id == rec.link_id, Payment.source_type == "RECOVERY",
        Payment.source_id == case.id,
    )).first()
    if link_payment is None:
        link_payment = _recovery_payment_attempt(s, case, pay, rec, gw.name)
    src = "paytm:/link/fetchTransaction + /v3/order/status" if gw.name == "paytm" else "fake-gateway"
    if _last_evidenced.get(case.id) != st.status.value or st.status == PayStatus.SUCCESS:
        _last_evidenced[case.id] = st.status.value
        evidence.record(s, "status_check", {"link_id": rec.link_id, "mapped_status": st.status.value, "txn_id": st.txn_id,
                                            "amount_paise": st.amount_paise, "expected_paise": pay.amount_paise,
                                            "trigger": source, "raw": st.raw},
                        case_id=case.id, source=src, ok=st.status not in (PayStatus.ERROR,))
    if st.status == PayStatus.SUCCESS:
        if case.state == CaseState.RECOVERED.value:
            return "already"
        if st.amount_paise != pay.amount_paise:  # missing (0) counts as unconfirmed, never as "matches"
            if case.stop_reason != "amount_mismatch":
                _set_state(s, case, CaseState.UNKNOWN, "amount_mismatch")
                reported = f"₹{fmt_inr(st.amount_paise)}" if st.amount_paise else "no amount"
                msg = (f"Paytm reports {reported} for {cust.name}, but ₹{fmt_inr(pay.amount_paise)} is owed: "
                       "NOT credited, no thank-you sent, owner informed")
                log_event(s, "verify", msg, case.id)
                if not case.id.startswith("eval-"):
                    telegram.owner_note(f"Check needed: {msg}. Txn {st.txn_id}.")
            return "mismatch"
        if not payment_events.record_verified_success(
                s, link_payment, st, gateway_name=gw.name, expected_link_id=rec.link_id):
            _set_state(s, case, CaseState.UNKNOWN)
            log_event(s, "verify", "Paytm success could not be bound to this link, merchant, order, and amount; NOT credited",
                      case.id)
            return "unknown"
        amount = pay.amount_paise
        late = case.state == CaseState.STOPPED.value
        _set_state(s, case, CaseState.RECOVERED)
        detail = f"Confirmed by {gw.name} status check ({source})" + ("; paid after follow-ups had stopped" if late else "")
        out = s.exec(select(Outcome).where(Outcome.case_id == case.id)).first()
        if out is not None and out.result == "STOPPED":  # money arrived after we stopped: the truth wins
            out.result, out.detail, out.txn_id, out.amount_paise, out.verified_at = "RECOVERED", detail, st.txn_id, amount, _now()
            s.add(out)
        else:
            _close(s, case, "RECOVERED", detail, st.txn_id, amount)
        messaging.send(s, case_id=case.id, customer=cust, template="thanks_v1", amount_paise=amount)
        log_event(s, "verify", f"Paytm confirmed {cust.name} paid ₹{fmt_inr(amount)} (txn {st.txn_id})", case.id)
        if not case.id.startswith("eval-"):
            env = evidence.environment(case.id)
            telegram.owner_note(f"Recovered ₹{fmt_inr(amount)} from {cust.name} (txn {st.txn_id}). "
                                f"Confirmed by {gw.name} status check [{env}].")
        return "recovered"
    if st.status in (PayStatus.ERROR, PayStatus.NOT_FOUND):
        if case.state != CaseState.UNKNOWN.value:
            _set_state(s, case, CaseState.UNKNOWN)
            log_event(s, "verify", f"Status check failed for {cust.name}; marked UNKNOWN, not counted", case.id)
        return "unknown"
    if case.state == CaseState.UNKNOWN.value and case.stop_reason != "amount_mismatch":
        _set_state(s, case, CaseState.SENT)
        log_event(s, "verify", f"Status check back for {cust.name}: still unpaid", case.id)
    return "pending"


REPLY_HOLDS = ("customer_says_paid", "customer_debited", "customer_later", "customer_other_method")


def maybe_remind(s, case: Case):
    if case.stop_reason in REPLY_HOLDS:  # the customer told us something; do not nag over it
        if case.stop_reason != "customer_later" or not case.send_not_before or _now() < _utc(case.send_not_before):
            return
        case.stop_reason, case.send_not_before = "", None  # their "later" has arrived: normal reminders resume
        s.add(case)
    rec = link_of(s, case.id)
    last = s.exec(select(Message).where(Message.case_id == case.id, Message.direction == "out")
                  .order_by(Message.id.desc())).first()
    if not rec or not last:
        return
    if _now() - _utc(last.created_at) < timedelta(seconds=get_settings().reminder_after_seconds):
        return
    dec = latest_decision(s, case.id)
    pd = check_policy(s, case, dec, owner_approved=True, is_reminder=True)
    cust = _cust(s, case)
    if pd.verdict == Verdict.ALLOW:
        n = case.messages_sent
        key = f"{key_base(case)}:reminder:{n}"
        if s.exec(select(ActionRecord).where(ActionRecord.idempotency_key == key)).first():
            return
        s.add(ActionRecord(case_id=case.id, kind="reminder", idempotency_key=key, link_id=rec.link_id,
                           short_url=rec.short_url, state="SENT", sent_at=_now()))
        pay = s.get(Payment, case.payment_id)
        messaging.send(s, case_id=case.id, customer=cust, template="reminder_v1", amount_paise=pay.amount_paise,
                       link=rec.short_url)
        case.messages_sent += 1
        s.add(case)
        log_event(s, "action", f"Reminder {n} to {cust.name} (same link)", case.id)
    elif pd.verdict == Verdict.BLOCK:
        _set_state(s, case, CaseState.STOPPED, pd.rule)
        _close(s, case, "STOPPED", pd.reason)
        log_event(s, "policy", f"STOP {cust.name}: {pd.reason}", case.id)


# ---------------------------------------------------------------- owner + customer
def owner_approve(s, case_id: str, via: str = "console") -> str:
    case = s.get(Case, case_id)
    if not case or case.state != CaseState.WAITING_OWNER.value:
        return "not-waiting"
    dec = latest_decision(s, case_id)
    case.owner_approved = True
    log_event(s, "owner", f"Owner approved {_cust(s, case).name} ({via})", case_id)
    evidence.record(s, "owner_approved", {"via": via, "decision_id": dec.id}, case_id=case_id, source=f"owner-{via.lower()}")
    pd = check_policy(s, case, dec, owner_approved=True)
    route(s, case, dec, pd)
    return case.state


def owner_skip(s, case_id: str, via: str = "console") -> str:
    case = s.get(Case, case_id)
    if not case or case.state != CaseState.WAITING_OWNER.value:
        return "not-waiting"
    _set_state(s, case, CaseState.STOPPED, "owner_skipped")
    _close(s, case, "STOPPED", "Owner chose to skip")
    log_event(s, "owner", f"Owner skipped {_cust(s, case).name} ({via})", case_id)
    evidence.record(s, "owner_skipped", {"via": via}, case_id=case_id, source=f"owner-{via.lower()}")
    return case.state


def expire_approvals(s) -> int:
    """An unanswered approval request closes with no customer contact (the safe default)."""
    ttl = timedelta(hours=get_settings().approval_ttl_hours)
    n = 0
    for case in s.exec(select(Case).where(Case.state == CaseState.WAITING_OWNER.value, Case.batch == "live")).all():
        if _now() - _utc(case.updated_at) >= ttl:
            _set_state(s, case, CaseState.STOPPED, "owner_timeout")
            _close(s, case, "STOPPED", "Owner did not answer in time; nobody was contacted")
            log_event(s, "owner", f"No owner answer for {_cust(s, case).name}; closed without contacting anyone", case.id)
            n += 1
    return n


def handle_reply(s, case_id: str, text: str, *, via: str = "console", stt: dict | None = None) -> dict:
    """A customer's free-text/voice reply to our message. The model classifies it into a closed set; the
    actions are bounded and reversible, and none moves money or writes to the customer."""
    from . import replies
    case = s.get(Case, case_id)
    if not case:
        return {"error": "unknown case"}
    cust = _cust(s, case)
    text = replies.clean(text)
    if text.upper().startswith("STOP"):
        return {"intent": "opt_out", "stopped": customer_stop(s, cust.id)}
    out, reasoner, raw = replies.classify(text)
    s.add(Message(case_id=case.id, customer_id=cust.id, direction="in", language=cust.language, text=text,
                  channel="telegram-demo-customer" if via == "telegram" else "console-demo"))
    said = f"“{out.quote or text[:60]}”"
    action = "no change"
    open_link = case.state in (CaseState.SENT.value, CaseState.UNKNOWN.value) and link_of(s, case.id) is not None
    if out.intent in ("already_paid", "debited_no_order"):
        result = verify(s, case, source="customer says paid") if open_link else "no-link"
        if result == "recovered":
            action = "Paytm confirms the payment: recovered"
        else:
            if case.state == CaseState.SENT.value:
                case.stop_reason = "customer_says_paid" if out.intent == "already_paid" else "customer_debited"
                s.add(case)
            action = "Paytm does not show it yet: reminders paused, owner told"
            telegram.owner_note(f"{cust.name} replied {said} ({out.intent.replace('_', ' ')}), but Paytm does not show the payment "
                                f"for ₹{fmt_inr(s.get(Payment, case.payment_id).amount_paise)}. Reminders paused. "
                                + ("Check for a debit without an order; do not ask them to pay twice." if out.intent == "debited_no_order" else ""))
    elif out.intent == "pay_later" and case.state == CaseState.SENT.value:
        hours = min(out.when_hours or 24.0, 72.0)  # never hold longer than Paytm keeps a link open for us
        case.stop_reason, case.send_not_before = "customer_later", _now() + timedelta(hours=hours)
        s.add(case)
        action = f"reminders held for {hours:g} h, then resume"
    elif out.intent == "other_method" and case.state == CaseState.SENT.value:
        case.stop_reason = "customer_other_method"
        s.add(case)
        action = "reminders paused; owner told to confirm the other payment by hand"
        telegram.owner_note(f"{cust.name} replied {said}: wants to pay another way. Reminders paused; confirm by hand.")
    elif out.intent == "refuse" and case.state in (CaseState.SENT.value, CaseState.SCHEDULED.value, CaseState.UNKNOWN.value):
        _set_state(s, case, CaseState.STOPPED, "customer_declined")
        _close(s, case, "STOPPED", "Customer declined in their reply")
        action = "follow-ups stopped for this payment"
    elif out.intent == "unclear":
        telegram.owner_note(f"{cust.name} replied {said}; Wapas could not tell what they mean. Nothing changed.")
        action = "owner told; nothing changed"
    evidence.record(s, "customer_reply", {"text": text, "intent": out.intent, "when_hours": out.when_hours, "quote": out.quote,
                                          "confidence": out.confidence, "reasoner": reasoner, "via": via, "stt": stt or None,
                                          "action": action, "raw": raw[:500]},
                    case_id=case.id, source=reasoner)
    log_event(s, "customer", f"{cust.name} replied {said} → {out.intent.replace('_', ' ')} ({reasoner}); {action}", case.id)
    return {"intent": out.intent, "when_hours": out.when_hours, "quote": out.quote, "confidence": out.confidence,
            "reasoner": reasoner, "action": action}


def customer_stop(s, customer_id: str) -> int:
    cust = s.get(Customer, customer_id)
    if not cust:
        return 0
    cust.opted_out = True
    s.add(cust)
    stopped = 0
    cases = s.exec(select(Case).join(Payment, Payment.id == Case.payment_id)
                   .where(Payment.customer_id == customer_id)).all()
    for c in cases:
        if c.state in (CaseState.SENT.value, CaseState.SCHEDULED.value, CaseState.WAITING_OWNER.value,
                       CaseState.UNKNOWN.value, CaseState.NEW.value, CaseState.DECIDED.value):
            s.add(Message(case_id=c.id, customer_id=customer_id, direction="in", language=cust.language, text="STOP"))
            _set_state(s, c, CaseState.STOPPED, "opted_out")
            _close(s, c, "STOPPED", "Customer replied STOP")
            stopped += 1
    log_event(s, "customer", f"{cust.name} replied STOP; no further contact")
    return stopped


def _quiet_now() -> bool:
    from .policy import _in_quiet_hours
    p = policy()
    return _in_quiet_hours(local_time(), p.quiet_start, p.quiet_end)


# ---------------------------------------------------------------- the loop
def tick(s, pre: dict | None = None) -> dict:
    """One pass of the loop. `pre` holds agent decisions already made outside the lock (see think)."""
    stats = {"decided": 0, "sent": 0, "verified": 0}
    pre = pre or {}
    for case in s.exec(select(Case).where(Case.state == CaseState.NEW.value, Case.group == "TREATED")).all():
        dec = decide_case(s, case, pre.get(case.id))
        route(s, case, dec, check_policy(s, case, dec))
        stats["decided"] += 1
    for case in s.exec(select(Case).where(Case.state == CaseState.SCHEDULED.value)).all():
        dec = latest_decision(s, case.id)
        pay = s.get(Payment, case.payment_id)
        if case.stop_reason == "waiting_bank_recovery" and detect.is_degraded(s, pay.bank):
            continue
        if case.stop_reason == "quiet_hours" and _quiet_now():
            continue
        if case.stop_reason in ("learning_wait", "agent_later") and case.send_not_before and _now() < _utc(case.send_not_before):
            continue
        if case.stop_reason == "gateway_retry":
            send_link(s, case, dec)
        else:
            route(s, case, dec, check_policy(s, case, dec, owner_approved=case.owner_approved))
        stats["sent"] += 1
    for case in s.exec(select(Case).where(Case.state.in_([CaseState.SENT.value, CaseState.UNKNOWN.value]),
                                          Case.batch != "earlier")).all():
        if not _due_for_check(case.id):
            continue
        r = verify(s, case)
        if r == "pending" and case.state == CaseState.SENT.value:
            maybe_remind(s, case)
        stats["verified"] += 1
    expire_approvals(s)
    s.commit()
    return stats
