import base64

import pytest
from sqlmodel import select

from app import approvals, doctor, executor, seed, telegram
from app.config import get_settings
from app.models import Case, Evidence

OWNER = 111      # private chat: chat id == the owner's user id
CUSTOMER = 222


@pytest.fixture()
def tg(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "telegram_bot_token", "123:abc", raising=False)
    monkeypatch.setattr(cfg, "telegram_owner_chat_id", str(OWNER), raising=False)
    monkeypatch.setattr(cfg, "telegram_customer_chat_id", str(CUSTOMER), raising=False)
    monkeypatch.setattr(cfg, "telegram_owner_user_id", "", raising=False)
    sent = []

    def fake_call(method, data=None, files=None, timeout=15.0):
        sent.append((method, data, files))
        return {"ok": True, "result": {"message_id": 1}}
    monkeypatch.setattr(telegram, "call", fake_call)
    telegram._msg_case.clear()
    telegram._last_case.clear()
    return sent


def _handlers(calls):
    def decision(verb, cid, token):
        from app import main
        calls.append((verb, cid))
        return main._tg_decision(verb, cid, token)

    def stop(cid):
        calls.append(("stop", cid))
        return 1

    def question(text, audio_b64, mime):
        calls.append(("q", text, bool(audio_b64)))
        return {"answer_hi": "हाँ", "answer_en": "Yes", "question": text, "audio_b64": base64.b64encode(b"ID3").decode(),
                "audio_mime": "audio/mpeg"}
    return dict(on_decision=decision, on_stop=stop, on_question=question)


def _press(token, chat=OWNER, user=OWNER):
    return {"callback_query": {"id": "q1", "data": token, "from": {"id": user},
                               "message": {"message_id": 9, "chat": {"id": chat}, "text": "Needs your approval"}}}


def _waiting(db):
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        assert s.get(Case, "c_A121").state == "WAITING_OWNER"
        return executor.latest_decision(s, "c_A121").id


def test_signed_owner_button_approves(db, tg):
    did = _waiting(db)
    calls = []
    r = telegram.handle_update(_press(approvals.make("ap", "c_A121", did)), **_handlers(calls))
    assert r.startswith("ap:c_A121:") and "rejected" not in r
    assert [m for m, _, _ in tg] == ["answerCallbackQuery", "editMessageText"]
    with db.session() as s:
        assert s.get(Case, "c_A121").owner_approved is True
        ev = s.exec(select(Evidence).where(Evidence.case_id == "c_A121", Evidence.kind == "owner_decision")).all()
        assert ev and ev[-1].ok


def test_forged_expired_stale_and_replayed_tokens_do_nothing(db, tg):
    did = _waiting(db)
    calls = []
    h = _handlers(calls)
    good = approvals.make("ap", "c_A121", did)
    verb, case, exp, sig = good.split(":")
    forged = f"ap:c_A121:{exp}:{'A' * len(sig)}"
    other_case = f"ap:c_A124:{exp}:{sig}"                                       # signature is bound to the case
    skip_as_approve = f"ap:c_A121:{exp}:{approvals.make('sk', 'c_A121', did).split(':')[3]}"  # and to the verb
    expired = approvals.make("ap", "c_A121", did, ttl_seconds=-5)
    stale = approvals.make("ap", "c_A121", did + 999)                           # for a decision that is not current
    for tok in (forged, other_case, skip_as_approve, expired, stale):
        assert "rejected" in telegram.handle_update(_press(tok), **h), tok
    with db.session() as s:
        assert s.get(Case, "c_A121").state == "WAITING_OWNER" and not s.get(Case, "c_A121").owner_approved
    assert "rejected" not in telegram.handle_update(_press(good), **h)        # the real one works once
    assert telegram.handle_update(_press(good), **h).endswith("not-waiting")   # replay: nothing happens


def test_only_the_owner_user_can_press(db, tg, monkeypatch):
    did = _waiting(db)
    calls = []
    tok = approvals.make("ap", "c_A121", did)
    assert telegram.handle_update(_press(tok, chat=CUSTOMER, user=CUSTOMER), **_handlers(calls)).startswith("ignored")
    # owner chat is a group: a random member cannot approve unless they are the configured owner user
    monkeypatch.setattr(get_settings(), "telegram_owner_chat_id", "-100500", raising=False)
    assert telegram.handle_update(_press(tok, chat=-100500, user=777), **_handlers(calls)).startswith("ignored")
    monkeypatch.setattr(get_settings(), "telegram_owner_user_id", "777", raising=False)
    assert "rejected" not in telegram.handle_update(_press(tok, chat=-100500, user=777), **_handlers(calls))
    assert calls == [("ap", "c_A121")]
    assert tg[0][0] == "answerCallbackQuery"  # ignored presses are still answered, as Telegram asks


def test_token_fits_telegram_limit():
    tok = approvals.make("ap", "c_WAP1790179470B676", 123456)
    assert len(tok.encode()) <= 64 and approvals.check(tok, 123456)[0]


def test_owner_request_message_says_what_why_risk_and_expiry(db, tg, monkeypatch):
    monkeypatch.setattr(telegram, "enabled", lambda: True)
    q = telegram._out
    while not q.empty():
        q.get_nowait()
    _waiting(db)
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    texts = [d["text"] for m, d, _ in msgs if m == "sendMessage" and "needs your approval" in d.get("text", "")]
    assert texts, msgs
    t = texts[0]
    for part in ("Customer:", "Amount: ₹", "Why you:", "Wapas proposes:", "Risk:", "expire", "contacts nobody"):
        assert part in t, part
    kb = [d for m, d, _ in msgs if "reply_markup" in d][0]["reply_markup"]["inline_keyboard"][0]
    assert [b["text"] for b in kb] == ["Approve", "Skip"] and all(len(b["callback_data"]) <= 64 for b in kb)


