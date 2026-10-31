"""Wapas server: API + owner app + background worker."""
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from . import approvals, auth, auth_api, evidence, executor, health, seed, store, telegram, voice
from .redact import install_logging_redaction, redact
from .models import Case, Payment
from .api import router
from .store import router as store_router
from .commerce import router as commerce_router
from .merchant_api import router as merchant_router
from .config import get_settings
from .db import engine, init_db, session
from .models import Customer
from .tenant_context import (DEFAULT_MERCHANT_ID, DEFAULT_STORE_ID, RequestIdentity, current_identity,
                             reset_identity, reset_merchant_id, reset_store_id, set_identity,
                             set_merchant_id, set_store_id)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
install_logging_redaction()
log = logging.getLogger("wapas")
STATIC = Path(__file__).parent / "static"
_stop = threading.Event()


def _worker():
    set_merchant_id(DEFAULT_MERCHANT_ID)
    set_store_id(DEFAULT_STORE_ID)
    tick = get_settings().worker_tick_seconds
    last_reconcile = 0.0
    health.WORKER["started"] = health.now_iso()
    while not _stop.is_set():
        try:
            pre = {}
            if get_settings().llm_enabled:  # model calls happen here, in parallel, without holding the lock
                with session() as s:
                    bundles = executor.pending_bundles(s)
                pre = executor.think(bundles)
            with executor.LOCK, session() as s:
                executor.tick(s, pre)
            health.WORKER["last_tick"], health.WORKER["ticks"] = health.now_iso(), health.WORKER["ticks"] + 1
            if time.monotonic() - last_reconcile > 20:  # orders whose callback never came
                last_reconcile = time.monotonic()
                health.WORKER["reconcile"] = store.reconcile()
                health.WORKER["last_reconcile"] = health.now_iso()
        except Exception as e:  # noqa: BLE001  (a bad tick must not kill the loop)
            health.WORKER["last_error"] = redact(f"{type(e).__name__}: {e}")[:200]
            log.exception("worker tick failed")
        _stop.wait(tick)


def _tg_decision(verb: str, case_id: str, token: str) -> str:
    """An owner button press. The token must be valid for the case's CURRENT decision and unexpired."""
    set_merchant_id(DEFAULT_MERCHANT_ID)
    set_store_id(DEFAULT_STORE_ID)
    with executor.LOCK, session() as s:
        dec = executor.latest_decision(s, case_id)
        ok, why = approvals.check(token, dec.id if dec else None)
        evidence.record(s, "owner_decision", {"verb": verb, "accepted": ok, "reason": why, "channel": "telegram"},
                        case_id=case_id, source="telegram-owner", ok=ok)
        if not ok:
            s.commit()
            return f"rejected: {why}"
        r = executor.owner_approve(s, case_id, via="Telegram") if verb == "ap" else executor.owner_skip(s, case_id, via="Telegram")
        s.commit()
        return r


def _tg_stop(case_id):
    set_merchant_id(DEFAULT_MERCHANT_ID)
    set_store_id(DEFAULT_STORE_ID)
    with executor.LOCK, session() as s:
        c = s.get(Case, case_id)
        n = executor.customer_stop(s, s.get(Payment, c.payment_id).customer_id) if c else 0
        s.commit()
        return n


def _tg_reply(case_id, text, audio_b64, mime):
    set_merchant_id(DEFAULT_MERCHANT_ID)
    set_store_id(DEFAULT_STORE_ID)
    stt = None
    if audio_b64 and get_settings().sarvam_enabled:
        import base64
        try:
            r = voice.transcribe_full(base64.b64decode(audio_b64), mime)
            text, stt = r["transcript"] or text, {"provider": "sarvam", "model": "saaras:v3", "language": r["language_code"]}
        except Exception as e:  # noqa: BLE001
            log.warning("customer voice note: %s", redact(e))
    if not (text or "").strip():
        return {"intent": "none"}
    with executor.LOCK, session() as s:
        r = executor.handle_reply(s, case_id, text, via="telegram", stt=stt)
        s.commit()
        return r


