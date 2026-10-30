"""Password hashing, membership resolution, sessions, and durable login throttling."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address

from sqlmodel import select

from .db import session
from .models import Merchant, Store
from .auth_models import AuthSession, LoginThrottle, MerchantMembership, User

SESSION_TTL = timedelta(hours=12)
PASSWORD_MIN_LENGTH = 14
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@+-]{2,119}$")
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 2**14, 8, 1, 64
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_LOCKOUT = timedelta(minutes=15)
LOGIN_FAILURE_LIMIT = 5


@dataclass(frozen=True)
class SessionIdentity:
    user_id: str
    username: str
    membership_id: str
    merchant_id: str
    store_id: str
    store_slug: str
    merchant_name: str
    store_name: str
    role: str
    token_hash: str
    csrf_hash: str
    expires_at: datetime


def normalize_username(value: str) -> str:
    username = (value or "").strip().casefold()
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Username must be 3–120 characters using letters, numbers, dot, underscore, @, +, or hyphen")
    return username


def validate_password(value: str) -> str:
    if not isinstance(value, str) or len(value) < PASSWORD_MIN_LENGTH or len(value) > 1024:
        raise ValueError(f"Password must be between {PASSWORD_MIN_LENGTH} and 1024 characters")
    if not (any(c.isalpha() for c in value) and any(not c.isalpha() for c in value)):
        raise ValueError("Password must include letters and numbers or symbols")
    return value


def hash_password(password: str) -> str:
    value = validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(value.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                            dklen=SCRYPT_DKLEN, maxmem=64 * 1024 * 1024)
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or not password or len(password) > 1024:
        return False
    try:
        algorithm, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        if n < 2**14 or n > 2**18 or r < 1 or r > 16 or p < 1 or p > 4:
            return False
        salt = base64.urlsafe_b64decode(salt_raw + "=" * (-len(salt_raw) % 4))
        expected = base64.urlsafe_b64decode(digest_raw + "=" * (-len(digest_raw) % 4))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                                dklen=len(expected), maxmem=128 * 1024 * 1024)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError, MemoryError):
        return False


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _dummy_password_hash() -> str:
    # Pay the same password-verification cost when a username is not present.
    return hash_password("dummy-login-timing-value-which-is-never-valid")


_DUMMY_HASH = _dummy_password_hash()


def create_user_membership(*, username: str, password: str, merchant_id: str, store_id: str,
                           role: str = "OWNER") -> tuple[User, MerchantMembership]:
    """Provision a user and one membership. Does not commit; caller owns the transaction."""
    normalized = normalize_username(username)
    password_hash = hash_password(password)
    role = role.upper()
    if role not in {"OWNER", "STAFF"}:
        raise ValueError("Role must be OWNER or STAFF")
    with session() as s:
        if s.exec(select(User).where(User.username == normalized)).first():
            raise ValueError("Username is already in use")
        merchant = s.get(Merchant, merchant_id)
        store = s.get(Store, store_id)
        if merchant is None or store is None or store.merchant_id != merchant_id:
            raise ValueError("Merchant and store must exist and belong together")
        user = User(username=normalized, password_hash=password_hash)
        s.add(user)
        s.flush()
        membership = MerchantMembership(user_id=user.id, merchant_id=merchant_id,
                                        store_id=store_id, role=role)
        s.add(membership)
        s.commit()
        s.refresh(user)
        s.refresh(membership)
        return user, membership


def create_merchant_with_owner(
    *,
    business_name: str,
    store_name: str,
    username: str,
    password: str,
    timezone: str = "Asia/Kolkata",
    phone: str | None = None,
    city: str | None = None,
) -> tuple[User, MerchantMembership, Merchant, Store]:
    """Create a new tenant: Merchant, Store with unique slug, User, and OWNER membership."""
    clean_business = (business_name or "").strip()
    if len(clean_business) < 2 or len(clean_business) > 120:
        raise ValueError("Business name must be between 2 and 120 characters")
    clean_store = (store_name or "").strip()
    if len(clean_store) < 2 or len(clean_store) > 120:
        raise ValueError("Store name must be between 2 and 120 characters")

    normalized_username = normalize_username(username)
    validate_password(password)
    password_hash = hash_password(password)

    raw_slug = re.sub(r"[^a-z0-9]+", "-", clean_store.lower()).strip("-")
    base_slug = raw_slug if len(raw_slug) >= 3 else "store"

    with session() as s:
        if s.exec(select(User).where(User.username == normalized_username)).first():
            raise ValueError("Username is already in use")

        candidate_slug = base_slug
        while s.exec(select(Store).where(Store.slug == candidate_slug)).first():
            candidate_slug = f"{base_slug}-{secrets.token_hex(2)}"

        merchant_id = "mer_" + secrets.token_hex(8)
        store_id = "sto_" + secrets.token_hex(8)

        merchant = Merchant(id=merchant_id, name=clean_business)
        s.add(merchant)
        s.flush()

        store = Store(
            id=store_id,
            merchant_id=merchant.id,
            name=clean_store,
            slug=candidate_slug,
            timezone=timezone,
        )
        s.add(store)
        s.flush()

        user = User(username=normalized_username, password_hash=password_hash)
        s.add(user)
        s.flush()

        membership = MerchantMembership(
            user_id=user.id,
            merchant_id=merchant.id,
            store_id=store.id,
            role="OWNER",
        )
        s.add(membership)
        s.flush()

        from . import audit
        audit.record(
            s,
            action="MERCHANT_REGISTERED",
            entity_type="merchant",
            entity_id=merchant.id,
            merchant_id=merchant.id,
            store_id=store.id,
            actor_type="user",
            actor_id=user.id,
            source="self_serve_onboarding",
            payload={
                "business_name": merchant.name,
                "store_name": store.name,
                "store_slug": store.slug,
                "username": user.username,
                "phone": phone,
                "city": city,
            },
        )
        s.commit()
        s.refresh(merchant)
        s.refresh(store)
        s.refresh(user)
        s.refresh(membership)
        return user, membership, merchant, store


def revoke_all_sessions_for_membership(membership_id: str) -> int:
    """Revoke all active sessions for a given membership."""
    with session() as s:
        sessions = s.exec(select(AuthSession).where(
            AuthSession.membership_id == membership_id,
            AuthSession.revoked_at.is_(None),
        )).all()
        now_dt = datetime.now(timezone.utc)
        count = 0
        for item in sessions:
            item.revoked_at = now_dt
            s.add(item)
            count += 1
        s.commit()
        return count


def list_store_members(merchant_id: str, store_id: str) -> list[dict]:
    with session() as s:
        memberships = s.exec(
            select(MerchantMembership)
            .where(
                MerchantMembership.merchant_id == merchant_id,
                MerchantMembership.store_id == store_id,
            )
            .order_by(MerchantMembership.created_at)
        ).all()
        result = []
        for m in memberships:
            user = s.get(User, m.user_id)
            result.append({
                "membership_id": m.id,
                "user_id": m.user_id,
                "username": user.username if user else "",
                "role": m.role,
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat(),
            })
        return result


def create_staff_membership(
    *,
    username: str,
    password: str,
    merchant_id: str,
    store_id: str,
    role: str = "STAFF",
    actor_id: str = "",
) -> tuple[User, MerchantMembership]:
    normalized = normalize_username(username)
    validate_password(password)
    password_hash = hash_password(password)
    role = role.upper()
    if role not in {"OWNER", "STAFF"}:
        raise ValueError("Role must be OWNER or STAFF")

    with session() as s:
        merchant = s.get(Merchant, merchant_id)
        store = s.get(Store, store_id)
        if merchant is None or store is None or store.merchant_id != merchant_id:
            raise ValueError("Merchant and store must exist and belong together")

        user = s.exec(select(User).where(User.username == normalized)).first()
        if user is None:
            user = User(username=normalized, password_hash=password_hash)
            s.add(user)
            s.flush()
        else:
            existing = s.exec(select(MerchantMembership).where(
                MerchantMembership.user_id == user.id,
                MerchantMembership.merchant_id == merchant_id,
                MerchantMembership.store_id == store_id,
            )).first()
            if existing:
                raise ValueError("User is already a member of this store")

        membership = MerchantMembership(
            user_id=user.id,
            merchant_id=merchant_id,
            store_id=store_id,
            role=role,
            is_active=True,
        )
        s.add(membership)
        s.flush()

        from . import audit
        audit.record(
            s,
            action="STAFF_MEMBER_CREATED",
            entity_type="membership",
            entity_id=membership.id,
            merchant_id=merchant_id,
            store_id=store_id,
            actor_type="user",
            actor_id=actor_id,
            source="merchant_staff_admin",
            payload={"username": user.username, "role": role},
        )
        s.commit()
        s.refresh(user)
        s.refresh(membership)
        return user, membership


def update_store_membership(
    *,
    membership_id: str,
    merchant_id: str,
    store_id: str,
    is_active: bool | None = None,
    role: str | None = None,
    actor_id: str = "",
) -> MerchantMembership:
    with session() as s:
        membership = s.get(MerchantMembership, membership_id)
        if membership is None or membership.merchant_id != merchant_id or membership.store_id != store_id:
            raise ValueError("Membership not found for this store")

        target_role = (role.upper() if role else membership.role)
        target_active = is_active if is_active is not None else membership.is_active

        if target_role not in {"OWNER", "STAFF"}:
            raise ValueError("Role must be OWNER or STAFF")

        if membership.role == "OWNER" and (target_role != "OWNER" or not target_active):
            active_owners = s.exec(select(MerchantMembership).where(
                MerchantMembership.merchant_id == merchant_id,
                MerchantMembership.store_id == store_id,
                MerchantMembership.role == "OWNER",
                MerchantMembership.is_active == True,
                MerchantMembership.id != membership.id,
            )).all()
            if not active_owners:
                raise ValueError("Cannot deactivate or demote the only active owner of this store")

        membership.is_active = target_active
        membership.role = target_role
        s.add(membership)
        s.flush()

        from . import audit
        audit.record(
            s,
            action="STAFF_MEMBER_UPDATED",
            entity_type="membership",
            entity_id=membership.id,
            merchant_id=merchant_id,
            store_id=store_id,
            actor_type="user",
            actor_id=actor_id,
            source="merchant_staff_admin",
            payload={"role": membership.role, "is_active": membership.is_active},
        )
        s.commit()
        s.refresh(membership)

        if not membership.is_active:
            revoke_all_sessions_for_membership(membership.id)

        return membership


def create_session(membership_id: str) -> tuple[str, str, datetime]:
    """Create a random browser token and CSRF secret; persist only their SHA-256 digests."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_TTL
    with session() as s:
        membership = s.get(MerchantMembership, membership_id)
        if membership is None or not membership.is_active:
            raise ValueError("Membership is not active")
        user = s.get(User, membership.user_id)
        if user is None or not user.is_active:
            raise ValueError("Membership is not active")
        from .tenant_context import tenant_scope
        with tenant_scope(membership.merchant_id, membership.store_id):
            store = s.get(Store, membership.store_id)
            if store is None or store.merchant_id != membership.merchant_id:
                raise ValueError("Membership is not active")
        s.add(AuthSession(token_hash=_sha256(token), csrf_hash=_sha256(csrf),
                          membership_id=membership.id, expires_at=expires_at))
        s.commit()
    return token, csrf, expires_at


