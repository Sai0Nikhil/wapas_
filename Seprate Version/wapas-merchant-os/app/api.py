"""HTTP API for the owner app, demo controls and Paytm callbacks."""
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlmodel import select

from . import detect, doctor, evaluate, evidence, executor, health, jobview, learning, seed, telegram, voice
from .config import get_settings
from .db import session
from .gateway import get_gateway
from .models import (ActionRecord, Case, Customer, Decision, Event, Evidence, Message, Outcome, Payment, PolicyResult)
from .ports import CaseState
from .templates import LANG_NAMES, fmt_inr
from .timeline import log_event

router = APIRouter()


def _iso(dt):
    return dt.isoformat() if dt else None


def _case_row(s, c: Case) -> dict:
    p = s.get(Payment, c.payment_id)
    cu = s.get(Customer, p.customer_id)
    return {"id": c.id, "name": cu.name, "customer_id": cu.id, "language": cu.language,
            "language_name": LANG_NAMES.get(cu.language, cu.language), "amount": p.amount_paise / 100,
            "amount_fmt": fmt_inr(p.amount_paise), "order_id": p.order_id, "bank": p.bank,
            "failure_code": p.failure_code, "state": c.state, "reason": c.stop_reason,
            "diagnosis": c.diagnosis, "confidence": c.confidence, "messages_sent": c.messages_sent,
            "opened_at": _iso(c.opened_at), "source": jobview.source_of(p, get_gateway().name)["kind"]}


@router.get("/api/state")
def state():
    cfg = get_settings()
    with session() as s:
        live = s.exec(select(Case).where(Case.batch == "live").order_by(Case.opened_at)).all()
        ids = [c.id for c in live]
        outs = s.exec(select(Outcome).where(Outcome.case_id.in_(ids))).all() if ids else []
        rec = [o for o in outs if o.result == "RECOVERED"]
        contacted = {a.case_id for a in s.exec(select(ActionRecord).where(ActionRecord.case_id.in_(ids),
                                                                          ActionRecord.state == "SENT")).all()} if ids else set()
        counts = {
            "flagged": len(live),
            "contacted": len(contacted),
            "paid": len(rec),
            "waiting_owner": sum(1 for c in live if c.state == CaseState.WAITING_OWNER.value),
            "stopped_by_policy": sum(1 for c in live if c.state in (CaseState.BLOCKED.value, CaseState.STOPPED.value)),
            "unknown": sum(1 for c in live if c.state == CaseState.UNKNOWN.value),
            "recovered_inr": sum(o.amount_paise for o in rec) / 100,
            "recovered_fmt": fmt_inr(sum(o.amount_paise for o in rec)),
        }
        msgs = s.exec(select(Message).where(Message.case_id.in_(ids)).order_by(Message.id.desc()).limit(40)).all() if ids else []
        events = s.exec(select(Event).order_by(Event.id.desc()).limit(60)).all()
        health = detect.bank_health(s, "Bank A")
        names = {c["customer_id"]: c["name"] for c in (_case_row(s, x) for x in live)}
        gw = get_gateway()
        return {
            "merchant": cfg.merchant_name, "gateway": gw.name, "llm": cfg.llm_enabled, "llm_model": cfg.llm_model,
            "sarvam": cfg.sarvam_enabled, "telegram": cfg.telegram_enabled, "counts": counts,
            "environment": evidence.environment(), "policy_version": executor.policy().version,
            "cases": [_case_row(s, c) for c in live],
            "messages": [{"id": m.id, "case_id": m.case_id, "name": names.get(m.customer_id, m.customer_id),
                          "direction": m.direction, "language": m.language, "text": m.text, "channel": m.channel,
                          "at": _iso(m.created_at)} for m in msgs],
            "events": [{"id": e.id, "case_id": e.case_id, "kind": e.kind, "text": e.text, "at": _iso(e.created_at)} for e in events],
            "bank": {"name": health.bank, "degraded": health.degraded, "recent_failures": health.recent_failures,
                     "recent_attempts": health.recent_attempts, "baseline": health.baseline_rate},
            "faults": {"status_timeout": getattr(gw, "fail_status_calls", False),
                       "gateway_down": getattr(gw, "fail_create_calls", False)},
        }


