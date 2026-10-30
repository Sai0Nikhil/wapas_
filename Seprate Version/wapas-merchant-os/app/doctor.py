"""Integration doctor: every configured service is actually called, and every answer is labelled.

    python -m app.doctor            human-readable
    python -m app.doctor --json     machine-readable
    python -m app.doctor --deep     also: create a ₹1 Paytm test order (Initiate Transaction), ping n8n
    python -m app.doctor --send-test  also: send one test message to the owner's Telegram chat

Statuses:
  VERIFIED        the real service answered correctly just now
  DEGRADED        it answered, but something needed for the full flow is missing
  FAILED          it was called and refused / errored
  UNVERIFIED      configured, not exercised by this run
  NOT CONFIGURED  no credentials; the feature is off
  SIMULATED       an offline twin stands in (never presented as live)
"""
import base64
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

import httpx

from .config import get_settings
from .gateway import get_gateway
from .ports import PayStatus
from .redact import redact

LAST: dict = {"at": None, "results": []}


def _check(item: str, ok: bool | None, detail: str, ms: float | None = None) -> dict:
    return {"item": item, "ok": ok, "detail": redact(detail)[:240], "ms": round(ms) if ms is not None else None}


def _result(name: str, status: str, checks: list[dict], summary: str) -> dict:
    return {"name": name, "status": status, "summary": redact(summary)[:240], "checks": checks,
            "detail": redact(summary)[:240]}


def _t0() -> float:
    return time.perf_counter()


def _ms(t: float) -> float:
    return (time.perf_counter() - t) * 1000


# ------------------------------------------------------------------ Paytm
def check_paytm(deep: bool = False) -> dict:
    cfg = get_settings()
    if cfg.gateway != "paytm":
        return _result("Paytm", "SIMULATED", [_check("mode", None, "GATEWAY=fake: offline twin; nothing reaches Paytm")],
                       "Fake gateway (offline twin). Not Paytm.")
    checks = []
    if not (cfg.paytm_mid and cfg.paytm_merchant_key):
        return _result("Paytm", "NOT CONFIGURED", [_check("credentials", False, "PAYTM_MID / PAYTM_MERCHANT_KEY missing")],
                       "No Paytm credentials")
    checks.append(_check("credentials configured", True, f"MID ending …{cfg.paytm_mid[-4:]}"))
    from .gateway.checksum import generate_signature, verify_signature
    sig = generate_signature('{"probe":1}', cfg.paytm_merchant_key)
    checks.append(_check("signature self-test", verify_signature('{"probe":1}', cfg.paytm_merchant_key, sig),
                         "sign + verify round trip with your key"))
    t = _t0()
    try:
        st = get_gateway().order_status("WAPASDOCTOR0001")
    except Exception as e:  # noqa: BLE001
        checks.append(_check("status API + authentication", False, f"{type(e).__name__}: {e}", _ms(t)))
        return _result("Paytm", "FAILED", checks, "Paytm status API unreachable")
    info = (st.raw or {}).get("resultInfo", {}) if isinstance(st.raw, dict) else {}
    code = f"{info.get('resultCode', '')} {info.get('resultMsg') or info.get('resultMessage') or st.status.value}".strip()
    auth_ok = st.status == PayStatus.NOT_FOUND
    checks.append(_check("status API + authentication", auth_ok,
                         f"{cfg.paytm_host} accepted MID and signature (unknown order → not found, as expected)"
                         if auth_ok else f"Paytm answered {code}", _ms(t)))
    if not auth_ok:
        return _result("Paytm", "FAILED", checks, f"Paytm refused the credentials or the request: {code}")
    pub = cfg.public_base_url.rstrip("/")
    cb_ok = pub.startswith("https://") and "localhost" not in pub and "127.0.0.1" not in pub
    checks.append(_check("callback URL is public https", cb_ok,
                         pub if cb_ok else f"{pub}: Paytm only posts to a public https URL on 443 (use ngrok/cloudflared)"))
    if cb_ok:
        t = _t0()
        try:
            r = httpx.get(pub + "/api/shop/products", timeout=10)
            checks.append(_check("callback URL reaches this app", r.status_code == 200, f"GET {pub}/api/shop/products → HTTP {r.status_code}", _ms(t)))
        except Exception as e:  # noqa: BLE001
            checks.append(_check("callback URL reaches this app", False, f"{type(e).__name__}: {e}", _ms(t)))
    if deep:
        t = _t0()
        oid = f"WAPASDOC{int(time.time())}"
        res = get_gateway().initiate_checkout(order_id=oid, amount_paise=100, cust_id="wapas_doctor",
                                              callback_url=pub + "/api/paytm/txn-callback")
        checks.append(_check("checkout (Initiate Transaction, ₹1 test order)", bool(res.get("ok")),
                             f"txnToken issued for {oid}" if res.get("ok") else res.get("error", "failed"), _ms(t)))
        t = _t0()
        gw = get_gateway()
        ok, detail = gw.probe_links() if hasattr(gw, "probe_links") else (None, "adapter has no link probe")
        checks.append(_check("Payment Links enabled on this MID", ok, detail, _ms(t)))
    else:
        checks.append(_check("checkout (Initiate Transaction)", None, "not run; use --deep"))
        checks.append(_check("Payment Links enabled on this MID", None, "not run; use --deep"))
    flow = _latest_paytm_verification()
    checks.append(_check("end-to-end: a Paytm-confirmed payment", bool(flow), flow or
                         "UNVERIFIED: no payment has been confirmed by Paytm's status API yet"))
    failed = [c for c in checks if c["ok"] is False and not c["item"].startswith("end-to-end")]
    status = "VERIFIED" if not failed else ("DEGRADED" if all("callback" in c["item"] for c in failed) else "FAILED")
    not_enabled = [c["item"] for c in failed if "not enabled" in str(c["detail"])]
    if not_enabled:
        summary = "Credentials authenticated by Paytm; not enabled on this test MID yet: " + ", ".join(
            "checkout" if i.startswith("checkout") else "Payment Links" for i in not_enabled)
    else:
        summary = "Connected to Paytm test environment" + ("" if flow else "; payment flow not yet proven")
    return _result("Paytm", status, checks, summary)


