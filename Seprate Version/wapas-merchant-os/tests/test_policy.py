from datetime import time
from pathlib import Path

import pytest

from app.policy import PolicyContext, PolicyError, evaluate, load_policy
from app.ports import Verdict

ROOT = Path(__file__).resolve().parent.parent
P = load_policy(ROOT / "policy.yaml")


def ctx(**kw):
    base = dict(action="payment_link", amount_paise=234000, confidence=0.9, opted_out=False,
                reminders_sent=0, recent_open_link_same_order=False, local_time=time(14, 0))
    base.update(kw)
    return PolicyContext(**base)


@pytest.mark.parametrize("kw,verdict,rule", [
    ({}, Verdict.ALLOW, "default_allow"),
    ({"opted_out": True}, Verdict.BLOCK, "opted_out"),
    ({"action": "refund"}, Verdict.BLOCK, "never_money_back"),
    ({"is_reminder": True, "reminders_sent": 2}, Verdict.BLOCK, "reminder_cap"),
    ({"recent_open_link_same_order": True}, Verdict.BLOCK, "duplicate"),
    ({"action": "retry_now"}, Verdict.BLOCK, "not_allowlisted"),
    ({"local_time": time(22, 30)}, Verdict.HOLD, "quiet_hours"),
    ({"local_time": time(8, 59)}, Verdict.HOLD, "quiet_hours"),
    ({"amount_paise": 840000}, Verdict.ASK_OWNER, "owner_amount"),
    ({"confidence": 0.5}, Verdict.ASK_OWNER, "owner_confidence"),
    ({"vip": True}, Verdict.ASK_OWNER, "owner_vip"),
    ({"amount_paise": 840000, "owner_approved": True}, Verdict.ALLOW, "default_allow"),
    ({"opted_out": True, "owner_approved": True}, Verdict.BLOCK, "opted_out"),
    ({"is_reminder": True, "reminders_sent": 1, "recent_open_link_same_order": True}, Verdict.ALLOW, "default_allow"),
])
def test_rules(kw, verdict, rule):
    d = evaluate(P, ctx(**kw))
    assert (d.verdict, d.rule) == (verdict, rule)


def test_first_match_wins_opt_out_beats_everything():
    d = evaluate(P, ctx(opted_out=True, action="refund", amount_paise=10**9))
    assert d.rule == "opted_out"


@pytest.mark.parametrize("patch", [
    lambda t: t + "\nsurprise: 1\n",
    lambda t: t.replace("allowed_actions: [payment_link, no_action]", "allowed_actions: [payment_link, refund]"),
    lambda t: t.replace("min_confidence: 0.80", "min_confidence: 3"),
    lambda t: t.replace("  max_reminders: 2\n", ""),
    lambda t: "::: not yaml",
])
def test_loader_fails_closed(tmp_path, patch):
    f = tmp_path / "p.yaml"
    f.write_text(patch((ROOT / "policy.yaml").read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(PolicyError):
        load_policy(f)


def test_setup_keys_updates_env_in_place_without_losing_comments(tmp_path, capsys):
    from app.setup_keys import read_env, update_env
    p = tmp_path / ".env"
    p.write_text("# Paytm\nPAYTM_MID=\nPAYTM_MERCHANT_KEY=\n\n# Tuning\nMERCHANT_NAME=Sharma Electronics\n", encoding="utf-8")
    update_env(p, {"PAYTM_MID": "TESTMID123", "PAYTM_MERCHANT_KEY": "s3cr3t-key-value", "GATEWAY": "paytm"})
    text = p.read_text(encoding="utf-8")
    assert "# Paytm" in text and "# Tuning" in text and "MERCHANT_NAME=Sharma Electronics" in text
    v = read_env(p)
    assert v["PAYTM_MID"] == "TESTMID123" and v["PAYTM_MERCHANT_KEY"] == "s3cr3t-key-value" and v["GATEWAY"] == "paytm"
    assert text.index("PAYTM_MID=TESTMID123") < text.index("# Tuning")  # edited in place, not appended
    assert "s3cr3t" not in capsys.readouterr().out                       # nothing printed
