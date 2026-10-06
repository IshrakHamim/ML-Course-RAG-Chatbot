"""Command-line tools: python -m app.cli <command>."""

import argparse
import getpass
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import AIServiceError
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.models import User
from app.schemas.auth import RegisterRequest
from app.services import documents, gemini, ingestion, retrieval
from app.services.ingestion import ExtractedDoc, IngestionError


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


URL_LIST_NAME = "urls.txt"


def _ingest_one(label: str, load: Callable[[], ExtractedDoc]) -> bool:
    try:
        with SessionLocal() as db:
            result = documents.ingest(db, load(), user_id=None)
    except IngestionError as exc:
        out(f"{label}: failed: {exc.message}")
        return False
    except AIServiceError as exc:
        out(f"{label}: failed: AI service error ({exc.kind}); try again later")
        return False
    out(
        f"{label}: {'added' if result.created else 'exists'} ({result.document.chunk_count} chunks)"
    )
    return True


def _url_list(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def ingest_path(target: str) -> int:
    path = Path(target)
    if not path.exists():
        out(f"Error: {target} does not exist")
        return 1
    files = sorted(p for p in path.iterdir() if p.is_file()) if path.is_dir() else [path]
    ok = True
    for file in files:
        if file.name.startswith("."):
            continue
        if file.name == URL_LIST_NAME:
            for url in _url_list(file):
                ok &= _ingest_one(url, lambda url=url: ingestion.fetch_url(url))
            continue
        try:
            ingestion.check_supported(file.name)
        except IngestionError as exc:
            out(f"{file.name}: skipped ({exc.message})")
            continue
        ok &= _ingest_one(
            file.name, lambda file=file: ingestion.load_upload(file.name, file.read_bytes())
        )
    return 0 if ok else 1


def reindex() -> int:
    with SessionLocal() as db:
        total = documents.reindex_all(db)
    out(f"Re-embedded {total} chunks with {get_settings().gemini_embedding_model}")
    return 0


def search(question: str) -> int:
    settings = get_settings()
    with SessionLocal() as db:
        hits = retrieval.search(db, gemini.embed_query(question), settings.rag_top_k)
    out(f"Top {settings.rag_top_k} chunks (RAG_MIN_SCORE={settings.rag_min_score}):")
    for hit in hits:
        page = hit.page if hit.page is not None else "-"
        mark = "pass" if hit.score >= settings.rag_min_score else "    "
        out(f"  {hit.score:.3f} {mark}  {hit.title}  (page {page})")
    if not hits:
        out("  (no chunks)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser(
        "create-admin", help="Create an admin (or promote an existing user)"
    )
    admin.add_argument("--email")
    commands.add_parser("check-gemini", help="Check the Gemini key, models and vector length")
    ingest = commands.add_parser(
        "ingest", help="Ingest a file or a directory (PDF/TXT/MD + urls.txt)"
    )
    ingest.add_argument("path")
    commands.add_parser("reindex", help="Re-embed chunks made with a different embedding model")
    search_cmd = commands.add_parser("search", help="Show retrieval scores for a question")
    search_cmd.add_argument("question")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(get_settings().log_level)
    logging.getLogger(__name__).debug("Running %s", args.command)
    if args.command == "create-admin":
        return create_admin(args.email)
    if args.command == "check-gemini":
        return gemini.run_check()
    if args.command == "ingest":
        return ingest_path(args.path)
    if args.command == "reindex":
        return reindex()
    if args.command == "search":
        return search(args.question)
    return 1


if __name__ == "__main__":
    sys.exit(main())