def resolve_session(token: str | None) -> SessionIdentity | None:
    """Resolve a bearer cookie into server-owned identity and role context."""
    if not token or len(token) > 256:
        return None
    token_hash = _sha256(token)
    now = datetime.now(timezone.utc)
    with session() as s:
        auth_session = s.get(AuthSession, token_hash)
        if (auth_session is None or auth_session.revoked_at is not None
                or _aware(auth_session.expires_at) <= now):
            return None
        membership = s.get(MerchantMembership, auth_session.membership_id)
        if membership is None or not membership.is_active:
            return None
        user = s.get(User, membership.user_id)
        if user is None or not user.is_active:
            return None
        merchant = s.get(Merchant, membership.merchant_id)
        if merchant is None:
            return None
        from .tenant_context import tenant_scope
        with tenant_scope(membership.merchant_id, membership.store_id):
            store = s.get(Store, membership.store_id)
            if store is None or store.merchant_id != membership.merchant_id:
                return None
        return SessionIdentity(user_id=user.id, username=user.username, membership_id=membership.id,
                               merchant_id=membership.merchant_id, store_id=membership.store_id,
                               store_slug=store.slug, merchant_name=merchant.name, store_name=store.name,
                               role=membership.role, token_hash=auth_session.token_hash,
                               csrf_hash=auth_session.csrf_hash, expires_at=_aware(auth_session.expires_at))


