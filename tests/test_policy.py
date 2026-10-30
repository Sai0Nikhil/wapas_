from app.models import Verdict
from app.services.policy import PolicyInput, evaluate


def test_allow():
    assert evaluate(PolicyInput(amount_paise=234_000, confidence=0.9)).verdict == Verdict.ALLOW


def test_above_limit_asks_owner():
    assert evaluate(PolicyInput(amount_paise=840_000, confidence=0.9)).verdict == Verdict.ASK_OWNER


def test_low_confidence_asks_owner():
    assert evaluate(PolicyInput(amount_paise=100_000, confidence=0.3)).verdict == Verdict.ASK_OWNER


def test_blocks():
    assert evaluate(PolicyInput(amount_paise=100, confidence=1, case_kind="refund")).verdict == Verdict.BLOCK
    assert evaluate(PolicyInput(amount_paise=100, confidence=1, opted_out=True)).verdict == Verdict.BLOCK
    assert evaluate(PolicyInput(amount_paise=100, confidence=1, reminder_count=2)).verdict == Verdict.BLOCK
    assert evaluate(PolicyInput(amount_paise=100, confidence=1, paytm_api_error=True)).verdict == Verdict.BLOCK


def test_fail_closed():
    assert evaluate(None).verdict == Verdict.BLOCK  # type: ignore[arg-type]