def _latest_paytm_verification() -> str:
    """A credited recovery (Outcome RECOVERED) whose status check ran against real Paytm."""
    try:
        from sqlmodel import select
        from .db import session
        from .models import Evidence, Outcome
        with session() as s:
            outs = s.exec(select(Outcome).where(Outcome.result == "RECOVERED").order_by(Outcome.verified_at.desc()).limit(50)).all()
            for o in outs:
                e = s.exec(select(Evidence).where(Evidence.case_id == o.case_id, Evidence.kind == "status_check",
                                                  Evidence.environment.startswith("paytm"))).first()
                if e:
                    return f"verified {o.verified_at:%Y-%m-%d %H:%M} UTC, case {o.case_id}, txn {o.txn_id}"
    except Exception:  # noqa: BLE001
        return ""
    return ""


# ------------------------------------------------------------------ LLM
def check_llm() -> dict:
    cfg = get_settings()
    if not cfg.llm_enabled:
        return _result("LLM", "NOT CONFIGURED", [_check("config", None, "LLM_BASE_URL / LLM_API_KEY / LLM_MODEL empty")],
                       "Rule reasoner only (no LLM configured)")
    from .agent import _chat
    t = _t0()
    try:
        body = {"model": cfg.llm_model, "temperature": 0, "max_tokens": 300,
                "messages": [{"role": "user", "content": "Reply with the single word OK."}]}
        if "sarvam" in cfg.llm_base_url:
            body["reasoning_effort"] = None  # a ping; documented: null turns reasoning off
        m = _chat(body)
    except Exception as e:  # noqa: BLE001
        return _result("LLM", "FAILED", [_check("chat completion", False, f"{type(e).__name__}: {e}", _ms(t))], "LLM call failed")
    content = (m.get("content") or "").strip()
    ok = bool(content)
    return _result("LLM", "VERIFIED" if ok else "DEGRADED",
                   [_check("chat completion", ok, f"{cfg.llm_model} replied: {content[:20]!r}" if ok else
                           "empty content (reasoning may have used the token budget)", _ms(t))],
                   f"{cfg.llm_model} at {cfg.llm_base_url}")


# ------------------------------------------------------------------ Sarvam
def check_sarvam() -> dict:
    cfg = get_settings()
    if not cfg.sarvam_enabled:
        return _result("Sarvam voice", "NOT CONFIGURED", [_check("config", None, "SARVAM_API_KEY empty")],
                       "Text answers; the browser speaks them")
    from .voice import speak, transcribe
    checks = []
    t = _t0()
    audio, mime = speak("नमस्ते, आज दो भुगतान वापस आए।", "hi-IN")
    checks.append(_check("text-to-speech (Bulbul v3, hi-IN)", bool(audio), f"returned {mime}" if audio else "failed (see server log)", _ms(t)))
    if audio:
        t = _t0()
        try:
            text = transcribe(base64.b64decode(audio), mime)
            checks.append(_check("speech-to-text (Saaras v3) on that audio", bool(text), f"heard: {text[:60]!r}", _ms(t)))
        except Exception as e:  # noqa: BLE001
            checks.append(_check("speech-to-text (Saaras v3) on that audio", False, f"{type(e).__name__}: {e}", _ms(t)))
    oks = [c["ok"] for c in checks]
    status = "VERIFIED" if all(oks) else ("DEGRADED" if any(oks) else "FAILED")
    return _result("Sarvam voice", status, checks, "Round trip: speak Hindi, then transcribe it back")