def _aware(value: datetime) -> datetime:
    # SQLite returns naive datetimes even when the model was populated with UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def session_csrf_valid(identity: SessionIdentity | None, raw_session_token: str | None,
                       csrf_token: str | None) -> bool:
    if (identity is None or not raw_session_token or not csrf_token or len(csrf_token) > 256
            or not hmac.compare_digest(identity.token_hash, _sha256(raw_session_token))):
        return False
    return hmac.compare_digest(identity.csrf_hash, _sha256(csrf_token))


def csrf_pair_valid(identity: SessionIdentity | None, cookie_token: str | None,
                    header_token: str | None, raw_session_token: str | None = None) -> bool:
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        return False
    return session_csrf_valid(identity, raw_session_token, header_token)


def rotate_session_csrf(raw_session_token: str | None) -> str | None:
    if not raw_session_token or len(raw_session_token) > 256:
        return None
    now = datetime.now(timezone.utc)
    with session() as s:
        auth_session = s.get(AuthSession, _sha256(raw_session_token))
        if auth_session is None or auth_session.revoked_at is not None or _aware(auth_session.expires_at) <= now:
            return None
        token = secrets.token_urlsafe(32)
        auth_session.csrf_hash = _sha256(token)
        s.add(auth_session)
        s.commit()
        return token


