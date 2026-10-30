"""Request/service tenant context derived from an authenticated identity or explicit worker scope."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

DEFAULT_MERCHANT_ID = "merchant_default"
DEFAULT_STORE_ID = "store_default"
_current_merchant: ContextVar[str | None] = ContextVar("wapas_merchant_id", default=None)
_current_store: ContextVar[str | None] = ContextVar("wapas_store_id", default=None)
_current_identity: ContextVar["RequestIdentity | None"] = ContextVar("wapas_identity", default=None)


@dataclass(frozen=True)
class RequestIdentity:
    user_id: str
    username: str
    membership_id: str
    merchant_id: str
    store_id: str
    role: str
    session_hash: str = ""


def current_identity() -> RequestIdentity | None:
    return _current_identity.get()


def current_merchant_id() -> str | None:
    override = _current_merchant.get()
    if override is not None:
        return override
    identity = current_identity()
    return identity.merchant_id if identity else None


def current_store_id() -> str | None:
    override = _current_store.get()
    if override is not None:
        return override
    identity = current_identity()
    return identity.store_id if identity else None


def tenant_default_merchant() -> str:
    """Resolve an ORM tenant default only from a request or explicit worker scope."""
    merchant_id = current_merchant_id()
    if merchant_id:
        return merchant_id
    from .config import get_settings

    if get_settings().app_env.lower() in {"test", "development"}:
        return DEFAULT_MERCHANT_ID
    raise RuntimeError("A merchant identity or explicit tenant scope is required for this write")


def tenant_default_store() -> str:
    store_id = current_store_id()
    if store_id:
        return store_id
    from .config import get_settings

    if get_settings().app_env.lower() in {"test", "development"}:
        return DEFAULT_STORE_ID
    raise RuntimeError("A store identity or explicit tenant scope is required for this write")


def set_merchant_id(merchant_id: str):
    return _current_merchant.set(merchant_id)


def reset_merchant_id(token) -> None:
    _current_merchant.reset(token)


def set_store_id(store_id: str | None):
    return _current_store.set(store_id)


def reset_store_id(token) -> None:
    _current_store.reset(token)


def set_identity(identity: RequestIdentity):
    return _current_identity.set(identity)


def reset_identity(token) -> None:
    _current_identity.reset(token)


@contextmanager
def merchant_scope(merchant_id: str):
    token = set_merchant_id(merchant_id)
    try:
        yield
    finally:
        reset_merchant_id(token)


@contextmanager
def tenant_scope(merchant_id: str, store_id: str | None = None):
    merchant_token = set_merchant_id(merchant_id)
    store_token = set_store_id(store_id)
    try:
        yield
    finally:
        reset_store_id(store_token)
        reset_merchant_id(merchant_token)
