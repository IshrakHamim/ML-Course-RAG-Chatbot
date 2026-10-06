"""Chat sessions and short-term conversation history."""

import uuid
from dataclasses import asdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import ChatMessage, ChatSession
from app.services.gemini import ChatTurn
from app.services.rag import ChatAnswer

TITLE_LENGTH = 60


def get_session(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession:
    session = db.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if session is None:
        raise NotFoundError("Session not found")
    return session


def get_or_create_session(
    db: Session, user_id: uuid.UUID, session_id: uuid.UUID | None, first_message: str
) -> ChatSession:
    """Returns the user's session, or a new one (flushed, not committed)."""
    if session_id is not None:
        return get_session(db, user_id, session_id)
    session = ChatSession(user_id=user_id, title=" ".join(first_message.split())[:TITLE_LENGTH])
    db.add(session)
    db.flush()
    return session


def recent_history(db: Session, session: ChatSession, limit: int) -> list[ChatTurn]:
    if limit <= 0:
        return []
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).all()
    return [
        ChatTurn("user" if m.role == "user" else "model", m.content) for m in reversed(messages)
    ]


def save_exchange(db: Session, session: ChatSession, user_text: str, answer: ChatAnswer) -> None:
    db.add(ChatMessage(session_id=session.id, role="user", content=user_text))
    db.flush()  # separate statements so the two messages get distinct timestamps
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=answer.answer,
            sources=[asdict(source) for source in answer.sources],
            grounded=answer.grounded,
            kind=answer.kind,
        )
    )
    session.updated_at = func.clock_timestamp()
    db.commit()


def list_sessions(db: Session, user_id: uuid.UUID) -> list[ChatSession]:
    return list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
    )


def delete_session(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
    db.delete(get_session(db, user_id, session_id))
    db.commit()


def delete_all_sessions(db: Session, user_id: uuid.UUID) -> int:
    sessions = list_sessions(db, user_id)
    for session in sessions:
        db.delete(session)
    db.commit()
    return len(sessions)