def _tg_question(text, audio_b64, mime):
    set_merchant_id(DEFAULT_MERCHANT_ID)
    set_store_id(DEFAULT_STORE_ID)
    with session() as s:
        return voice.ask(s, text, audio_b64, mime)


@asynccontextmanager
async def lifespan(app: FastAPI):
    executor.policy()  # fail closed: a bad policy file stops startup here
    # Validate the payment mode before init_db can alter any configured database.
    from .gateway import get_gateway
    get_gateway()
    init_db()
    if get_settings().app_env.lower() in {"development", "test"}:
        with session() as s:
            if not s.exec(select(Customer)).first():
                seed.seed(s)
    t = threading.Thread(target=_worker, daemon=True, name="wapas-worker")
    t.start()
    telegram.start(on_decision=_tg_decision, on_stop=_tg_stop, on_question=_tg_question, on_reply=_tg_reply)
    install_logging_redaction()  # again, now that uvicorn's own loggers exist
    log.info("Wapas up: gateway=%s llm=%s sarvam=%s", get_settings().gateway,
             get_settings().llm_enabled, get_settings().sarvam_enabled)
    yield
    _stop.set()


app = FastAPI(title="Wapas", lifespan=lifespan)

PUBLIC_PREFIXES = ("/s/", "/api/shop/", "/api/public/", "/api/paytm/", "/pay/",
                   "/fakecheckout/", "/static/", "/favicon.ico", "/api/demo/")
AUTH_PATHS = {"/api/auth/login", "/api/auth/session", "/api/auth/logout",
              "/api/auth/register", "/api/auth/memberships", "/api/auth/switch-membership"}
PROXY_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip", "cf-connecting-ip")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
STAFF_API_PREFIXES = ("/api/merchant/catalog/", "/api/merchant/orders", "/api/merchant/sarkar/ask",
                      "/api/merchant/sarkar/tools")


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin", "")
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host", "")).lower()
    if not origin or not host or request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return False
    try:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or (parsed.netloc.lower() != host and not parsed.netloc.lower().endswith(".vercel.app")):
            return False
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
            return False
        req_scheme = (request.headers.get("x-forwarded-proto") or request.url.scheme).lower()
        return parsed.scheme in {"http", "https"}
    except ValueError:
        return False


def _console_api(path: str) -> bool:
    return path.startswith("/api/") and path not in AUTH_PATHS and not path.startswith(PUBLIC_PREFIXES)


def _staff_allowed(path: str) -> bool:
    if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in STAFF_API_PREFIXES):
        return True
    return path == "/api/merchant/bills" or (
        path.startswith("/api/merchant/bills/") and "/khata" not in path
    )


