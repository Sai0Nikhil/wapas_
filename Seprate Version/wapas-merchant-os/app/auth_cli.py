"""Explicit account provisioning. Passwords are entered interactively, never in argv."""
import argparse
from getpass import getpass
import sys

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel, select

from . import auth_models, models  # register auth and Merchant/Store tables
from .auth import create_user_membership, normalize_username, validate_password
from .auth_models import MerchantMembership, User
from .config import get_settings
from .db import engine, reset_engine, session
from .models import Merchant, Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision a Wapas merchant login")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, role in (("create-owner", "OWNER"), ("create-staff", "STAFF")):
        cmd = sub.add_parser(name, help=f"create a user with the {role.lower()} role")
        cmd.add_argument("--database-url", required=True,
                         help="explicit SQLModel database URL for the already initialized installation")
        cmd.add_argument("--username", help="login username (prompted if omitted)")
        cmd.add_argument("--merchant-id", default="merchant_default")
        cmd.add_argument("--store-id", default="store_default")
        cmd.set_defaults(role=role)
    membership = sub.add_parser("add-membership", help="add another merchant/store membership to an existing user")
    membership.add_argument("--database-url", required=True)
    membership.add_argument("--username", required=True)
    membership.add_argument("--merchant-id", required=True)
    membership.add_argument("--store-id", required=True)
    membership.add_argument("--role", choices=("OWNER", "STAFF"), required=True)
    return parser


def _prepare_database(database_url: str) -> None:
    if not database_url or not database_url.startswith(("sqlite:", "postgresql:", "postgres:")):
        raise ValueError("Use an explicit SQLite or PostgreSQL SQLModel database URL")
    get_settings().database_url = database_url
    reset_engine(database_url)
    # Create only missing tables; this command does not run migrations or seed records.
    SQLModel.metadata.create_all(engine())
    with session() as s:
        if not s.exec(select(Merchant.id).limit(1)).first() or not s.exec(select(Store.id).limit(1)).first():
            raise ValueError("The selected database has no initialized merchant/store; initialize it safely first")


def _read_password() -> str:
    first = getpass("New password (14+ characters): ")
    second = getpass("Repeat password: ")
    if first != second:
        raise ValueError("Passwords did not match")
    return validate_password(first)


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _prepare_database(args.database_url)
        if args.command == "add-membership":
            username = normalize_username(args.username)
            with session() as s:
                user = s.exec(select(User).where(User.username == username)).first()
                merchant = s.get(Merchant, args.merchant_id)
                store = s.get(Store, args.store_id)
                if user is None or merchant is None or store is None or store.merchant_id != merchant.id:
                    raise ValueError("User or merchant/store membership target was not found")
                existing = s.exec(select(MerchantMembership).where(
                    MerchantMembership.user_id == user.id,
                    MerchantMembership.merchant_id == merchant.id,
                    MerchantMembership.store_id == store.id,
                )).first()
                if existing:
                    raise ValueError("That user already has this merchant/store membership")
                s.add(MerchantMembership(user_id=user.id, merchant_id=merchant.id,
                                         store_id=store.id, role=args.role))
                s.commit()
            print("Merchant membership added.")
            return 0

        username = args.username or input("Username: ")
        password = _read_password()
        user, _membership = create_user_membership(
            username=username, password=password, merchant_id=args.merchant_id,
            store_id=args.store_id, role=args.role,
        )
        print(f"{args.role.title()} login created for {user.username}.")
        return 0
    except (ValueError, PermissionError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print("Account provisioning failed. Check the selected database and retry.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
