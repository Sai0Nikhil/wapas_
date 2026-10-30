"""The owner's question, by voice or text, answered from the database.

Speech in: Sarvam speech-to-text (codemix mode). Speech out: Sarvam
text-to-speech. The answer text is built from counts, never free LLM text.
"""
import base64
import logging

import httpx
from sqlmodel import select

from .config import get_settings
from .models import Case, Outcome
from .ports import CaseState
from .templates import fmt_inr

log = logging.getLogger("wapas.voice")


def _fname(mime: str) -> str:
    m = (mime or "").lower()
    for key, ext in (("ogg", "ogg"), ("opus", "ogg"), ("mpeg", "mp3"), ("mp3", "mp3"), ("mp4", "m4a"), ("aac", "aac"),
                     ("wav", "wav"), ("webm", "webm")):
        if key in m:
            return f"question.{ext}"
    return "question.webm"


def transcribe_full(audio: bytes, mime: str) -> dict:
    """Sarvam's REST STT takes up to 30 s of audio (WebM from browsers and OGG/Opus from Telegram both work)."""
    cfg = get_settings()
    r = httpx.post(cfg.sarvam_base_url.rstrip("/") + "/speech-to-text", timeout=30.0,
                   headers={"api-subscription-key": cfg.sarvam_api_key},
                   files={"file": (_fname(mime), audio, mime or "audio/webm")},
                   data={"model": "saaras:v3", "mode": "codemix", "language_code": "unknown"})
    r.raise_for_status()
    j = r.json()
    return {"transcript": j.get("transcript", ""), "language_code": j.get("language_code") or ""}


def transcribe(audio: bytes, mime: str) -> str:
    return transcribe_full(audio, mime)["transcript"]


def speak(text: str, lang: str = "hi-IN") -> tuple[str | None, str]:
    """Returns (base64 audio, mime). MP3 first (plays on phones; Telegram's sendAudio needs MP3), then WAV.
    Sarvam's current TTS reference names the language field `language_code`; older docs said
    `target_language_code`, so that name is tried once if the first is rejected."""
    cfg = get_settings()
    url = cfg.sarvam_base_url.rstrip("/") + "/text-to-speech"
    headers = {"api-subscription-key": cfg.sarvam_api_key}
    for codec, mime in (("mp3", "audio/mpeg"), ("wav", "audio/wav")):
        for lang_field in ("language_code", "target_language_code"):
            body = {"text": text[:2400], lang_field: lang, "model": "bulbul:v3", "speaker": "shubh",
                    "output_audio_codec": codec}
            try:
                r = httpx.post(url, json=body, headers=headers, timeout=30.0)
            except Exception as e:  # noqa: BLE001
                log.warning("Sarvam TTS failed: %s", e)
                break
            if r.status_code < 400:
                audios = r.json().get("audios") or []
                if audios:
                    return audios[0], mime
                break
            log.warning("Sarvam TTS %s (%s): %s", r.status_code, lang_field, r.text[:200])
            if r.status_code not in (400, 422):
                break
    return None, ""


# Script ranges -> language, for typed questions (spoken ones come with Sarvam's language_code)
_SCRIPTS = (("te", 0x0C00, 0x0C7F), ("kn", 0x0C80, 0x0CFF), ("ta", 0x0B80, 0x0BFF), ("hi", 0x0900, 0x097F))


def detect_lang(text: str, stt_code: str = "") -> str:
    if stt_code:
        return stt_code.split("-")[0].lower()
    for code, lo, hi in _SCRIPTS:
        if any(lo <= ord(ch) <= hi for ch in text or ""):
            return code
    return "hi"


def intent(q: str) -> str:
    t = q.lower()
    if any(w in t for w in ["approval", "approve", "मंज़ूरी", "मंजूरी", "रुके", "waiting", "pending",
                            "అనుమతి", "ஒப்புதல்", "ಅನುಮೋದನೆ"]):
        return "approvals"
    if any(w in t for w in ["kyun", "क्यों", "why", "stop", "रोक", "block", "ఎందుకు", "ஏன்", "ಏಕೆ"]):
        return "stopped"
    return "total"