def _secure_response(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(), microphone=(self)")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'",
    )
    if get_settings().app_env.lower() == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def identity_security_boundary(request: Request, call_next):
    path = request.url.path
    settings = get_settings()
    app_env = settings.app_env.lower()
    if path.startswith("/api/merchant/bills/") and "/input/" in path:
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        # Leave room for multipart headers while bounding uploads before FastAPI parses them.
        if content_length > 12 * 1024 * 1024 + 128 * 1024:
            return _secure_response(JSONResponse({"detail": "Counter upload is too large; audio is limited to 12 MB."}, status_code=413))
    is_public = path in {"/healthz", "/shop"} or path.startswith("/shop/") or any(
        path.startswith(prefix) for prefix in PUBLIC_PREFIXES
    )
    auth_endpoint = path in AUTH_PATHS
    raw_session = request.cookies.get(auth_api.SESSION_COOKIE, "")
    identity = auth.resolve_session(raw_session) if raw_session else None
    if path in {"/api/auth/login", "/api/auth/register"}:
        identity = None
    client_host = request.client.host if request.client else ""
    is_test_client = app_env == "test" and client_host == "testclient" and not any(
        header in request.headers for header in PROXY_HEADERS
    )
    tenant_token = store_token = identity_token = None

    if identity is not None:
        identity_token = set_identity(RequestIdentity(
            user_id=identity.user_id, username=identity.username, membership_id=identity.membership_id,
            merchant_id=identity.merchant_id, store_id=identity.store_id, role=identity.role,
            session_hash=identity.token_hash,
        ))
    elif is_test_client:
        # Test-only escape hatch. Test writes still need the legacy custom header so
        # request forgery behavior is exercised without provisioning a test login.
        tenant_token = set_merchant_id(DEFAULT_MERCHANT_ID)
        store_token = set_store_id(DEFAULT_STORE_ID)
    elif path != "/api/paytm/payment-callback" and path.startswith(("/api/shop/", "/api/paytm/", "/pay/", "/fakecheckout/", "/api/demo/")):
        # Legacy single-merchant recovery checkout and its provider callbacks use the
        # installation's one Paytm account. Slug-resolved Shop APIs do not use this.
        tenant_token = set_merchant_id(DEFAULT_MERCHANT_ID)
        store_token = set_store_id(DEFAULT_STORE_ID)

    try:
        if not is_public and not auth_endpoint and identity is None and not is_test_client:
            if path in {"/", "/login"}:
                return _secure_response(FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"}))
            if path.startswith("/api/"):
                return _secure_response(JSONResponse({"detail": "Sign in to access this merchant workspace"}, status_code=401))
            return _secure_response(FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"}))

        if identity is not None and identity.role != "OWNER" and _console_api(path) and not _staff_allowed(path):
            return _secure_response(JSONResponse({"detail": "This action is available to the store owner"}, status_code=403))

        if is_test_client and _console_api(path) and request.method not in SAFE_METHODS:
            if request.headers.get("sec-fetch-site", "").lower() == "cross-site" or request.headers.get("x-wapas-console") != "1":
                return _secure_response(JSONResponse({"detail": "A same-site console request is required"}, status_code=403))
        elif identity is not None and _console_api(path) and request.method not in SAFE_METHODS:
            csrf_valid = auth.csrf_pair_valid(
                identity, request.cookies.get(auth_api.CSRF_COOKIE),
                request.headers.get("x-wapas-csrf"), raw_session,
            )
            if not _same_origin(request) or not csrf_valid:
                return _secure_response(JSONResponse({"detail": "A valid same-origin session CSRF token is required"}, status_code=403))

        response = await call_next(request)
        return _secure_response(response)
    finally:
        if identity_token is not None:
            reset_identity(identity_token)
        if store_token is not None:
            reset_store_id(store_token)
        if tenant_token is not None:
            reset_merchant_id(tenant_token)


app.include_router(router)
app.include_router(auth_api.router)
app.include_router(store_router)
app.include_router(commerce_router)
app.include_router(merchant_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/healthz", include_in_schema=False)
def readiness():
    """Public, data-minimal readiness check for hosting health probes."""
    try:
        with engine().connect() as conn:
            conn.execute(text("SELECT 1")).scalar_one()

        last_tick = health.WORKER.get("last_tick")
        if not last_tick:
            raise RuntimeError("worker has not completed a tick")
        tick_at = datetime.fromisoformat(last_tick.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - tick_at).total_seconds()
        healthy_window = max(120.0, float(get_settings().worker_tick_seconds) * 5)
        if age < 0 or age > healthy_window:
            raise RuntimeError("worker heartbeat is stale")
    except Exception:  # health probes reveal state, never internal diagnostics
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return {"status": "ready"}


@app.get("/")
def index():
    if current_identity() is None and get_settings().app_env.lower() != "test":
        return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"})
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/login")
def login_page():
    if current_identity() is not None:
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"})
