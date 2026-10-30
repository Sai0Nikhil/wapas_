"""Guided key setup: you paste each key once (hidden), it is written to .env, then the live doctor runs.

    python -m app.setup_keys        (or double-click setup.bat on Windows)

Nothing here sends a key anywhere except to the service it belongs to, and no key is ever printed.
Telegram chat ids are found for you: send /start to your bot from each phone when asked.
"""
import getpass
import os
import re
import secrets
import shutil
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


# ------------------------------------------------------------------ .env editing (tested)
def read_env(path: Path) -> dict:
    vals = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*)$", line)
            if m:
                vals[m.group(1)] = m.group(2).strip()
    return vals


def update_env(path: Path, updates: dict) -> None:
    """Change only the given keys; keep every comment, blank line and other setting in place."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done = set()
    out = []
    for line in lines:
        m = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        if m and m.group(1) in updates:
            k = m.group(1)
            out.append(f"{k}={updates[k]}")
            done.add(k)
        else:
            out.append(line)
    missing = [k for k in updates if k not in done]
    if missing:
        out.append("")
        out.extend(f"{k}={updates[k]}" for k in missing)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------------ prompts
def ask(q: str, default: str = "") -> str:
    a = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
    return a or default


def yes(q: str, default: bool = True) -> bool:
    a = input(f"{q} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not a else a.startswith("y")


def secret(q: str, pattern: str | None = None, hint: str = "") -> str:
    while True:
        v = getpass.getpass(f"{q} (hidden, paste then Enter; blank to skip): ").strip()
        if not v or not pattern or re.fullmatch(pattern, v):
            return v
        print(f"  That does not look right{': ' + hint if hint else ''}. Try again.")


def _tg(token: str, method: str, **kw) -> dict:
    try:
        return httpx.post(f"https://api.telegram.org/bot{token}/{method}", json=kw, timeout=20).json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "description": type(e).__name__}


def _pick_chat(token: str, who: str) -> str:
    input(f"\n  On the {who} phone: open Telegram, find your bot, send /start. Then press Enter here...")
    upd = _tg(token, "getUpdates", timeout=0)
    chats = {}
    for u in upd.get("result", []):
        msg = u.get("message") or u.get("callback_query", {}).get("message") or {}
        c = msg.get("chat") or {}
        if c.get("id") is not None:
            name = c.get("title") or " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x) or c.get("username") or "?"
            chats[str(c["id"])] = name
    if not chats:
        print("  No messages seen yet. Send /start again, wait a few seconds.")
        return _pick_chat(token, who) if yes("  Try again?", True) else ""
    items = list(chats.items())
    for i, (cid, name) in enumerate(items, 1):
        print(f"   {i}. {name}  (chat id {cid})")
    n = ask(f"  Which one is the {who}? number", "1")
    try:
        return items[int(n) - 1][0]
    except (ValueError, IndexError):
        return ""


# ------------------------------------------------------------------ main
def main() -> int:
    print("\nWapas key setup. Keys are written to .env on this computer only and never printed.\n")
    if not ENV.exists():
        shutil.copy(EXAMPLE, ENV)
    cur = read_env(ENV)
    upd: dict[str, str] = {}

    print("1) PAYTM TEST KEYS  - Paytm dashboard > Developers > API Keys > Test mode")
    if yes("   Set up Paytm now?", not cur.get("PAYTM_MID")):
        mid = ask("   Test MID (letters and digits)", cur.get("PAYTM_MID", ""))
        key = secret("   Test merchant key", r"[\S]{8,64}", "8-64 characters, no spaces")
        if mid and (key or cur.get("PAYTM_MERCHANT_KEY")):
            upd["PAYTM_MID"] = mid
            if key:
                upd["PAYTM_MERCHANT_KEY"] = key
            upd["PAYTM_WEBSITE"] = cur.get("PAYTM_WEBSITE") or "WEBSTAGING"
            upd["GATEWAY"] = "paytm"
            print("   Paytm posts results only to a public https address (port 443).")
            print("   Start a tunnel in another window:  ngrok http 8000   (or: cloudflared tunnel --url http://localhost:8000)")
            url = ask("   Paste the https URL it shows (blank = later)", cur.get("PUBLIC_BASE_URL", "") if cur.get("PUBLIC_BASE_URL", "").startswith("https") else "")
            if url.startswith("https://"):
                upd["PUBLIC_BASE_URL"] = url.rstrip("/")
            elif url:
                print("   Not https; left unchanged. Paytm callbacks will not reach you until it is set.")

    print("\n2) SARVAM  - dashboard.sarvam.ai > API keys (one key powers the agent's brain AND voice)")
    if yes("   Set up Sarvam now?", not cur.get("SARVAM_API_KEY")):
        k = secret("   Sarvam API key", r"[\S]{10,200}", "no spaces")
        if k:
            upd["SARVAM_API_KEY"] = k
            if yes("   Also use Sarvam-105B as the agent's brain?", True):
                upd.update(LLM_BASE_URL="https://api.sarvam.ai/v1", LLM_API_KEY=k, LLM_MODEL="sarvam-105b")

    print("\n3) TELEGRAM  - in Telegram, message @BotFather, send /newbot, follow it, copy the token")
    if yes("   Set up Telegram now?", not cur.get("TELEGRAM_BOT_TOKEN")):
        tok = secret("   Bot token", r"\d{5,}:[A-Za-z0-9_-]{20,}", "looks like 123456789:ABC...")
        if tok:
            me = _tg(tok, "getMe")
            if not me.get("ok"):
                print(f"   Telegram refused that token ({me.get('description')}). Skipping Telegram.")
            else:
                print(f"   Bot OK: @{me['result'].get('username')}")
                _tg(tok, "deleteWebhook", drop_pending_updates=False)
                upd["TELEGRAM_BOT_TOKEN"] = tok
                owner = _pick_chat(tok, "OWNER")
                if owner:
                    upd["TELEGRAM_OWNER_CHAT_ID"] = owner
                if yes("   Add a second phone as the demo CUSTOMER?", True):
                    cust = _pick_chat(tok, "CUSTOMER")
                    if cust and cust != owner:
                        upd["TELEGRAM_CUSTOMER_CHAT_ID"] = cust
                    elif cust:
                        print("   That is the owner's chat; use a different phone/account for the customer.")

    if not cur.get("APPROVAL_SECRET"):
        upd["APPROVAL_SECRET"] = secrets.token_urlsafe(32)  # so approval buttons survive a restart

    if upd:
        update_env(ENV, upd)
        print(f"\nSaved {len(upd)} setting(s) to .env: " + ", ".join(sorted(upd)))
    else:
        print("\nNothing changed.")

    if yes("\nRun the live integration check now?", True):
        from . import config
        config.get_settings.cache_clear()
        from . import doctor
        return doctor.main([])
    return 0


if __name__ == "__main__":
    sys.exit(main())
