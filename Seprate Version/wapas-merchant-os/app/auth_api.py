"""Browser login, membership selection, session inspection, and logout endpoints."""
from datetime import datetime, timezone
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import select

from . import auth
from .auth_models import MerchantMembership, User
from .db import session
from .models import Merchant, Store

router = APIRouter(prefix="/api/auth", tags=["authentication"])
SESSION_COOKIE = "wapas_session"
CSRF_COOKIE = "wapas_csrf"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)
    membership_id: str | None = Field(default=None, max_length=80)


class RegisterRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=120)
    store_name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=14, max_length=1024)
    phone: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    timezone: str = Field(default="Asia/Kolkata", max_length=50)


class SwitchMembershipRequest(BaseModel):
    membership_id: str = Field(min_length=1, max_length=80)


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin", "")
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host", "")).lower()
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        return (parsed.netloc.lower() == host or parsed.netloc.lower().endswith(".vercel.app") or "vercel" in parsed.netloc.lower())
    except ValueError:
        return False


def _secure_cookie() -> bool:
    configured_env = os.getenv("WAPAS_ENV")
    if configured_env:
        return configured_env.lower() == "production"
    try:
        from .config import get_settings
        return getattr(get_settings(), "app_env", os.getenv("WAPAS_ENV", "production")).lower() == "production"
    except Exception:  # noqa: BLE001
        return os.getenv("WAPAS_ENV", "production").lower() not in {"development", "test"}


def _set_login_cookies(response: Response, session_token: str, csrf_token: str,
                       expires_at: datetime) -> None:
    max_age = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(SESSION_COOKIE, session_token, max_age=max_age, expires=max_age,
                        httponly=True, secure=_secure_cookie(), samesite="strict", path="/")
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=max_age, expires=max_age,
                        httponly=False, secure=_secure_cookie(), samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _identity_payload(identity: auth.SessionIdentity, csrf_token: str) -> dict:
    return {
        "authenticated": True,
        "username": identity.username,
        "membership_id": identity.membership_id,
        "role": identity.role,
        "merchant_id": identity.merchant_id,
        "store_id": identity.store_id,
        "store_slug": identity.store_slug,
        "merchant_name": identity.merchant_name,
        "store_name": identity.store_name,
        "csrf_token": csrf_token,
        "expires_at": identity.expires_at.isoformat(),
    }


def _membership_payload(s, membership: MerchantMembership) -> dict:
    from .tenant_context import tenant_scope
    with tenant_scope(membership.merchant_id, membership.store_id):
        merchant = s.get(Merchant, membership.merchant_id)
        store = s.get(Store, membership.store_id)
        return {
            "id": membership.id,
            "merchant_id": membership.merchant_id,
            "merchant_name": merchant.name if merchant else "Merchant",
            "store_id": membership.store_id,
            "store_name": store.name if store else "Store",
            "store_slug": store.slug if store else "",
            "role": membership.role,
        }


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    if not _same_origin(request):
        raise HTTPException(403, "Sign-in request must come from this site")
    client_ip = request.client.host if request.client else "unknown"
    if auth.login_is_throttled(body.username, client_ip):
        raise HTTPException(429, "Unable to sign in right now. Wait a few minutes and try again.")

    try:
        username = auth.normalize_username(body.username)
    except ValueError:
        username = ""
    with session() as s:
        user = s.exec(select(User).where(User.username == username)).first() if username else None
        encoded = user.password_hash if user else auth._DUMMY_HASH
        password_ok = auth.verify_password(body.password, encoded)
        if user is None or not user.is_active or not password_ok:
            auth.record_login_failure(body.username, client_ip)
            raise HTTPException(401, "Username or password is incorrect")
        memberships = s.exec(select(MerchantMembership).where(
            MerchantMembership.user_id == user.id, MerchantMembership.is_active == True,  # noqa: E712
        ).order_by(MerchantMembership.merchant_id, MerchantMembership.store_id)).all()
        if not memberships:
            auth.record_login_failure(body.username, client_ip)
            raise HTTPException(401, "Username or password is incorrect")
        auth.clear_login_failures(body.username, client_ip)
        if body.membership_id:
            membership = next((m for m in memberships if m.id == body.membership_id), None)
            if membership is None:
                raise HTTPException(401, "Username or password is incorrect")
        elif len(memberships) == 1:
            membership = memberships[0]
        else:
            return {
                "authenticated": False,
                "needs_membership_selection": True,
                "memberships": [_membership_payload(s, item) for item in memberships],
            }
        payload = {
            "user_id": user.id,
            "username": user.username,
            "membership_id": membership.id,
            "merchant_id": membership.merchant_id,
            "store_id": membership.store_id,
            "role": membership.role,
        }

    raw_session, csrf, expires_at = auth.create_session(payload["membership_id"])
    identity = auth.resolve_session(raw_session)
    if identity is None:
        raise HTTPException(500, "Could not establish a sign-in session")
    _set_login_cookies(response, raw_session, csrf, expires_at)
    payload.update({"authenticated": True, "store_slug": identity.store_slug,
                    "merchant_name": identity.merchant_name, "store_name": identity.store_name,
                    "csrf_token": csrf, "expires_at": expires_at.isoformat()})
    return payload


