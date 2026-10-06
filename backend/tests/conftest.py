import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://rag:rag@localhost:5432/ragbot_test"
)
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["JWT_SECRET"] = "t" * 40
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# The fake bag-of-words embeddings score lower than real Gemini embeddings.
os.environ["RAG_MIN_SCORE"] = "0.2"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402


def _create_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(url.set(database="ragbot"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database():
    try:
        _create_test_database()
    except OperationalError:
        pytest.exit("Postgres not reachable: run `docker compose up -d db`", returncode=1)
    from app.core.db import engine

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    from app.models import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _restore_logging():
    """cli.main() reconfigures logging; under capsys that binds handlers to a temporary stream."""
    import logging

    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    from app.core.db import engine
    from app.models import Base

    names = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def db():
    from app.core.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db):
    from app.core.security import hash_password
    from app.models import User

    def _make_user(
        email: str = "user@example.com", role: str = "user", password: str = "password123"
    ):
        user = User(email=email, password_hash=hash_password(password), role=role)
        db.add(user)
        db.commit()
        return user

    return _make_user


@pytest.fixture
def token_for():
    from app.core.security import create_access_token

    return lambda user: create_access_token(user.id)


@pytest.fixture
def user(make_user, token_for) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(make_user('user@example.com'))}"}


@pytest.fixture
def admin(make_user, token_for) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(make_user('admin@example.com', 'admin'))}"}


@pytest.fixture
def fake_gemini(monkeypatch):
    from app.services import gemini
    from tests.fakes import FakeGemini

    fake = FakeGemini()
    monkeypatch.setattr(gemini, "embed_texts", fake.embed_texts)
    monkeypatch.setattr(gemini, "embed_query", fake.embed_query)
    monkeypatch.setattr(gemini, "generate", fake.generate)
    return fake


HANDBOOK_TEXT = (
    "The late submission policy deducts ten percent per day.\n\n"
    "Office hours are on Tuesdays at 3pm in room 204."
)


@pytest.fixture
def seeded_kb(db, fake_gemini):
    from app.services import documents
    from app.services.ingestion import ExtractedDoc, Section

    doc = ExtractedDoc("Course Handbook", "text", "handbook.md", [Section(HANDBOOK_TEXT, None)])
    return documents.ingest(db, doc, user_id=None).document