@router.get("/api/integrations")
def integrations(deep: bool = False):
    return doctor.run_all(deep=deep)


def _doctor_status(name: str) -> tuple[str, str] | None:
    for r in doctor.LAST.get("results") or []:
        if r["name"] == name:
            return r["status"], r["summary"]
    return None


@router.get("/api/proof")
def proof():
    """Trust panel. Every line says VERIFIED only if something real answered; fake stays SIMULATED."""
    cfg = get_settings()
    gw = get_gateway()
    env = evidence.environment()
    items = []
    last_check = doctor.LAST.get("at")

    def item(name, status, detail):
        items.append({"name": name, "status": status, "detail": detail})

    if gw.name != "paytm":
        item("Paytm", "SIMULATED", "Fake gateway: no call reaches Paytm. Set GATEWAY=paytm with test keys.")
    else:
        d = _doctor_status("Paytm")
        item("Paytm", d[0] if d else "UNVERIFIED", d[1] if d else "Configured; press Check live")
    for nm, enabled, off in (("LLM", cfg.llm_enabled, "Rule reasoner only"),
                             ("Sarvam voice", cfg.sarvam_enabled, "Text answers; browser speech")):
        d = _doctor_status(nm)
        item(nm, (d[0] if d else "UNVERIFIED") if enabled else "NOT CONFIGURED", (d[1] if d else "Configured; press Check live") if enabled else off)
    if not cfg.telegram_bot_token:
        item("Owner channel", "NOT CONFIGURED", "Telegram off; approvals in this console only")
    else:
        st = telegram.STATUS
        status = "VERIFIED" if st.get("last_ok") else ("DEGRADED" if st.get("last_error") else "UNVERIFIED")
        item("Owner channel", status, f"Telegram (not WhatsApp) · last delivered {st.get('last_ok') or 'never'}"
             + (f" · last error: {st['last_error']}" if st.get("last_error") else ""))
    w = doctor.check_worker()
    item("Worker", w["status"], "; ".join(c["detail"] for c in w["checks"])[:200])
    with session() as s:
        # Only a CREDITED recovery counts: Outcome RECOVERED (exact amount), backed by a status-check record.
        last_rec = s.exec(select(Outcome).join(Case, Case.id == Outcome.case_id)
                          .where(Case.batch == "live", Outcome.result == "RECOVERED").order_by(Outcome.verified_at.desc())).first()
        ev_row = s.exec(select(Evidence).where(Evidence.case_id == last_rec.case_id, Evidence.kind == "status_check")
                        .order_by(Evidence.id.desc())).first() if last_rec else None
        if last_rec and ev_row:
            live_env = ev_row.environment.startswith("paytm")
            item("Latest verification", "VERIFIED" if live_env else "SIMULATED",
                 f"case {last_rec.case_id} · ₹{fmt_inr(last_rec.amount_paise)} · txn {last_rec.txn_id} · "
                 f"{ev_row.environment} · {ev_row.source} · {last_rec.verified_at:%H:%M:%S} UTC")
        else:
            item("Latest verification", "UNVERIFIED", "No payment confirmed and credited yet")
        auto = s.exec(select(Case).join(Outcome, Outcome.case_id == Case.id)
                      .where(Case.batch == "live", Outcome.result == "RECOVERED", Case.owner_approved == False)  # noqa: E712
                      .order_by(Outcome.verified_at.desc())).first()
        if auto:
            item("Last autonomous job", "VERIFIED" if env.startswith("paytm") else "SIMULATED",
                 f"{auto.id}: signal → decision → policy AUTO → link → payment verified, no human step ({env})")
        else:
            item("Last autonomous job", "UNVERIFIED", "No case has gone signal → verified payment without a human yet")
    p = executor.policy()
    item("Policy", "VERIFIED", f"version {p.version} loaded fail-closed · auto limit ₹{fmt_inr(p.auto_max_amount_paise)} · "
                               f"confidence floor {p.min_confidence:.0%} · refunds never automatic")
    item("Learning", "VERIFIED", "Live: passive evidence only (no exploration, enforced in code and tests). "
                                 "Research batches: experiments on simulated customers only.")
    return {"environment": env, "doctor_at": last_check, "items": items}


