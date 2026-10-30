"""The slide-5/6 incident end to end on the fake gateway."""
from sqlmodel import select

from app import detect, executor, seed
from app.gateway import get_gateway
from app.models import ActionRecord, Case, Message, Outcome
from app.ports import CaseState


def states(s):
    rows = s.exec(select(Case).where(Case.batch == "live")).all()
    out = {}
    for c in rows:
        out[c.state] = out.get(c.state, 0) + 1
    return out


def case(s, order):
    return s.get(Case, f"c_{order}")


def test_incident_policy_split(db):
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        st = states(s)
        # 9 allowed but queued until the bank recovers, 2 to the owner, 3 blocked
        assert st == {"SCHEDULED": 9, "WAITING_OWNER": 2, "BLOCKED": 3}
        assert {case(s, o).stop_reason for o in ("A143", "A145", "A147")} == {"opted_out", "duplicate"}
        rahul = executor.latest_decision(s, "c_A118")
        assert rahul.diagnosis == "bank_side" and rahul.send_after == "bank_recovered"
        assert rahul.language == "hi" and rahul.template == "bank_issue_v1"
        links = s.exec(select(ActionRecord).where(ActionRecord.case_id.like("c_A1%"),
                                                  ActionRecord.kind == "payment_link")).all()
        assert [l.case_id for l in links] == ["c_A147_prior"]  # only the seeded earlier link


def test_bank_recovery_sends_exactly_one_link_each(db):
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        executor.tick(s)
        assert states(s).get("SENT") == 9
        links = s.exec(select(ActionRecord).where(ActionRecord.kind == "payment_link",
                                                  ActionRecord.case_id.like("c_A1%"))).all()
        live = [l for l in links if not l.case_id.endswith("_prior")]
        assert len(live) == 9 and len({l.idempotency_key for l in live}) == 9
        msg = s.exec(select(Message).where(Message.case_id == "c_A118")).first()
        assert "राहुल" not in msg.text and "Rahul" in msg.text and "₹2,340" in msg.text  # Hindi template, name as given


def test_payment_recovered_only_after_status_check_and_duplicate_ignored(db):
    gw = get_gateway()
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        rec = executor.link_of(s, "c_A118")
        gw.pay(rec.link_id)
        assert case(s, "A118").state == "SENT"  # paying alone changes nothing until we verify
        executor.tick(s)
        c = case(s, "A118")
        assert c.state == "RECOVERED"
        out = s.exec(select(Outcome).where(Outcome.case_id == "c_A118")).one()
        assert out.amount_paise == 234000 and out.txn_id.startswith("TXN")
        before = gw.create_calls
        executor.verify(s, c)  # a second confirmation (duplicate callback)
        s.commit()
        assert gw.create_calls == before
        thanks = [m for m in s.exec(select(Message).where(Message.case_id == "c_A118")).all() if "धन्यवाद" in m.text]
        assert len(thanks) == 1


def test_status_timeout_is_unknown_and_not_counted(db):
    gw = get_gateway()
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        gw.pay(executor.link_of(s, "c_A127").link_id)
        gw.fail_status_calls = True
        executor.tick(s)
        assert case(s, "A127").state == "UNKNOWN"
        assert s.exec(select(Outcome).where(Outcome.case_id == "c_A127")).first() is None
        gw.fail_status_calls = False
        executor.tick(s)
        assert case(s, "A127").state == "RECOVERED"


def test_gateway_down_pauses_and_never_double_sends(db):
    gw = get_gateway()
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        gw.fail_create_calls = True
        detect.mark_recovered("Bank A")
        executor.tick(s)
        assert states(s).get("SCHEDULED") == 9
        assert s.exec(select(Message).where(Message.case_id == "c_A118")).all() == []
        gw.fail_create_calls = False
        executor.tick(s)
        executor.tick(s)
        assert states(s).get("SENT") == 9
        assert len(s.exec(select(Message).where(Message.case_id == "c_A118")).all()) == 1


def test_owner_approval_and_skip(db):
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        detect.mark_recovered("Bank A")
        executor.owner_approve(s, "c_A121")
        executor.owner_skip(s, "c_A124")
        s.commit()
        assert case(s, "A121").state == "SENT" and case(s, "A121").owner_approved
        assert case(s, "A124").state == "STOPPED"


