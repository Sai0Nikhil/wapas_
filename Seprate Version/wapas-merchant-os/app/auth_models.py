"""Credentials, merchant memberships, and revocable browser sessions."""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "authuser"
    __table_args__ = (UniqueConstraint("username", name="uq_authuser_username"),)

    id: str = Field(default_factory=lambda: "usr_" + uuid4().hex, primary_key=True)
    username: str = Field(index=True, max_length=120)
    password_hash: str = Field(max_length=320)
    is_active: bool = True
    created_at: datetime = Field(default_factory=now, index=True)
    password_changed_at: Optional[datetime] = None


class MerchantMembership(SQLModel, table=True):
    __tablename__ = "merchantmembership"
    __table_args__ = (
        UniqueConstraint("user_id", "merchant_id", "store_id", name="uq_membership_user_merchant_store"),
        CheckConstraint("role IN ('OWNER','STAFF')", name="ck_membership_role"),
        Index("ix_membership_scope_active", "merchant_id", "store_id", "is_active"),
    )

    id: str = Field(default_factory=lambda: "mbr_" + uuid4().hex, primary_key=True)
    user_id: str = Field(foreign_key="authuser.id", index=True)
    merchant_id: str = Field(foreign_key="merchant.id", index=True)
    store_id: str = Field(foreign_key="store.id", index=True)
    role: str = "STAFF"
    is_active: bool = True
    created_at: datetime = Field(default_factory=now, index=True)


class AuthSession(SQLModel, table=True):
    __tablename__ = "authsession"
    __table_args__ = (Index("ix_authsession_expiry_revoked", "expires_at", "revoked_at"),)

    # SHA-256 digest of the browser's random token, never the bearer token itself.
    token_hash: str = Field(primary_key=True, max_length=64)
    csrf_hash: str = Field(max_length=64)
    membership_id: str = Field(foreign_key="merchantmembership.id", index=True)
    created_at: datetime = Field(default_factory=now, index=True)
    expires_at: datetime = Field(index=True)
    revoked_at: Optional[datetime] = None


class LoginThrottle(SQLModel, table=True):
    __tablename__ = "loginthrottle"

    # The key is a one-way digest over a username or IP address. Raw values are not kept.
    attempt_hash: str = Field(primary_key=True, max_length=64)
    failures: int = 0
    window_started_at: datetime = Field(default_factory=now)
    blocked_until: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=now)