@router.get("/api/learning")
def learning_state():
    with session() as s:
        last = evaluate.latest(s)
        return {"live": learning.live_evidence(s),
                "eval": learning.research_summary(s, last["batch"]) if last else None,
                "eval_batch": last["batch"] if last else None,
                "true_lift": last.get("true_lift") if last else None}


@router.get("/api/cases/{case_id}")
def case_detail(case_id: str):
    with session() as s:
        c = s.get(Case, case_id)
        if not c:
            raise HTTPException(404)
        row = _case_row(s, c)
        cu = s.get(Customer, row["customer_id"])
        dec = executor.latest_decision(s, case_id)
        prs = s.exec(select(PolicyResult).where(PolicyResult.case_id == case_id).order_by(PolicyResult.id)).all()
        acts = s.exec(select(ActionRecord).where(ActionRecord.case_id == case_id).order_by(ActionRecord.id)).all()
        out = s.exec(select(Outcome).where(Outcome.case_id == case_id)).first()
        msgs = s.exec(select(Message).where(Message.case_id == case_id).order_by(Message.id)).all()
        evs = s.exec(select(Event).where(Event.case_id == case_id).order_by(Event.id)).all()
        row.update({
            "history": {"on_time": cu.on_time_count, "late": cu.late_count, "vip": cu.vip, "opted_out": cu.opted_out},
            "decision": None if not dec else {
                "diagnosis": dec.diagnosis, "evidence": json.loads(dec.evidence_json),
                "options": json.loads(dec.options_json), "chosen_action": dec.chosen_action,
                "send_after": dec.send_after, "template": dec.template, "language": dec.language,
                "confidence": dec.confidence, "reasoner": dec.reasoner, "raw_output": dec.raw_output,
                "timing_arm": dec.timing_arm, "trace": json.loads(dec.trace_json or "[]")},
            "policy": [{"outcome": p.outcome, "rule": p.rule_hit, "version": p.policy_version, "at": _iso(p.created_at)} for p in prs],
            "actions": [{"kind": a.kind, "key": a.idempotency_key, "link_id": a.link_id, "url": a.short_url,
                         "state": a.state, "error": a.error, "sent_at": _iso(a.sent_at)} for a in acts],
            "outcome": None if not out else {"result": out.result, "txn_id": out.txn_id,
                                             "amount": out.amount_paise / 100, "detail": out.detail},
            "messages": [{"direction": m.direction, "language": m.language, "text": m.text, "at": _iso(m.created_at)} for m in msgs],
            "timeline": [{"kind": e.kind, "text": e.text, "at": _iso(e.created_at)} for e in evs],
            "job": jobview.build(s, case_id, get_gateway().name),
        })
        return row


@router.get("/api/cases/{case_id}/evidence")
def case_evidence(case_id: str):
    with session() as s:
        if not s.get(Case, case_id):
            raise HTTPException(404)
        return jobview.evidence_bundle(s, case_id, get_gateway().name)


# ------------------------------------------------------------------ owner
@router.post("/api/owner/approve/{case_id}")
def approve(case_id: str):
    with executor.LOCK, session() as s:
        r = executor.owner_approve(s, case_id)
        s.commit()
        return {"state": r}