# Answers in Telugu, Tamil and Kannada (Hindi + English below). NEED A NATIVE-SPEAKER CHECK before the demo.
def _local(lang: str, kind: str, n: int, amount: str, w: int, k: int) -> str:
    if lang == "te":
        wait = ("1 పెద్ద మొత్తం మీ అనుమతి కోసం వేచి ఉంది." if w == 1 else f"{w} పెద్ద మొత్తాలు మీ అనుమతి కోసం వేచి ఉన్నాయి.") if w else "మీ అనుమతి కోసం ఏదీ వేచి లేదు."
        if kind == "approvals":
            return wait
        if kind == "stopped":
            return f"{k} కేసులను పాలసీ ఆపింది: ఆప్ట్-అవుట్, డూప్లికేట్ లేదా రిమైండర్ పరిమితి వల్ల."
        base = "ఈరోజు ఇంకా ఏ చెల్లింపూ తిరిగి రాలేదు." if n == 0 else (
            f"ఈరోజు 1 చెల్లింపు తిరిగి వచ్చింది, మొత్తం ₹{amount}, Paytm నిర్ధారించింది." if n == 1 else
            f"ఈరోజు {n} చెల్లింపులు తిరిగి వచ్చాయి, మొత్తం ₹{amount}, Paytm నిర్ధారించింది.")
        return base + (" " + wait if w else "")
    if lang == "ta":
        wait = ("1 பெரிய தொகை உங்கள் ஒப்புதலுக்காக காத்திருக்கிறது." if w == 1 else f"{w} பெரிய தொகைகள் உங்கள் ஒப்புதலுக்காக காத்திருக்கின்றன.") if w else "உங்கள் ஒப்புதலுக்காக எதுவும் காத்திருக்கவில்லை."
        if kind == "approvals":
            return wait
        if kind == "stopped":
            return f"{k} வழக்குகளை கொள்கை நிறுத்தியது: விலகல், நகல் அல்லது நினைவூட்டல் வரம்பு காரணமாக."
        base = "இன்று இதுவரை எந்த பணமும் திரும்ப வரவில்லை." if n == 0 else (
            f"இன்று 1 பணம் செலுத்தல் திரும்ப வந்தது, மொத்தம் ₹{amount}, Paytm உறுதிசெய்தது." if n == 1 else
            f"இன்று {n} பணம் செலுத்தல்கள் திரும்ப வந்தன, மொத்தம் ₹{amount}, Paytm உறுதிசெய்தது.")
        return base + (" " + wait if w else "")
    if lang == "kn":
        wait = ("1 ದೊಡ್ಡ ಮೊತ್ತ ನಿಮ್ಮ ಅನುಮೋದನೆಗಾಗಿ ಕಾಯುತ್ತಿದೆ." if w == 1 else f"{w} ದೊಡ್ಡ ಮೊತ್ತಗಳು ನಿಮ್ಮ ಅನುಮೋದನೆಗಾಗಿ ಕಾಯುತ್ತಿವೆ.") if w else "ನಿಮ್ಮ ಅನುಮೋದನೆಗಾಗಿ ಯಾವುದೂ ಕಾಯುತ್ತಿಲ್ಲ."
        if kind == "approvals":
            return wait
        if kind == "stopped":
            return f"{k} ಪ್ರಕರಣಗಳನ್ನು ನೀತಿ ನಿಲ್ಲಿಸಿದೆ: ಆಯ್ಕೆ ರದ್ದು, ನಕಲು ಅಥವಾ ಜ್ಞಾಪನೆ ಮಿತಿಯ ಕಾರಣ."
        base = "ಇಂದು ಇನ್ನೂ ಯಾವುದೇ ಪಾವತಿ ಹಿಂತಿರುಗಿಲ್ಲ." if n == 0 else (
            f"ಇಂದು 1 ಪಾವತಿ ಹಿಂತಿರುಗಿದೆ, ಒಟ್ಟು ₹{amount}, Paytm ದೃಢಪಡಿಸಿದೆ." if n == 1 else
            f"ಇಂದು {n} ಪಾವತಿಗಳು ಹಿಂತಿರುಗಿವೆ, ಒಟ್ಟು ₹{amount}, Paytm ದೃಢಪಡಿಸಿದೆ.")
        return base + (" " + wait if w else "")
    return ""


