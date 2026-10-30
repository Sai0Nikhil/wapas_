"""Telegram: the OWNER channel (and, for the demo, a stand-in CUSTOMER phone).

Owner channel   : approval requests with signed Approve / Skip buttons, recovery
                  notes, and questions by text or voice (answered via Sarvam).
Customer channel: a second demo phone that receives exactly what a customer
                  would receive; replying STOP opts that customer out.
This is Telegram, not WhatsApp. Sends go through a queue on their own thread so
the recovery loop never waits on the network. Only the configured owner, pressing
a button whose signed token is valid for the case's current decision, can approve.
"""
import base64
import logging
import queue
import threading
from datetime import datetime, timezone

import httpx

from . import approvals
from .config import get_settings
from .redact import redact

log = logging.getLogger("wapas.telegram")
_out: "queue.Queue[tuple[str, dict, dict | None]]" = queue.Queue()
_msg_case: dict[int, str] = {}          # customer-chat message_id -> case_id (for STOP replies)
_last_case: list[str] = []
_threads_started = False
STATUS = {"last_ok": None, "last_error": "", "sent": 0, "polling": False}
STT_MAX_SECONDS = 30  # Sarvam's REST speech-to-text limit


def enabled() -> bool:
    return get_settings().telegram_enabled


def _url(method: str) -> str:
    return f"https://api.telegram.org/bot{get_settings().telegram_bot_token}/{method}"


def call(method: str, data: dict | None = None, files: dict | None = None, timeout: float = 15.0) -> dict:
    try:
        r = httpx.post(_url(method), data=data if files else None, json=None if files else (data or {}),
                       files=files, timeout=timeout)
        res = r.json()
        if res.get("ok"):
            STATUS["last_ok"], STATUS["sent"] = datetime.now(timezone.utc).isoformat(), STATUS["sent"] + 1
        else:
            STATUS["last_error"] = redact(f"{method}: {res.get('description', r.status_code)}")[:200]
        return res
    except Exception as exc:  # noqa: BLE001
        STATUS["last_error"] = redact(f"{method}: {type(exc).__name__}: {exc}")[:200]
        log.warning("telegram call %s failed: %s", method, redact(exc))
        return {"ok": False, "description": str(exc)}


# ------------------------------------------------------------------ outbound (queued)
def _enqueue(method: str, data: dict, meta: dict | None = None):
    if enabled():
        _out.put((method, data, meta))


def customer_message(case_id: str, name: str, language_name: str, text: str):
    chat = get_settings().telegram_customer_chat_id
    if chat:
        _enqueue("sendMessage", {"chat_id": chat, "text": f"[Demo customer phone] To {name} ({language_name}):\n\n{text}",
                                 "link_preview_options": {"is_disabled": True}}, {"case_id": case_id})


def owner_request(case_id: str, decision_id: int, *, customer: str, amount_fmt: str, why: str, proposal: str,
                  risk: str) -> None:
    """Approval request: what, how much, why it needs the owner, what Wapas proposes, the risk, and what
    happens if nobody answers. Buttons carry signed, expiring tokens bound to this decision."""
    cfg = get_settings()
    if not cfg.telegram_owner_chat_id:
        return
    ttl = cfg.approval_ttl_hours
    text = (f"{cfg.merchant_name} · needs your approval\n\n"
            f"Customer: {customer}\nAmount: ₹{amount_fmt}\n"
            f"Why you: {why}\nWapas proposes: {proposal}\nRisk: {risk}\n\n"
            f"Buttons expire in {ttl:g} h. If you do nothing, Wapas contacts nobody and closes the case.")
    kb = {"inline_keyboard": [[{"text": "Approve", "callback_data": approvals.make("ap", case_id, decision_id)},
                               {"text": "Skip", "callback_data": approvals.make("sk", case_id, decision_id)}]]}
    _enqueue("sendMessage", {"chat_id": cfg.telegram_owner_chat_id, "text": text, "reply_markup": kb})


