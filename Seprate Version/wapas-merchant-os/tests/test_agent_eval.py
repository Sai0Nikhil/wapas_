from sqlmodel import select

from app import agent, detect, evaluate, executor, seed
from app.models import Case


def test_invalid_llm_output_goes_to_owner(db, monkeypatch):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_base_url", "http://llm.invalid")
    monkeypatch.setattr(cfg, "llm_api_key", "k")
    monkeypatch.setattr(cfg, "llm_model", "m")
    monkeypatch.setattr(agent, "llm_reasoner", lambda b: (None, '{"diagnosis":"maybe"}', "bad", []))
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        c = s.get(Case, "c_A118")
        assert c.state == "WAITING_OWNER"
        assert executor.latest_decision(s, c.id).confidence == 0.0


def test_llm_down_falls_back_to_rules(db, monkeypatch):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_base_url", "http://llm.invalid")
    monkeypatch.setattr(cfg, "llm_api_key", "k")
    monkeypatch.setattr(cfg, "llm_model", "m")

    def boom(b):
        raise ConnectionError("down")
    monkeypatch.setattr(agent, "llm_reasoner", boom)
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        d = executor.latest_decision(s, "c_A118")
        assert d.reasoner.startswith("rules") and d.chosen_action == "payment_link"


def test_decision_contract_rejects_two_chosen():
    import pytest
    from pydantic import ValidationError
    bad = {"diagnosis": "bank_side", "evidence": ["x"], "confidence": 0.9,
           "chosen": {"action": "payment_link", "send_after": "now", "template": "bank_issue_v1"},
           "options": [{"action": a, "verdict": "chosen", "why": "Chosen: x"} for a in agent.OPTION_ACTIONS]}
    with pytest.raises(ValidationError):
        agent.DecisionOut.model_validate(bad)


def test_newcombe_interval():
    d, lo, hi = evaluate.newcombe(50, 100, 30, 100)
    assert abs(d - 0.2) < 1e-9 and lo < 0.2 < hi and lo > 0.05 and hi < 0.35


def test_eval_batch_has_no_duplicates_or_breaches(db):
    with db.session() as s:
        m = evaluate.run_batch(s, n=120, holdout_share=0.2, seed=3)
        assert m["treated_n"] + m["holdout_n"] == 120
        assert m["duplicates"] == 0 and m["breaches"] == 0
        assert 0 <= m["holdout_rate"] <= 1 and m["uplift_ci"][0] <= m["uplift"] <= m["uplift_ci"][1]
        live = s.exec(select(Case).where(Case.batch == "live")).all()
        assert live == []


def test_eval_batch_leaves_no_case_stuck_waiting(db, monkeypatch):
    """Every simulated case must reach an outcome, or the treated rate is silently deflated."""
    from sqlmodel import select
    from app import evaluate
    from app.config import get_settings
    from app.models import Case
    monkeypatch.setattr(get_settings(), "learning", True)
    with db.session() as s:
        m = evaluate.run_batch(s, n=200, seed=11, wave=50)
        stuck = s.exec(select(Case).where(Case.batch == m["batch"], Case.group == "TREATED",
                                          Case.state.in_(["NEW", "DECIDED", "SCHEDULED", "WAITING_OWNER", "SENT"]))).all()
        assert stuck == [], [(c.id, c.state, c.stop_reason) for c in stuck][:5]