def answer(s, q: str, lang: str = "hi") -> dict:
    """Deterministic: counts come from the database (Paytm-verified outcomes only). No LLM writes these numbers."""
    live = s.exec(select(Case).where(Case.batch == "live")).all()
    ids = [c.id for c in live]
    outs = s.exec(select(Outcome).where(Outcome.case_id.in_(ids))).all() if ids else []
    from datetime import datetime, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).date()
    rec = [o for o in outs if o.result == "RECOVERED" and o.verified_at and
           (o.verified_at if o.verified_at.tzinfo else o.verified_at.replace(tzinfo=timezone.utc)).astimezone(ist).date() == today]
    total = sum(o.amount_paise for o in rec)
    waiting = [c for c in live if c.state == CaseState.WAITING_OWNER.value]
    stopped = [c for c in live if c.state in (CaseState.BLOCKED.value, CaseState.STOPPED.value)]
    kind = intent(q)
    w = len(waiting)
    wait_hi = "1 बड़ा amount आपकी approval के लिए रुका है।" if w == 1 else f"{w} बड़े amounts आपकी approval के लिए रुके हैं।"
    wait_en = "1 large amount is waiting for your approval." if w == 1 else f"{w} large amounts are waiting for your approval."
    n = len(rec)
    if kind == "approvals":
        hi = wait_hi if waiting else "अभी कोई approval बाकी नहीं है।"
        en = wait_en if waiting else "Nothing is waiting for your approval."
    elif kind == "stopped":
        hi = f"{len(stopped)} cases policy ने रोके: opt-out, duplicate या reminder limit की वजह से।"
        en = f"Policy stopped {len(stopped)} cases: opt-outs, duplicates or the reminder limit."
    else:
        if n == 0:
            hi, en = "आज अभी तक कोई payment वापस नहीं आया।", "No payments have come back yet today."
        else:
            hi = f"आज {n} payment{'s' if n > 1 else ''} वापस आ{'ए' if n > 1 else 'या'}, कुल ₹{fmt_inr(total)}, Paytm से confirm {'हुए' if n > 1 else 'हुआ'}।"
            en = f"Today {n} payment{'s' if n > 1 else ''} came back, ₹{fmt_inr(total)} in total, confirmed by Paytm."
        if waiting:
            hi += " " + wait_hi
            en += " " + wait_en
    local = _local(lang, kind, n, fmt_inr(total), w, len(stopped)) if lang in ("te", "ta", "kn") else ""
    return {"intent": kind, "answer_hi": hi, "answer_en": en, "answer_local": local, "language": lang}


def ask(s, text: str = "", audio_b64: str = "", mime: str = "") -> dict:
    """Owner question -> (Sarvam STT) -> answer from verified counts -> (Sarvam TTS in the asker's language).
    Returns a trace with provider, model, latency and any fallback, so the console shows what really ran."""
    import time as _time
    cfg = get_settings()
    q, stt_lang = text, ""
    trace = {"reasoning": "deterministic answer from Paytm-verified counts (no LLM)"}
    if audio_b64:
        if cfg.sarvam_enabled:
            t0 = _time.perf_counter()
            try:
                r = transcribe_full(base64.b64decode(audio_b64), mime)
                q, stt_lang = r["transcript"] or text, r["language_code"]
                trace["stt"] = {"provider": "sarvam", "model": "saaras:v3", "ok": True, "language": stt_lang,
                                "ms": round((_time.perf_counter() - t0) * 1000)}
            except Exception as e:  # noqa: BLE001
                log.warning("Sarvam STT failed: %s", e)
                trace["stt"] = {"provider": "sarvam", "model": "saaras:v3", "ok": False, "fallback": "typed text",
                                "ms": round((_time.perf_counter() - t0) * 1000)}
        else:
            trace["stt"] = {"provider": None, "ok": False, "fallback": "SARVAM_API_KEY not set: typed text only"}
    lang = detect_lang(q or "", stt_lang)
    out = answer(s, q or "", lang)
    out["question"] = q
    speak_text, speak_lang = (out["answer_local"], f"{lang}-IN") if out["answer_local"] else (out["answer_hi"], "hi-IN")
    if cfg.sarvam_enabled:
        t0 = _time.perf_counter()
        out["audio_b64"], out["audio_mime"] = speak(speak_text, speak_lang)
        trace["tts"] = {"provider": "sarvam", "model": "bulbul:v3", "language": speak_lang, "ok": bool(out["audio_b64"]),
                        "ms": round((_time.perf_counter() - t0) * 1000),
                        **({} if out["audio_b64"] else {"fallback": "browser speech"})}
    else:
        out["audio_b64"], out["audio_mime"] = None, ""
        trace["tts"] = {"provider": None, "ok": False, "fallback": "browser speech (SARVAM_API_KEY not set)"}
    out["trace"] = trace
    return out