def test_unanswered_approval_closes_without_contact(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "approval_ttl_hours", 0.0)
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        executor.tick(s)
        c = s.get(Case, "c_A121")
        assert c.state == "STOPPED" and c.stop_reason == "owner_timeout" and c.messages_sent == 0


def test_customer_stop_reply_maps_to_the_right_case(db, tg):
    telegram._msg_case[77] = "c_A118"
    telegram._msg_case[78] = "c_A127"
    calls = []
    u = {"message": {"chat": {"id": CUSTOMER}, "from": {"id": CUSTOMER}, "text": "stop", "reply_to_message": {"message_id": 77}}}
    assert telegram.handle_update(u, **_handlers(calls)) == "stop:c_A118:1"
    assert calls == [("stop", "c_A118")]


def test_owner_question_gets_text_and_mp3_reply(db, tg):
    calls = []
    u = {"message": {"chat": {"id": OWNER}, "from": {"id": OWNER}, "text": "Kitna wapas aaya?"}}
    assert telegram.handle_update(u, **_handlers(calls)) == "answered"
    assert calls == [("q", "Kitna wapas aaya?", False)]
    assert [m for m, _, _ in tg] == ["sendMessage", "sendAudio"]
    name, raw, mime = tg[1][2]["audio"]
    assert name == "wapas.mp3" and mime == "audio/mpeg" and raw == b"ID3"


def test_long_voice_note_is_refused_before_calling_sarvam(db, tg):
    calls = []
    u = {"message": {"chat": {"id": OWNER}, "from": {"id": OWNER}, "voice": {"file_id": "f", "duration": 45}}}
    assert telegram.handle_update(u, **_handlers(calls)) == "voice too long" and calls == []


def test_non_owner_text_is_not_answered(db, tg):
    calls = []
    u = {"message": {"chat": {"id": 999}, "from": {"id": 999}, "text": "how much?"}}
    assert telegram.handle_update(u, **_handlers(calls)) == "ignored" and calls == []


def test_queue_is_silent_when_telegram_is_off(monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "", raising=False)
    before = telegram._out.qsize()
    telegram.owner_note("hello")
    assert telegram._out.qsize() == before


def test_doctor_reports_not_configured_when_nothing_is_set(db, monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "sarvam_api_key", "", raising=False)
    monkeypatch.setattr(cfg, "n8n_webhook_url", "", raising=False)
    res = {r["name"]: r["status"] for r in doctor.run_all()}
    assert res["Paytm"] == "SIMULATED" and res["LLM"] == "NOT CONFIGURED"
    assert res["Sarvam voice"] == "NOT CONFIGURED" and res["Telegram"] == "NOT CONFIGURED"
    assert res["Database"] == "VERIFIED"


def test_doctor_database_check_is_read_only(db, monkeypatch):
    from app import db as dbm

    def forbidden_engine():
        pytest.fail("SQLite diagnostics must not open the writable application engine")

    monkeypatch.setattr(dbm, "engine", forbidden_engine)
    result = doctor.check_database()
    assert result["status"] == "VERIFIED"
    assert result["checks"][0]["item"] == "read-only connection"


def test_doctor_cli_does_not_initialize_or_migrate_database(monkeypatch):
    from app import db as dbm

    def forbidden_init(*_args, **_kwargs):
        pytest.fail("the diagnostic command must not initialize or migrate a database")

    monkeypatch.setattr(dbm, "init_db", forbidden_init)
    monkeypatch.setattr(doctor, "run_all", lambda **_kwargs: [])
    assert doctor.main(["--json"]) == 0


def test_doctor_flags_a_rejected_paytm_key(db, monkeypatch):
    from app.ports import PayStatus, StatusResult
    monkeypatch.setattr(get_settings(), "gateway", "paytm")
    monkeypatch.setattr(get_settings(), "paytm_mid", "MID", raising=False)
    monkeypatch.setattr(get_settings(), "paytm_merchant_key", "k" * 16, raising=False)

    class G:
        name = "paytm"

        def order_status(self, order_id):
            return StatusResult(status=PayStatus.ERROR, raw={"resultInfo": {"resultCode": "330", "resultMsg": "Invalid Checksum"}})
    monkeypatch.setattr(doctor, "get_gateway", lambda: G())
    r = doctor.check_paytm()
    assert r["status"] == "FAILED" and any("330" in c["detail"] for c in r["checks"])


def test_secrets_never_reach_logs(monkeypatch):
    import logging
    from app.redact import RedactingFilter, redact, redact_obj
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw", raising=False)
    monkeypatch.setattr(get_settings(), "paytm_merchant_key", "SuperSecretKey12", raising=False)
    line = "POST https://api.telegram.org/bot123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw/getUpdates key=SuperSecretKey12"
    assert "AAHdq" not in redact(line) and "SuperSecret" not in redact(line)
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "req %s", (line,), None)
    RedactingFilter().filter(rec)
    assert "AAHdq" not in rec.getMessage() and "SuperSecret" not in rec.getMessage()
    # uvicorn's access formatter unpacks a 5-tuple; the filter must keep the shape
    acc = logging.LogRecord("uvicorn.access", logging.INFO, "f", 1, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4", "GET", "/?token=abc123", "1.1", 200), None)
    RedactingFilter().filter(acc)
    assert len(acc.args) == 5 and "abc123" not in acc.getMessage()
    assert redact_obj({"head": {"signature": "xyz"}, "CHECKSUMHASH": "q"}) == {"head": {"signature": "<redacted>"}, "CHECKSUMHASH": "<redacted>"}
