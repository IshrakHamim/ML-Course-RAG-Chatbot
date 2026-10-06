"""Command-line tools: python -m app.cli <command>."""

import argparse
import getpass
import logging
import sys

from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.models import User
from app.schemas.auth import RegisterRequest
from app.services import gemini


def out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def create_admin(email: str | None) -> int:
    email = email or input("Admin email: ")
    password = getpass.getpass("Password (min 8 characters): ")
    if getpass.getpass("Repeat password: ") != password:
        out("Error: passwords do not match.")
        return 1
    try:
        account = RegisterRequest(email=email, password=password)
    except ValidationError as exc:
        out("Error: " + "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors()))
        return 1
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == account.email))
        if user is None:
            db.add(User(email=account.email, password_hash=hash_password(password), role="admin"))
            action = "Created"
        else:
            user.role = "admin"
            user.password_hash = hash_password(password)
            action = "Promoted existing user to"
        db.commit()
    out(f"{action} admin: {account.email}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser(
        "create-admin", help="Create an admin (or promote an existing user)"
    )
    admin.add_argument("--email")
    commands.add_parser("check-gemini", help="Check the Gemini key, models and vector length")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(get_settings().log_level)
    logging.getLogger(__name__).debug("Running %s", args.command)
    if args.command == "create-admin":
        return create_admin(args.email)
    if args.command == "check-gemini":
        return gemini.run_check()
    return 1


if __name__ == "__main__":
    sys.exit(main())