# ------------------------------------------------------------------ Telegram
def check_telegram(send_test: bool = False) -> dict:
    cfg = get_settings()
    if not cfg.telegram_bot_token:
        return _result("Telegram", "NOT CONFIGURED", [_check("config", None, "TELEGRAM_BOT_TOKEN empty")],
                       "Owner channel off (console only)")
    checks = []
    t = _t0()
    try:
        r = httpx.get(f"https://api.telegram.org/bot{cfg.telegram_bot_token}/getMe", timeout=10).json()
    except Exception as e:  # noqa: BLE001
        return _result("Telegram", "FAILED", [_check("bot token (getMe)", False, f"{type(e).__name__}: {e}", _ms(t))], "Telegram unreachable")
    if not r.get("ok"):
        return _result("Telegram", "FAILED", [_check("bot token (getMe)", False, r.get("description", "bad token"), _ms(t))], "Bad bot token")
    checks.append(_check("bot token (getMe)", True, f"@{r['result'].get('username')}", _ms(t)))
    owner = cfg.telegram_owner_chat_id
    checks.append(_check("owner chat configured", bool(owner), "set" if owner else "TELEGRAM_OWNER_CHAT_ID empty"))
    if owner and owner.startswith("-"):
        checks.append(_check("owner user for a group chat", bool(cfg.telegram_owner_user_id),
                             "set" if cfg.telegram_owner_user_id else "group chat: set TELEGRAM_OWNER_USER_ID or nobody can approve"))
    checks.append(_check("demo customer chat configured", bool(cfg.telegram_customer_chat_id) or None,
                         "set" if cfg.telegram_customer_chat_id else "optional; customer messages stay in the console inbox"))
    if send_test and owner:
        t = _t0()
        try:
            s = httpx.post(f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage", timeout=10,
                           json={"chat_id": owner, "text": "Wapas doctor: owner channel test ✔"}).json()
            checks.append(_check("message send to owner", bool(s.get("ok")), "delivered" if s.get("ok") else s.get("description", ""), _ms(t)))
        except Exception as e:  # noqa: BLE001
            checks.append(_check("message send to owner", False, f"{type(e).__name__}: {e}", _ms(t)))
    else:
        from . import telegram
        last = telegram.STATUS.get("last_ok")
        checks.append(_check("message send to owner", True if last else None,
                             f"last successful send {last}" if last else "not exercised; use --send-test"))
    bad = [c for c in checks if c["ok"] is False]
    return _result("Telegram", "VERIFIED" if not bad else "DEGRADED", checks, "Owner channel (Telegram, not WhatsApp)")


# ------------------------------------------------------------------ n8n, database, worker
def check_n8n(deep: bool = False) -> dict:
    cfg = get_settings()
    if not cfg.n8n_webhook_url:
        return _result("n8n", "NOT CONFIGURED", [_check("config", None, "N8N_WEBHOOK_URL empty")], "Optional; off")
    if not deep:
        return _result("n8n", "UNVERIFIED", [_check("webhook", None, "configured; not pinged (use --deep)")], "Configured")
    t = _t0()
    try:
        r = httpx.post(cfg.n8n_webhook_url, json={"ping": True, "from": "wapas-doctor", "note": "connectivity check; ignore"}, timeout=10)
        ok = r.status_code < 400
        return _result("n8n", "VERIFIED" if ok else "FAILED", [_check("webhook", ok, f"HTTP {r.status_code}", _ms(t))], "n8n webhook")
    except Exception as e:  # noqa: BLE001
        return _result("n8n", "FAILED", [_check("webhook", False, f"{type(e).__name__}: {e}", _ms(t))], "n8n unreachable")


