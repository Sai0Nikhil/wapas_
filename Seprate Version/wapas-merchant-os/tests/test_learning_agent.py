import json
import random

from app import agent, detect, executor, learning, seed
from app.models import Case


def test_bandit_prefers_the_arm_that_pays(db, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "learning", True)
    from app import evaluate
    with db.session() as s:
        m = evaluate.run_batch(s, n=400, holdout_share=0.2, seed=5, wave=50)
        stats = m["learning"]
        cs = stats["customer_side"]
        # simulated truth: 'wait' pays better for customer-side failures; the loop should learn that
        # and shift traffic there. Seeded, so this is deterministic (18/20 seeds pass; see README).
        assert cs["wait"]["mean"] > cs["now"]["mean"]
        assert cs["wait"]["n"] > cs["now"]["n"]
        assert cs["now"]["n"] >= 15  # the exploration floor keeps the losing arm measured
        last = m["waves"][-1]
        assert m["duplicates"] == 0 and m["breaches"] == 0
        assert sum(w["now"] + w["wait"] for w in m["waves"]) > 0 and last["now"] + last["wait"] > 0


def test_live_customers_are_never_randomised(db, monkeypatch):
    """Hard safety rule: exploration exists only in research batches. Even with learning on and research
    data screaming 'wait', a live case gets the agent's deterministic timing and choose_arm is never called."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "learning", True)
    from app import evaluate
    with db.session() as s:
        evaluate.run_batch(s, n=120, seed=5, wave=40)  # research data exists

    def boom(*a, **k):
        raise AssertionError("choose_arm called for a live case")
    monkeypatch.setattr(learning, "choose_arm", boom)
    with db.session() as s:
        seed.trigger_spike(s)
        detect.mark_recovered("Bank A")
        executor.tick(s)
        live = s.exec(__import__("sqlmodel").select(Case).where(Case.batch == "live")).all()
        arms = {executor.latest_decision(s, c.id).timing_arm for c in live if executor.latest_decision(s, c.id)}
        assert arms == {"now"}
        assert s.get(Case, "c_A118").state == "SENT"


def test_choose_arm_refuses_live_batches(db):
    import pytest
    with db.session() as s:
        for batch in ("live", "", "earlier"):
            with pytest.raises(learning.LiveExperimentError):
                learning.choose_arm(s, "bank_side", batch=batch)
        arm, info = learning.choose_arm(s, "bank_side", batch="eval-123")
        assert arm in learning.ARMS


def test_agent_recommended_delay_is_deterministic_and_policy_checked(db, monkeypatch):
    """'later' is the agent's judgment (e.g. customer just closed the checkout), not an experiment."""
    from app.config import get_settings
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(get_settings(), "agent_delay_seconds", 1800)
    from app.models import Payment
    with db.session() as s:
        seed.trigger_spike(s)
        s.add(Payment(id="pay_drop", order_id="DROP1", customer_id="cast_A118", amount_paise=99900, bank="Bank C",
                      status="FAILED", failure_code="USER_DROPPED"))
        s.add(Case(id="c_drop", payment_id="pay_drop", batch="live"))
        s.commit()
        executor.tick(s)
        c = s.get(Case, "c_drop")
        d = executor.latest_decision(s, "c_drop")
        assert d.send_after == "later" and d.timing_arm == "now"
        assert c.state == "SCHEDULED" and c.stop_reason == "agent_later" and c.messages_sent == 0
        c.send_not_before = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.add(c)
        s.commit()
        executor.tick(s)
        assert s.get(Case, "c_drop").state == "SENT" and s.get(Case, "c_drop").messages_sent == 1


