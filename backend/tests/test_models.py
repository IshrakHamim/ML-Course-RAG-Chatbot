import hashlib
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import ChatMessage, ChatSession, Chunk, Document, User


def make_document(content_hash: str | None = None) -> Document:
    return Document(
        title="Doc",
        source_type="text",
        source="doc.txt",
        content_hash=content_hash or hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        chunk_count=0,
    )


def unit_vector(dim: int = 768) -> list[float]:
    return [1.0] + [0.0] * (dim - 1)


def make_chunk(index: int, dim: int = 768) -> Chunk:
    return Chunk(
        chunk_index=index,
        content=f"chunk {index}",
        embedding=unit_vector(dim),
        embedding_model="test-model",
    )


def test_deleting_document_cascades_chunks(db):
    document = make_document()
    document.chunks = [make_chunk(0), make_chunk(1)]
    db.add(document)
    db.commit()
    db.execute(delete(Document).where(Document.id == document.id))
    db.commit()
    assert db.scalar(select(func.count()).select_from(Chunk)) == 0


def test_content_hash_unique(db):
    db.add_all([make_document("a" * 64), make_document("a" * 64)])
    with pytest.raises(IntegrityError):
        db.commit()


def test_embedding_dimension_enforced(db):
    document = make_document()
    document.chunks = [make_chunk(0, dim=767)]
    db.add(document)
    with pytest.raises(DBAPIError):
        db.commit()


def test_deleting_session_cascades_messages(db):
    user = User(email="a@example.com", password_hash="x")
    session = ChatSession(user=user, title="t")
    session.messages = [ChatMessage(role="user", content="hi")]
    db.add(session)
    db.commit()
    db.execute(delete(ChatSession).where(ChatSession.id == session.id))
    db.commit()
    assert db.scalar(select(func.count()).select_from(ChatMessage)) == 0


def test_role_check_constraint(db):
    db.add(User(email="b@example.com", password_hash="x", role="superuser"))
    with pytest.raises(IntegrityError):
        db.commit()