@router.post("/api/owner/skip/{case_id}")
def skip(case_id: str):
    with executor.LOCK, session() as s:
        r = executor.owner_skip(s, case_id)
        s.commit()
        return {"state": r}


class VoiceIn(BaseModel):
    text: str = ""
    audio_b64: str = ""
    mime: str = ""


@router.post("/api/voice/ask")
def voice_ask(body: VoiceIn):
    with session() as s:
        return voice.ask(s, body.text, body.audio_b64, body.mime)


# ------------------------------------------------------------------ Paytm callback
@router.post("/api/paytm/callback")
async def paytm_callback(request: Request):
    ctype = request.headers.get("content-type", "")
    if "json" in ctype:
        data = await request.json()
        payload = data.get("body", data) if isinstance(data, dict) else {}
    else:
        payload = dict(await request.form())
    gw = get_gateway()
    if not gw.verify_callback(dict(payload)):
        with executor.LOCK, session() as s:
            log_event(s, "security", "Rejected a callback with an invalid checksum")
            s.commit()
        raise HTTPException(status_code=400, detail="invalid checksum")
    # Paytm's link webhook identifies the link by MERC_UNQ_REF ("LI_<id>") and echoes our LINKNOTES ("wapas:<key>").
    notes = str(payload.get("LINKNOTES") or "")
    key = notes.split("wapas:", 1)[1].strip() if notes.startswith("wapas:") else ""
    ref = str(payload.get("MERC_UNQ_REF") or payload.get("LINKID") or payload.get("linkId") or "")
    link_id = ref[3:] if ref.upper().startswith("LI_") else ref
    with executor.LOCK, session() as s:
        q = select(ActionRecord).where(ActionRecord.kind == "payment_link", ActionRecord.state == "SENT")
        if key:
            q = q.where(ActionRecord.idempotency_key == key)
        elif link_id:
            q = q.where(ActionRecord.link_id == link_id)
        else:
            q = q.where(ActionRecord.id == -1)  # cannot tell which link: verify nothing (the poller still will)
        recs = s.exec(q).all()
        evidence.record(s, "link_callback", {k: v for k, v in payload.items() if k != "CHECKSUMHASH"} |
                        {"checksum_valid": True, "matched_cases": [r.case_id for r in recs]},
                        case_id=recs[0].case_id if len(recs) == 1 else "", source="paytm:link webhook")
        results = []
        for rec in recs:
            case = s.get(Case, rec.case_id)
            if case.state == CaseState.RECOVERED.value:
                log_event(s, "verify", "Duplicate callback ignored: case already recovered, nothing sent", case.id)
                results.append("duplicate")
                continue
            executor._due_for_check(case.id, force=True)
            results.append(executor.verify(s, case, source="callback"))  # never trust the callback alone
        s.commit()
        return {"ok": True, "results": results}


class ReplyIn(BaseModel):
    text: str = ""
    audio_b64: str = ""
    mime: str = ""


@router.post("/api/customer/reply/{case_id}")
def customer_reply(case_id: str, body: ReplyIn):
    """A customer's reply to our message (console stand-in for the customer's phone; the Telegram
    customer chat calls the same code). Voice goes through Sarvam speech-to-text first."""
    if len(body.audio_b64) > 2_000_000:
        raise HTTPException(413, "voice note too large (keep it under 30 s)")
    text, stt = body.text, None
    if body.audio_b64 and get_settings().sarvam_enabled:
        import base64
        try:
            r = voice.transcribe_full(base64.b64decode(body.audio_b64), body.mime)
            text, stt = r["transcript"] or text, {"provider": "sarvam", "model": "saaras:v3", "language": r["language_code"]}
        except Exception as e:  # noqa: BLE001
            stt = {"provider": "sarvam", "ok": False, "error": type(e).__name__}
    if not text.strip():
        raise HTTPException(400, "empty reply")
    with executor.LOCK, session() as s:
        if not s.get(Case, case_id):
            raise HTTPException(404)
        r = executor.handle_reply(s, case_id, text, via="console", stt=stt)
        s.commit()
        return r