def owner_note(text: str):
    chat = get_settings().telegram_owner_chat_id
    if chat:
        _enqueue("sendMessage", {"chat_id": chat, "text": text})


def _sender():
    while True:
        method, data, meta = _out.get()
        try:
            res = call(method, data)
            if meta and res.get("ok"):
                mid = res["result"]["message_id"]
                _msg_case[mid] = meta["case_id"]
                _last_case[:] = [meta["case_id"]]
            elif not res.get("ok"):
                log.warning("telegram %s failed: %s", method, redact(res.get("description")))
        except Exception as e:  # noqa: BLE001
            STATUS["last_error"] = redact(f"{type(e).__name__}: {e}")[:200]
            log.warning("telegram send error: %s", redact(e))


# ------------------------------------------------------------------ inbound (long polling)
def _is_owner(cq_or_msg: dict) -> bool:
    """The owner is a Telegram *user*. In a private chat the chat id equals the user id; in a
    group the owner's user id must be configured, or nobody can approve."""
    cfg = get_settings()
    chat = str(cq_or_msg.get("message", cq_or_msg).get("chat", {}).get("id", ""))
    frm = str(cq_or_msg.get("from", {}).get("id", ""))
    owner_chat = str(cfg.telegram_owner_chat_id)
    if not owner_chat or chat != owner_chat:
        return False
    owner_user = str(cfg.telegram_owner_user_id or (owner_chat if not owner_chat.startswith("-") else ""))
    return bool(owner_user) and frm == owner_user