def test_reminders_then_stop(db, monkeypatch):
    from app.config import get_settings
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        monkeypatch.setattr(get_settings(), "reminder_after_seconds", 0)
        executor.tick(s)   # reminder 1
        executor.tick(s)   # reminder 2
        executor.tick(s)   # cap reached -> stop
        c = case(s, "A118")
        assert c.messages_sent == 3 and c.state == "STOPPED" and c.stop_reason == "reminder_cap"
        links = s.exec(select(ActionRecord).where(ActionRecord.case_id == "c_A118", ActionRecord.kind == "payment_link")).all()
        assert len(links) == 1  # reminders reuse the same link


def test_customer_stop(db):
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        c = case(s, "A131")
        executor.customer_stop(s, "cast_A131")
        s.commit()
        assert case(s, "A131").state == "STOPPED" and case(s, "A131").stop_reason == "opted_out"


def test_quiet_hours_hold(db, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "clock_override", "22:30")
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        assert case(s, "A118").state == "SCHEDULED" and case(s, "A118").stop_reason == "quiet_hours"
        monkeypatch.setattr(get_settings(), "clock_override", "09:30")
        executor.tick(s)
        assert case(s, "A118").state == "SENT"


def test_voice_answer_counts_only_verified(db):
    from app import voice
    gw = get_gateway()
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        a = voice.answer(s, "आज कितने payments वापस आए?")
        assert a["intent"] == "total" and "कोई payment" in a["answer_hi"]
        gw.pay(executor.link_of(s, "c_A118").link_id)
        executor.tick(s)
        a = voice.answer(s, "aaj kitne payments wapas aaye")
        assert "₹2,340" in a["answer_hi"] and "2 बड़े amounts" in a["answer_hi"]
        assert voice.answer(s, "approval kitne pending?")["intent"] == "approvals"


def test_reset_and_replay_never_reuses_a_paid_link(db):
    """Regression: after a reset the same case ids come back; they must get new links."""
    gw = get_gateway()
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        gw.pay(executor.link_of(s, "c_A118").link_id)
        executor.tick(s)
        assert case(s, "A118").state == "RECOVERED"
        seed.reset(s)          # note: fake gateway memory deliberately NOT cleared here
        seed.seed(s)
    import time; time.sleep(1.1)  # new open time -> new idempotency key
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        executor.tick(s)
        assert case(s, "A118").state == "SENT"  # not instantly 'recovered' from the old paid link