def test_hallucinated_tool_is_refused_and_traced(db, monkeypatch):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_base_url", "https://api.sarvam.ai/v1")
    monkeypatch.setattr(cfg, "llm_api_key", "k")
    monkeypatch.setattr(cfg, "llm_model", "sarvam-105b")
    calls = []

    def fake_chat(body):
        calls.append(body)
        if body.get("tool_choice") == "auto" and len(calls) == 1:
            return {"content": "", "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "create_payment_link", "arguments": "{\"amount\": 99999}"}},
                {"id": "t2", "type": "function", "function": {"name": "get_bank_health", "arguments": "{}"}}]}
        if body.get("tool_choice") == "auto":
            return {"content": "done"}
        return {"content": "not json at all"}
    monkeypatch.setattr(agent, "_chat", fake_chat)
    from app.gateway import get_gateway
    before = len(get_gateway().links)
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        d = executor.latest_decision(s, "c_A118")
        trace = json.loads(d.trace_json)
        assert trace[0]["tool"] == "create_payment_link" and trace[0]["rejected"] is True
        assert "not an allowed tool" in trace[0]["result"]["error"]
        assert d.confidence == 0.0  # invalid final output -> owner decides
        assert s.get(Case, "c_A118").state in ("WAITING_OWNER", "SCHEDULED")
    assert len(get_gateway().links) == before  # the agent created nothing