@router.get("/session")
def current_session(request: Request, response: Response):
    raw_session = request.cookies.get(SESSION_COOKIE, "")
    identity = auth.resolve_session(raw_session)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    if identity is None:
        return {"authenticated": False}
    csrf = request.cookies.get(CSRF_COOKIE, "")
    if not auth.session_csrf_valid(identity, raw_session, csrf):
        csrf = auth.rotate_session_csrf(raw_session) or ""
        identity = auth.resolve_session(raw_session)
        if identity is None or not csrf:
            raise HTTPException(401, "Sign-in session expired")
        _set_login_cookies(response, raw_session, csrf, identity.expires_at)
    return _identity_payload(identity, csrf)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    raw_session = request.cookies.get(SESSION_COOKIE, "")
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("x-wapas-csrf", "")
    identity = auth.resolve_session(raw_session)
    if identity is not None and not auth.csrf_pair_valid(identity, csrf_cookie, csrf_header, raw_session):
        raise HTTPException(403, "A valid session CSRF token is required")
    auth.revoke_session(raw_session)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=_secure_cookie(), samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", httponly=False, secure=_secure_cookie(), samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 204
    return response


@router.post("/register", status_code=201)
def register(body: RegisterRequest, request: Request, response: Response):
    if not _same_origin(request):
        raise HTTPException(403, "Registration request must come from this site")
    client_ip = request.client.host if request.client else "unknown"
    if auth.login_is_throttled(body.username, client_ip):
        raise HTTPException(429, "Too many requests. Please wait a few minutes.")

    try:
        user, membership, merchant, store = auth.create_merchant_with_owner(
            business_name=body.business_name,
            store_name=body.store_name,
            username=body.username,
            password=body.password,
            timezone=body.timezone,
            phone=body.phone,
            city=body.city,
        )
    except ValueError as exc:
        msg = str(exc)
        if "Username is already in use" in msg:
            raise HTTPException(409, msg) from exc
        raise HTTPException(400, msg) from exc

    raw_session, csrf, expires_at = auth.create_session(membership.id)
    identity = auth.resolve_session(raw_session)
    if identity is None:
        raise HTTPException(500, "Could not establish a sign-in session")
    _set_login_cookies(response, raw_session, csrf, expires_at)
    payload = {
        "authenticated": True,
        "user_id": user.id,
        "username": user.username,
        "membership_id": membership.id,
        "merchant_id": membership.merchant_id,
        "store_id": membership.store_id,
        "store_slug": identity.store_slug,
        "merchant_name": identity.merchant_name,
        "store_name": identity.store_name,
        "role": membership.role,
        "csrf_token": csrf,
        "expires_at": expires_at.isoformat(),
    }
    return payload


@router.get("/memberships")
def current_memberships(request: Request):
    raw_session = request.cookies.get(SESSION_COOKIE, "")
    identity = auth.resolve_session(raw_session)
    if identity is None:
        raise HTTPException(401, "Sign in to view memberships")
    with session() as s:
        memberships = s.exec(select(MerchantMembership).where(
            MerchantMembership.user_id == identity.user_id,
            MerchantMembership.is_active == True,
        ).order_by(MerchantMembership.created_at)).all()
        return {"memberships": [_membership_payload(s, item) for item in memberships]}


@router.post("/switch-membership")
def switch_membership(body: SwitchMembershipRequest, request: Request, response: Response):
    if not _same_origin(request):
        raise HTTPException(403, "Membership switch request must come from this site")
    raw_session = request.cookies.get(SESSION_COOKIE, "")
    identity = auth.resolve_session(raw_session)
    if identity is None:
        raise HTTPException(401, "Sign in to switch store membership")
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("x-wapas-csrf", "")
    if not auth.csrf_pair_valid(identity, csrf_cookie, csrf_header, raw_session):
        raise HTTPException(403, "A valid session CSRF token is required")

    with session() as s:
        target_membership = s.get(MerchantMembership, body.membership_id)
        if target_membership is None or not target_membership.is_active or target_membership.user_id != identity.user_id:
            raise HTTPException(404, "Target membership not found or not active for this user")
        user = s.get(User, identity.user_id)
        if user is None or not user.is_active:
            raise HTTPException(401, "User is inactive")
        payload = {
            "user_id": user.id,
            "username": user.username,
            "membership_id": target_membership.id,
            "merchant_id": target_membership.merchant_id,
            "store_id": target_membership.store_id,
            "role": target_membership.role,
        }

    auth.revoke_session(raw_session)
    new_raw_session, new_csrf, expires_at = auth.create_session(payload["membership_id"])
    new_identity = auth.resolve_session(new_raw_session)
    if new_identity is None:
        raise HTTPException(500, "Could not establish switch session")
    _set_login_cookies(response, new_raw_session, new_csrf, expires_at)
    payload.update({
        "authenticated": True,
        "store_slug": new_identity.store_slug,
        "merchant_name": new_identity.merchant_name,
        "store_name": new_identity.store_name,
        "csrf_token": new_csrf,
        "expires_at": expires_at.isoformat(),
    })
    return payload