def check_database() -> dict:
    from sqlalchemy import inspect, text
    from sqlmodel import SQLModel
    from sqlalchemy.engine import make_url
    from .db import _sqlite_database_path, engine
    # Register all mapped tables without running init_db(), which is a mutating
    # startup/migration operation and does not belong in a diagnostic command.
    from . import (auth_models, billing_models, commerce_models, demand_models, khata_models,
                   merchant_os_models, models, rate_limit_models, sarkar_models, sound_models)  # noqa: F401
    cfg = get_settings()
    parsed = make_url(cfg.database_url)
    t = _t0()
    try:
        if parsed.get_backend_name() == "sqlite":
            path = _sqlite_database_path(cfg.database_url)
            if path is None:
                c = sqlite3.connect(":memory:")
                label = "in-memory SQLite"
            else:
                c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
                label = path.name
            try:
                c.execute("SELECT 1")
                tables = {row[0] for row in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                missing_tables = [tb.name for tb in SQLModel.metadata.sorted_tables if tb.name not in tables]
                missing = []
                for table in SQLModel.metadata.sorted_tables:
                    if table.name not in tables:
                        continue
                    identifier = table.name.replace('"', '""')
                    have = {row[1] for row in c.execute(f'PRAGMA table_info("{identifier}")')}
                    missing.extend(f"{table.name}.{col.name}" for col in table.columns if col.name not in have)
            finally:
                c.close()
        else:
            with engine().connect() as c:
                c.execute(text("SELECT 1"))
            insp = inspect(engine())
            missing = [f"{tb.name}.{col.name}" for tb in SQLModel.metadata.sorted_tables if insp.has_table(tb.name)
                       for col in tb.columns if col.name not in {c["name"] for c in insp.get_columns(tb.name)}]
            missing_tables = [tb.name for tb in SQLModel.metadata.sorted_tables if not insp.has_table(tb.name)]
            label = parsed.get_backend_name()
    except Exception as e:  # noqa: BLE001
        detail = redact(f"{type(e).__name__}: {e}")[:240]
        return _result("Database", "FAILED", [_check("read-only connection", False, detail, _ms(t))], "Database error")
    ok = not missing and not missing_tables
    return _result("Database", "VERIFIED" if ok else "DEGRADED",
                   [_check("read-only connection", True, label, _ms(t)),
                    _check("schema current", ok, "all tables and columns present" if ok else f"missing: {missing_tables + missing}")],
                   "Read-only database inspection; this command does not initialize or migrate the database")


def check_worker() -> dict:
    from .health import WORKER
    if not WORKER.get("started"):
        return _result("Worker", "UNVERIFIED", [_check("heartbeat", None, "not running in this process (run the server; see console)")],
                       "Background loop")
    last = WORKER.get("last_tick")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() if last else 1e9
    ok = age < max(10.0, 5 * get_settings().worker_tick_seconds)
    checks = [_check("heartbeat", ok, f"last tick {age:.0f} s ago, {WORKER.get('ticks')} ticks"),
              _check("reconciler", bool(WORKER.get("last_reconcile")) or None,
                     (f"last run {WORKER['last_reconcile'][11:19]} UTC · " +
                      ", ".join(f"{k} {v}" for k, v in (WORKER.get("reconcile") or {}).items()))
                     if WORKER.get("last_reconcile") else "not run yet")]
    if WORKER.get("last_error"):
        checks.append(_check("last error", False, WORKER["last_error"]))
    return _result("Worker", "VERIFIED" if ok else "DEGRADED", checks, "Decide → policy → act → verify loop")


def run_all(deep: bool = False, send_test: bool = False) -> list[dict]:
    res = [check_paytm(deep), check_llm(), check_sarvam(), check_telegram(send_test), check_n8n(deep),
           check_database(), check_worker()]
    LAST["at"], LAST["results"] = datetime.now(timezone.utc).isoformat(), res
    return res


def main(argv: list[str]) -> int:
    # The default Windows console encoding can be cp1252 while summaries contain
    # the rupee sign and Unicode arrows. Keep the human-readable CLI usable there.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    res = run_all(deep="--deep" in argv, send_test="--send-test" in argv)
    if "--json" in argv:
        print(json.dumps({"at": LAST["at"], "results": res}, ensure_ascii=False, indent=1))
    else:
        for r in res:
            print(f"{r['status']:>15}  {r['name']:<13} {r['summary']}")
            for c in r["checks"]:
                mark = {True: "ok ", False: "XX ", None: " - "}[c["ok"]]
                ms = f" ({c['ms']} ms)" if c.get("ms") is not None else ""
                print(f"{'':>17}{mark} {c['item']}: {c['detail']}{ms}")
    return 1 if any(r["status"] == "FAILED" for r in res) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