def test_old_database_is_upgraded_in_place(tmp_path, monkeypatch):
    """A wapas.db from the first version (no learning/trace columns) must keep working."""
    import sqlite3
    from app import db as dbm, seed
    from app.config import get_settings
    from sqlmodel import select
    from app.models import Decision
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE decision (id INTEGER PRIMARY KEY, case_id VARCHAR, diagnosis VARCHAR, evidence_json VARCHAR, "
                "options_json VARCHAR, chosen_action VARCHAR, send_after VARCHAR, language VARCHAR, template VARCHAR, "
                "confidence FLOAT, reasoner VARCHAR, raw_output VARCHAR, created_at DATETIME)")
    con.execute("INSERT INTO decision (case_id, diagnosis, evidence_json, options_json, chosen_action, send_after, language, "
                "template, confidence, reasoner, raw_output) VALUES ('c_old','bank_side','[]','[]','payment_link','now','hi',"
                "'bank_issue_v1',0.9,'rules','')")
    con.commit()
    con.close()
    monkeypatch.setattr(get_settings(), "database_url", f"sqlite:///{path}")
    dbm.reset_engine()
    dbm.init_db()
    cols = [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(decision)")]
    assert "timing_arm" in cols and "trace_json" in cols
    with dbm.session() as s:
        old = s.exec(select(Decision).where(Decision.case_id == "c_old")).first()
        assert old.timing_arm == "now"
        seed.seed(s)
    dbm.reset_engine()


def test_wrong_amount_is_never_credited(db):
    """Verification mismatch: Paytm confirms a payment, but not for the amount owed. No recovery is counted,
    no thank-you goes out, the case is UNKNOWN and the owner is told."""
    from app.gateway import get_gateway
    from app.models import Message, Outcome
    from sqlmodel import select
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        rec = executor.link_of(s, "c_A118")
        get_gateway().pay(rec.link_id, 234000 - 10000)
        c = s.get(Case, "c_A118")
        assert executor.verify(s, c) == "mismatch"
        s.commit()
        c = s.get(Case, "c_A118")
        assert c.state == "UNKNOWN" and c.stop_reason == "amount_mismatch"
        assert s.exec(select(Outcome).where(Outcome.case_id == "c_A118")).first() is None
        assert not [m for m in s.exec(select(Message).where(Message.case_id == "c_A118")).all() if "धन्यवाद" in m.text or "Thank" in m.text]
        executor._due_for_check("c_A118", force=True)
        executor.tick(s)  # re-checking does not flip it back to SENT or credit it
        assert s.get(Case, "c_A118").state == "UNKNOWN"


def test_payment_after_followups_stopped_is_still_counted(db):
    """Money that arrives after Wapas stopped chasing is real money: Paytm's answer wins."""
    from app.gateway import get_gateway
    from app.models import Outcome
    from sqlmodel import select
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        c = s.get(Case, "c_A118")
        executor._set_state(s, c, CaseState.STOPPED, "reminder_cap")
        executor._close(s, c, "STOPPED", "No payment after reminders")
        s.commit()
        get_gateway().pay(executor.link_of(s, "c_A118").link_id)
        assert executor.verify(s, s.get(Case, "c_A118")) == "recovered"
        s.commit()
        o = s.exec(select(Outcome).where(Outcome.case_id == "c_A118")).first()
        assert o.result == "RECOVERED" and "after follow-ups had stopped" in o.detail
        assert s.get(Case, "c_A118").state == "RECOVERED"


def test_job_trace_and_proof_are_truthful_on_the_fake_gateway(db):
    """The console's story for one case is built from records, and nothing on the fake gateway is called VERIFIED."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, headers={"X-Wapas-Console": "1"})
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
    assert c.post("/api/demo/pay/c_A118").status_code == 200
    d = c.get("/api/cases/c_A118").json()
    titles = [x["title"] for x in d["job"]["steps"]]
    for t in ("Signal detected", "Context gathered", "Cause diagnosed", "Recovery options evaluated", "Policy → AUTO",
              "Payment link created", "Customer messaged", "Payment status → PAID", "Recovery verified"):
        assert t in titles, (t, titles)
    card = d["job"]["card"]
    assert card["policy"]["verdict"] == "AUTO" and all(ch["ok"] for ch in card["policy"]["checks"])
    assert "exactly one link" in card["action"] and card["result"].startswith("RECOVERED")
    assert d["job"]["source"]["kind"] == "simulated" and d["job"]["environment"] == "fake-gateway"
    bundle = c.get("/api/cases/c_A118/evidence").json()
    kinds = [e["kind"] for e in bundle["evidence"]]
    assert "link_created" in kinds and "status_check" in kinds and "link_callback" in kinds
    assert all(e["environment"] == "fake-gateway" for e in bundle["evidence"])
    proof = {i["name"]: i["status"] for i in c.get("/api/proof").json()["items"]}
    assert proof["Paytm"] == "SIMULATED" and proof["Latest verification"] == "SIMULATED"
    assert proof["Last autonomous job"] == "SIMULATED"
    assert "VERIFIED" not in (proof["Paytm"], proof["Latest verification"])


def test_proof_panel_never_shows_a_mismatched_payment_as_verification(db):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, headers={"X-Wapas-Console": "1"})
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
    assert c.post("/api/demo/pay-wrong-amount/c_A127").status_code == 200
    items = {i["name"]: i for i in c.get("/api/proof").json()["items"]}
    assert items["Latest verification"]["status"] == "UNVERIFIED"
    assert items["Last autonomous job"]["status"] == "UNVERIFIED"


def test_success_without_a_reported_amount_is_not_credited(db):
    """Found in review: a SUCCESS with amount 0 (e.g. Paytm omitting txnAmount) used to credit the owed amount."""
    from app.ports import PayStatus, StatusResult
    gw = get_gateway()
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        orig = gw.link_status
        gw.link_status = lambda link_id: StatusResult(PayStatus.SUCCESS, txn_id="TXNZERO", amount_paise=0)
        try:
            assert executor.verify(s, s.get(Case, "c_A118")) == "mismatch"
        finally:
            gw.link_status = orig
        s.commit()
        assert s.get(Case, "c_A118").state == "UNKNOWN"
        assert s.exec(select(Outcome).where(Outcome.case_id == "c_A118")).first() is None