def test_agent_module_cannot_reach_the_gateway():
    """Execution boundary: the agent imports nothing that can move money or message a customer."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(agent))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    forbidden = {"gateway", "executor", "messaging", "telegram", "store", "paytm", "fake"}
    assert not (imported & forbidden), imported & forbidden
    assert set(agent.TOOL_NAMES) == {"get_customer_history", "get_bank_health", "get_learning_stats"}


def test_tool_calling_agent_trace_and_schema(db, monkeypatch):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_base_url", "https://api.sarvam.ai/v1")
    monkeypatch.setattr(cfg, "llm_api_key", "k")
    monkeypatch.setattr(cfg, "llm_model", "sarvam-105b")
    calls = []
    final = {"diagnosis": "bank_side", "evidence": ["Bank A: 14 of 20 failed", "11 on-time payments"],
             "options": [{"action": "retry_now", "verdict": "rejected", "why": "Rejected: bank still degraded"},
                         {"action": "payment_link", "verdict": "chosen", "why": "Chosen: brief outage, good payer"},
                         {"action": "ask_owner", "verdict": "rejected", "why": "Not needed: under limit"},
                         {"action": "no_action", "verdict": "rejected", "why": "Rejected: likely a lost sale"}],
             "chosen": {"action": "payment_link", "send_after": "bank_recovered", "template": "bank_issue_v1"},
             "confidence": 0.91}

    def fake_chat(body):
        calls.append(body)
        if body.get("tool_choice") == "auto" and len(calls) == 1:
            return {"content": "", "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "get_customer_history", "arguments": "{}"}},
                {"id": "t2", "type": "function", "function": {"name": "get_bank_health", "arguments": "{}"}}]}
        if body.get("tool_choice") == "auto":
            return {"content": "I have what I need."}
        assert body["response_format"]["type"] == "json_schema"
        # Sarvam answers 400 if tool messages arrive without the tool list; the final call must not call tools
        assert body["tools"] and body["tool_choice"] == "none"
        return {"content": json.dumps(final)}
    monkeypatch.setattr(agent, "_chat", fake_chat)
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        d = executor.latest_decision(s, "c_A118")
        trace = json.loads(d.trace_json)
        assert d.reasoner == "llm:sarvam-105b" and d.confidence == 0.9  # 0.91 claimed, capped at the detector's 0.9
        assert [t["tool"] for t in trace] == ["get_customer_history", "get_bank_health"]
        assert trace[0]["result"]["on_time_payments"] == 11
        # tool messages were sent back to the model with matching ids
        tool_msgs = [m for m in calls[1]["messages"] if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tool_msgs] == ["t1", "t2"]


def test_eval_is_reproducible(db, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "learning", True)
    from app import evaluate
    from app.gateway import get_gateway
    runs = []
    for _ in range(2):  # same seed on a fresh database -> identical arm choices and outcomes
        db.init_db(drop=True)
        get_gateway().reset()
        with db.session() as s:
            seed.seed(s)
            runs.append(evaluate.run_batch(s, n=100, holdout_share=0.2, seed=9, wave=50))
    a, b = runs
    assert a["waves"] == b["waves"] and a["treated_rate"] == b["treated_rate"]


def test_simulated_outcomes_never_steer_live_customers(db, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "learning", True)
    from app import evaluate
    with db.session() as s:
        m = evaluate.run_batch(s, n=120, seed=4, wave=40)
        assert sum(v["n"] for d in m["learning"].values() for v in d.values()) > 0
        live = learning.live_evidence(s)
        assert all(d["contacted_closed"] == 0 for d in live.values())


def test_back_to_back_batches_do_not_collide(db):
    from app import evaluate
    with db.session() as s:
        a = evaluate.run_batch(s, n=20, seed=1, wave=20)
        b = evaluate.run_batch(s, n=20, seed=1, wave=20)
    assert a["batch"] != b["batch"]


def test_thompson_draws_are_beta():
    rng = random.Random(1)

    class S:  # minimal stand-in: no data -> uniform priors
        pass
    import app.learning as L
    L_arm_stats = L.arm_stats
    L.arm_stats = lambda s, d, batch="live": {a: {"paid": 0, "unpaid": 0, "n": 0, "mean": 0.5} for a in L.ARMS}
    try:
        picks = [L.choose_arm(S(), "bank_side", rng, batch="eval-t")[0] for _ in range(200)]
        assert 60 < picks.count("now") < 140
    finally:
        L.arm_stats = L_arm_stats


def test_model_calls_run_in_parallel_outside_the_lock(db, monkeypatch):
    import time
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_parallel", 6)
    real = agent.rules_reasoner

    def slow_decide(b):
        time.sleep(0.3)  # a model round-trip
        return agent.AgentDecision(real(b), "llm:test", trace=[{"tool": "get_bank_health", "result": {}}])
    monkeypatch.setattr(agent, "decide", slow_decide)
    with db.session() as s:
        seed.trigger_spike(s)
        bundles = executor.pending_bundles(s)
    assert len(bundles) == 14
    t0 = time.time()
    pre = executor.think(bundles)  # no lock held here
    assert time.time() - t0 < 14 * 0.3 / 2
    monkeypatch.setattr(agent, "decide", lambda b: (_ for _ in ()).throw(AssertionError("decided twice")))
    with executor.LOCK, db.session() as s:
        executor.tick(s, pre)
        assert executor.latest_decision(s, "c_A118").reasoner == "llm:test"


def test_eval_batch_never_calls_the_llm(db, monkeypatch):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_base_url", "https://api.sarvam.ai/v1")
    monkeypatch.setattr(cfg, "llm_api_key", "k")
    monkeypatch.setattr(cfg, "llm_model", "sarvam-105b")
    monkeypatch.setattr(agent, "_chat", lambda body: (_ for _ in ()).throw(AssertionError("LLM called in eval")))
    from app import evaluate
    with db.session() as s:
        m = evaluate.run_batch(s, n=40, seed=3, wave=20)
    assert m["treated_n"] > 0 and m["reasoner"].startswith("rules")


def test_sarvam_reasoning_is_off_by_default_and_explicit_when_set(monkeypatch):
    """Sarvam reasons when the field is absent, so "off" must go out as null (measured live: 30-60 s
    per call with reasoning, 1-4 s without)."""
    import httpx
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_base_url", "https://api.sarvam.ai/v1")
    monkeypatch.setattr(cfg, "llm_api_key", "k")
    seen = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        seen.update(url=url, body=json, headers=headers, timeout=timeout)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(agent.httpx, "post", fake_post)
    monkeypatch.setattr(cfg, "llm_reasoning_effort", "off")
    agent._chat({"model": "sarvam-105b", "messages": []})
    assert seen["url"] == "https://api.sarvam.ai/v1/chat/completions" and seen["headers"]["api-subscription-key"] == "k"
    assert "reasoning_effort" in seen["body"] and seen["body"]["reasoning_effort"] is None
    assert seen["body"]["max_tokens"] == 1024 and seen["timeout"] == 45.0
    monkeypatch.setattr(cfg, "llm_reasoning_effort", "low")
    agent._chat({"model": "sarvam-105b", "messages": []})
    assert seen["body"]["reasoning_effort"] == "low" and seen["body"]["max_tokens"] == 4096 and seen["timeout"] == 90.0
    agent._chat({"model": "sarvam-105b", "messages": [], "reasoning_effort": None, "max_tokens": 300})
    assert seen["body"]["reasoning_effort"] is None and seen["body"]["max_tokens"] == 300  # explicit values win


def test_rate_limit_is_retried_not_mistaken_for_no_tool_support(monkeypatch):
    import httpx
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_base_url", "https://api.sarvam.ai/v1")
    monkeypatch.setattr(cfg, "llm_api_key", "k")
    monkeypatch.setattr(agent.time, "sleep", lambda s: None)
    replies = [429, 429, 200]

    def fake_post(url, json=None, timeout=None, headers=None):
        code = replies.pop(0)
        body = {"choices": [{"message": {"content": "OK"}}]} if code == 200 else {"error": "rate"}
        return httpx.Response(code, json=body, headers={"retry-after": "1"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(agent.httpx, "post", fake_post)
    assert agent._chat({"model": "m", "messages": []})["content"] == "OK" and replies == []


def _llm(monkeypatch, final):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "llm_base_url", "https://api.sarvam.ai/v1")
    monkeypatch.setattr(cfg, "llm_api_key", "k")
    monkeypatch.setattr(cfg, "llm_model", "sarvam-105b")
    monkeypatch.setattr(agent, "_chat", lambda body: {"content": "ok"} if "tools" in body else {"content": json.dumps(final)})


def _final(diagnosis, send_after, conf, template="bank_issue_v1"):
    return {"diagnosis": diagnosis, "evidence": ["model evidence"],
            "options": [{"action": "retry_now", "verdict": "rejected", "why": "Rejected: x"},
                        {"action": "payment_link", "verdict": "chosen", "why": "Chosen: y"},
                        {"action": "ask_owner", "verdict": "rejected", "why": "Not needed: z"},
                        {"action": "no_action", "verdict": "rejected", "why": "Rejected: w"}],
            "chosen": {"action": "payment_link", "send_after": send_after, "template": template}, "confidence": conf}


def test_overconfident_model_that_disagrees_with_the_detector_goes_to_the_owner(db, monkeypatch):
    _llm(monkeypatch, _final("customer_side", "now", 0.99, "retry_later_v1"))
    with db.session() as s:
        seed.trigger_spike(s)   # Bank A outage: the detector says bank-side
        executor.tick(s)
        d = executor.latest_decision(s, "c_A118")
        assert d.confidence == 0.6 and "detector says bank-side" in d.evidence_json
        assert s.get(Case, "c_A118").state == "WAITING_OWNER"


def test_model_cannot_send_into_a_live_outage(db, monkeypatch):
    _llm(monkeypatch, _final("bank_side", "now", 0.95))
    from app.gateway import get_gateway
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        c = s.get(Case, "c_A118")
        assert c.state == "SCHEDULED" and c.stop_reason == "waiting_bank_recovery" and c.messages_sent == 0
    assert not get_gateway().links


def test_rules_trace_is_labelled_as_rules_not_model(db):
    with db.session() as s:
        seed.trigger_spike(s)
        executor.tick(s)
        trace = json.loads(executor.latest_decision(s, "c_A118").trace_json)
        assert {t["caller"] for t in trace} == {"rules"}
        from app import jobview
        steps = jobview.build(s, "c_A118", "fake")["steps"]
        ctx = [x for x in steps if x["title"] == "Context gathered"][0]
        assert ctx["detail"].startswith("rule reasoner looked up (no model)")