def revoke_session(token: str | None) -> bool:
    if not token or len(token) > 256:
        return False
    with session() as s:
        auth_session = s.get(AuthSession, _sha256(token))
        if auth_session is None or auth_session.revoked_at is not None:
            return False
        auth_session.revoked_at = datetime.now(timezone.utc)
        s.add(auth_session)
        s.commit()
        return True


def _throttle_hash(kind: str, value: str) -> str:
    return _sha256(f"wapas-login-throttle:{kind}:{value}")


def login_throttle_keys(username: str, client_ip: str) -> tuple[str, str]:
    normalized = (username or "").strip().casefold()[:120]
    try:
        address = ip_address(client_ip).compressed
    except ValueError:
        address = "unknown"
    return _throttle_hash("user", normalized), _throttle_hash("ip", address)


def login_is_throttled(username: str, client_ip: str) -> bool:
    keys = login_throttle_keys(username, client_ip)
    now = datetime.now(timezone.utc)
    with session() as s:
        records = s.exec(select(LoginThrottle).where(LoginThrottle.attempt_hash.in_(keys))).all()
        return any(row.blocked_until is not None and _aware(row.blocked_until) > now for row in records)


def record_login_failure(username: str, client_ip: str) -> None:
    keys = login_throttle_keys(username, client_ip)
    now = datetime.now(timezone.utc)
    with session() as s:
        for key in keys:
            row = s.get(LoginThrottle, key)
            if row is None:
                row = LoginThrottle(attempt_hash=key, failures=1, window_started_at=now,
                                    updated_at=now)
            else:
                started = _aware(row.window_started_at)
                if now - started > LOGIN_WINDOW:
                    row.failures, row.window_started_at = 1, now
                    row.blocked_until = None
                else:
                    row.failures += 1
                if row.failures >= LOGIN_FAILURE_LIMIT:
                    row.blocked_until = now + LOGIN_LOCKOUT
                row.updated_at = now
            s.add(row)
        s.commit()


def clear_login_failures(username: str, client_ip: str) -> None:
    keys = login_throttle_keys(username, client_ip)
    with session() as s:
        for row in s.exec(select(LoginThrottle).where(LoginThrottle.attempt_hash.in_(keys))).all():
            s.delete(row)
        s.commit()


def bootstrap_local_owner(*, username: str, password: str, merchant_id: str, store_id: str,
                          app_env: str, remote_addr: str, forwarded_headers=()) -> tuple[User, MerchantMembership] | None:
    """Create the first local owner only in explicit dev mode on an unproxied loopback host.

    Returns None when the target already has an active owner. It never changes an existing
    password or membership, so repeating startup is harmless.
    """
    if app_env != "development" or forwarded_headers:
        raise PermissionError("Local bootstrap is available only in unproxied development mode")
    try:
        if not ip_address(remote_addr).is_loopback:
            raise PermissionError("Local bootstrap requires a loopback connection")
    except ValueError as exc:
        raise PermissionError("Local bootstrap requires a loopback connection") from exc
    normalized = normalize_username(username)
    password = validate_password(password)
    with session() as s:
        existing_owner = s.exec(select(MerchantMembership).where(
            MerchantMembership.merchant_id == merchant_id,
            MerchantMembership.store_id == store_id,
            MerchantMembership.role == "OWNER", MerchantMembership.is_active == True,  # noqa: E712
        )).first()
        if existing_owner:
            return None
        if s.exec(select(User)).first():
            raise PermissionError("Local bootstrap only runs before any login account exists")
        merchant, store = s.get(Merchant, merchant_id), s.get(Store, store_id)
        if merchant is None or store is None or store.merchant_id != merchant_id:
            raise ValueError("Merchant and store must exist and belong together")
        user = User(username=normalized, password_hash=hash_password(password))
        s.add(user)
        s.flush()
        membership = MerchantMembership(user_id=user.id, merchant_id=merchant_id,
                                        store_id=store_id, role="OWNER")
        s.add(membership)
        s.commit()
        s.refresh(user)
        s.refresh(membership)
        return user, membership