def handle_update(u: dict, *, on_decision, on_stop, on_question, on_reply=None):
    """Dispatcher (unit-tested). on_decision(verb, case_id, token) does the token check against the DB."""
    cfg = get_settings()
    owner = str(cfg.telegram_owner_chat_id)
    cust = str(cfg.telegram_customer_chat_id)
    cq = u.get("callback_query")
    if cq:
        if not _is_owner(cq):
            call("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": "Only the owner can decide this."})
            return "ignored: not the owner"
        token = cq.get("data") or ""
        parsed = approvals.parse(token)
        if not parsed:
            call("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": "Unknown button."})
            return "ignored: malformed token"
        verb, case_id = parsed[0], parsed[1]
        state = on_decision(verb, case_id, token)
        word = "Approved" if verb == "ap" else "Skipped"
        rejected = str(state).startswith("rejected")
        call("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": state if rejected else word})
        m = cq.get("message", {})
        if m.get("message_id") and m.get("text"):
            note = f"\n\n→ Not applied: {state}" if rejected else f"\n\n→ {word} by owner ({state})"
            call("editMessageText", {"chat_id": m.get("chat", {}).get("id"), "message_id": m["message_id"],
                                     "text": (m.get("text") or "")[:3900] + note})
        return f"{verb}:{case_id}:{state}"
    msg = u.get("message") or {}
    chat = str(msg.get("chat", {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    if cust and chat == cust and chat != owner:
        ref = (msg.get("reply_to_message") or {}).get("message_id")
        case_id = _msg_case.get(ref) or (_last_case[0] if _last_case else "")
        if text.upper().startswith("STOP"):
            if case_id:
                n = on_stop(case_id)
                call("sendMessage", {"chat_id": chat, "text": "You will not receive more messages about this payment."})
                return f"stop:{case_id}:{n}"
            return "stop: no case"
        if case_id and on_reply and (text or msg.get("voice")):
            audio_b64, mime = "", ""
            voice = msg.get("voice")
            if voice:
                if int(voice.get("duration") or 0) > STT_MAX_SECONDS:
                    return "voice too long"
                f = call("getFile", {"file_id": voice["file_id"]})
                path = f.get("result", {}).get("file_path")
                if path:
                    raw = httpx.get(f"https://api.telegram.org/file/bot{cfg.telegram_bot_token}/{path}", timeout=30).content
                    audio_b64, mime = base64.b64encode(raw).decode(), voice.get("mime_type") or "audio/ogg"
            r = on_reply(case_id, text, audio_b64, mime)
            return f"reply:{case_id}:{r.get('intent')}"
        return "ignored: customer chat, no case"
    if chat == owner and _is_owner(msg):
        audio_b64, mime = "", ""
        voice = msg.get("voice")
        if voice:
            if int(voice.get("duration") or 0) > STT_MAX_SECONDS:
                call("sendMessage", {"chat_id": chat, "text": f"Please keep voice questions under {STT_MAX_SECONDS} seconds."})
                return "voice too long"
            f = call("getFile", {"file_id": voice["file_id"]})
            path = f.get("result", {}).get("file_path")
            if path:
                raw = httpx.get(f"https://api.telegram.org/file/bot{cfg.telegram_bot_token}/{path}", timeout=30).content
                audio_b64, mime = base64.b64encode(raw).decode(), voice.get("mime_type") or "audio/ogg"
        if not (text or audio_b64):
            return "ignored"
        if text.startswith("/start"):
            call("sendMessage", {"chat_id": chat, "text": "Wapas is watching your payments. Ask me anything, by text or voice."})
            return "start"
        ans = on_question(text, audio_b64, mime)
        reply = "\n".join(x for x in (ans.get("answer_local"), ans.get("answer_hi"), ans.get("answer_en")) if x)
        if ans.get("question") and audio_b64:
            reply = f"“{ans['question']}”\n\n" + reply
        call("sendMessage", {"chat_id": chat, "text": reply})
        if ans.get("audio_b64"):
            amime = ans.get("audio_mime") or ""
            raw = base64.b64decode(ans["audio_b64"])
            if "mpeg" in amime or "mp3" in amime:  # sendAudio takes MP3/M4A only
                call("sendAudio", {"chat_id": chat, "title": "Wapas"}, files={"audio": ("wapas.mp3", raw, "audio/mpeg")})
            else:
                call("sendDocument", {"chat_id": chat}, files={"document": ("wapas.wav", raw, amime or "audio/wav")})
        return "answered"
    return "ignored"


def _poller(on_decision, on_stop, on_question, on_reply=None):
    offset = 0
    try:  # getUpdates does not work while a webhook is set
        call("deleteWebhook", {"drop_pending_updates": False})
    except Exception as e:  # noqa: BLE001
        log.warning("telegram deleteWebhook: %s", redact(e))
    STATUS["polling"] = True
    backoff = 2.0
    while True:
        try:
            r = httpx.post(_url("getUpdates"), json={"offset": offset, "timeout": 25,
                                                     "allowed_updates": ["message", "callback_query"]},
                           timeout=35.0).json()
            if not r.get("ok"):
                STATUS["last_error"] = redact(f"getUpdates: {r.get('description')}")[:200]
                log.warning("telegram getUpdates refused: %s", redact(r.get("description")))
                threading.Event().wait(backoff)
                backoff = min(backoff * 2, 60.0)
                continue
            backoff = 2.0
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                try:
                    log.info("telegram: %s", handle_update(u, on_decision=on_decision, on_stop=on_stop,
                                                           on_question=on_question, on_reply=on_reply))
                except Exception:  # noqa: BLE001
                    log.exception("telegram update failed")
        except Exception as e:  # noqa: BLE001
            log.warning("telegram poll error: %s", redact(e))
            threading.Event().wait(backoff)
            backoff = min(backoff * 2, 60.0)


def start(on_decision, on_stop, on_question, on_reply=None):
    global _threads_started
    if _threads_started or not enabled():
        return
    _threads_started = True
    threading.Thread(target=_sender, daemon=True, name="tg-send").start()
    threading.Thread(target=_poller, args=(on_decision, on_stop, on_question, on_reply), daemon=True, name="tg-poll").start()