# ------------------------------------------------------------------ demo controls
def _require_demo_controls():
    if not get_settings().demo_controls_enabled:
        raise HTTPException(403, "Demo controls are disabled in production")


def _fake():
    _require_demo_controls()
    gw = get_gateway()
    if gw.name != "fake":
        raise HTTPException(400, "This control works with the fake gateway only")
    return gw


@router.post("/api/demo/reset")
def demo_reset():
    _require_demo_controls()
    with executor.LOCK, session() as s:
        seed.reset(s)
        seed.seed(s)
        gw = get_gateway()
        if gw.name == "fake":
            gw.reset()
        return {"ok": True}


@router.post("/api/demo/spike")
def demo_spike():
    _require_demo_controls()
    with executor.LOCK, session() as s:
        return {"cases": seed.trigger_spike(s)}


@router.post("/api/demo/bank-recovers")
def demo_bank_recovers():
    _require_demo_controls()
    detect.mark_recovered("Bank A")
    with executor.LOCK, session() as s:
        log_event(s, "signal", "Bank A success rate is back to normal")
        s.commit()
    return {"ok": True}


@router.post("/api/demo/reset-incident")
def demo_reset_incident():
    _require_demo_controls()
    with executor.LOCK, session() as s:
        seed.reset(s)
        seed.seed(s)
        seed.trigger_spike(s)
        executor.tick(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        executor.tick(s)
        gw = get_gateway()
        if gw.name == "fake":
            gw.reset()
        s.commit()
    return {"ok": True, "cases": 14, "split": "9 auto, 2 owner, 3 blocked"}


def _pay_case(s, case_id: str, wrong_amount: bool = False) -> dict:
    gw = _fake()
    rec = executor.link_of(s, case_id)
    if not rec:
        raise HTTPException(400, "No link sent for this case yet")
    amount = None
    if wrong_amount:
        owed = s.get(Payment, s.get(Case, case_id).payment_id).amount_paise
        amount = max(100, owed - 10000)  # the gateway reports ₹100 less than owed
    gw.pay(rec.link_id, amount)
    return gw.callback_payload(rec.link_id)


@router.post("/api/demo/pay/{case_id}")
async def demo_pay(case_id: str, request: Request):
    _require_demo_controls()
    with executor.LOCK, session() as s:
        payload = _pay_case(s, case_id)
    return await _deliver_callback(payload)


@router.post("/api/demo/pay-wrong-amount/{case_id}")
async def demo_pay_wrong(case_id: str):
    """Safe-failure demo: the gateway confirms a payment for the wrong amount. Nothing may be credited."""
    _require_demo_controls()
    with executor.LOCK, session() as s:
        payload = _pay_case(s, case_id, wrong_amount=True)
    return await _deliver_callback(payload)


async def _deliver_callback(payload: dict):
    from starlette.datastructures import Headers  # noqa: F401
    gw = get_gateway()
    link_id = payload["LINKID"]
    if not gw.verify_callback(payload):
        raise HTTPException(400)
    with executor.LOCK, session() as s:
        recs = s.exec(select(ActionRecord).where(ActionRecord.link_id == link_id, ActionRecord.kind == "payment_link")).all()
        evidence.record(s, "link_callback", {k: v for k, v in payload.items() if k != "CHECKSUMHASH"} |
                        {"checksum_valid": True, "matched_cases": [r.case_id for r in recs], "delivered_by": "demo control"},
                        case_id=recs[0].case_id if len(recs) == 1 else "", source="fake-gateway (demo button)")
        res = []
        for rec in recs:
            case = s.get(Case, rec.case_id)
            if case.state == CaseState.RECOVERED.value:
                log_event(s, "verify", "Duplicate callback ignored: case already recovered, nothing sent", case.id)
                res.append("duplicate")
                continue
            executor._due_for_check(case.id, force=True)
            res.append(executor.verify(s, case, source="callback"))
        s.commit()
    return {"ok": True, "results": res}


@router.post("/api/demo/duplicate-callback/{case_id}")
async def demo_duplicate(case_id: str):
    _require_demo_controls()
    with executor.LOCK, session() as s:
        rec = executor.link_of(s, case_id)
        if not rec:
            raise HTTPException(400, "No link for this case")
        payload = _fake().callback_payload(rec.link_id)
    return await _deliver_callback(payload)


@router.post("/api/demo/fault/{name}")
def demo_fault(name: str, on: bool = True):
    _require_demo_controls()
    gw = _fake()
    if name == "status-timeout":
        gw.fail_status_calls = on
    elif name == "gateway-down":
        gw.fail_create_calls = on
    else:
        raise HTTPException(404)
    with executor.LOCK, session() as s:
        log_event(s, "fault", f"Injected fault '{name}' {'ON' if on else 'OFF'}")
        s.commit()
    return {"ok": True}


@router.post("/api/demo/stop/{case_id}")
def demo_stop(case_id: str):
    _require_demo_controls()
    with executor.LOCK, session() as s:
        c = s.get(Case, case_id)
        if not c:
            raise HTTPException(404)
        n = executor.customer_stop(s, s.get(Payment, c.payment_id).customer_id)
        s.commit()
        return {"stopped": n}


@router.post("/api/eval/run")
def eval_run(n: int = 400):
    _require_demo_controls()
    with executor.LOCK, session() as s:
        try:
            return evaluate.run_batch(s, n=n)
        except RuntimeError as e:
            raise HTTPException(400, str(e))


@router.get("/api/eval")
def eval_latest():
    _require_demo_controls()
    with session() as s:
        return evaluate.latest(s) or {}


# ------------------------------------------------------------------ fake checkout page
PAY_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pay {merchant}</title><style>body{{font-family:system-ui,Arial,sans-serif;background:#F7F6F2;color:#0B1220;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center}}
.card{{background:#fff;border:1px solid #D9D6CE;border-radius:18px;padding:28px;width:min(360px,90vw)}}.tag{{background:#FFF4E0;color:#7A4300;font-size:11px;font-weight:700;letter-spacing:.1em;padding:4px 8px;border-radius:6px}}
h1{{font-size:20px;margin:14px 0 4px}}.amt{{font-size:40px;font-weight:700;margin:12px 0}}button{{width:100%;padding:14px;border:0;border-radius:12px;background:#1746C8;color:#fff;font-size:16px;font-weight:600}}
p{{color:#3D4654}}</style></head><body><div class="card"><span class="tag">TEST CHECKOUT · FAKE GATEWAY</span><h1>{merchant}</h1><p>{desc}</p>
<div class="amt">₹{amount}</div>{body}</div></body></html>"""


@router.get("/pay/{link_id}", response_class=HTMLResponse)
def pay_page(link_id: str):
    gw = _fake()
    link = gw.links.get(link_id)
    if not link:
        raise HTTPException(404)
    paid = link["txn"] != ""
    body = ("<p><b>Paid.</b> Transaction " + link["txn"] + "</p>") if paid else \
        f'<form method="post" action="/pay/{link_id}"><button type="submit">Pay ₹{fmt_inr(link["amount"])}</button></form>'
    return PAY_PAGE.format(merchant=get_settings().merchant_name, desc=link["desc"], amount=fmt_inr(link["amount"]), body=body)


@router.post("/pay/{link_id}")
async def pay_submit(link_id: str):
    gw = _fake()
    if link_id not in gw.links:
        raise HTTPException(404)
    gw.pay(link_id)
    await _deliver_callback(gw.callback_payload(link_id))
    return RedirectResponse(f"/pay/{link_id}", status_code=303)
