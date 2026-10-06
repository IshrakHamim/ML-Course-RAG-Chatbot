import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User
from app.schemas.chat import ChatRequest, ChatResponse, SessionDetail, SessionOut, SourceOut
from app.services import memory, rag

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    summary="Ask a question (creates a session when session_id is omitted)",
    responses={
        404: {"description": "Session not found"},
        503: {"description": "The AI service is busy"},
    },
)
def chat(
    body: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ChatResponse:
    try:
        session = memory.get_or_create_session(db, user.id, body.session_id, body.message)
        history = memory.recent_history(db, session, get_settings().memory_turns)
        answer = rag.answer_question(db, body.message, history)
        memory.save_exchange(db, session, body.message, answer)
    except Exception:
        db.rollback()
        raise
    return ChatResponse(
        answer=answer.answer,
        sources=[SourceOut(**asdict(source)) for source in answer.sources],
        session_id=session.id,
        grounded=answer.grounded,
        kind=answer.kind,
    )


@router.get("/sessions", response_model=list[SessionOut], summary="List my chat sessions")
def list_sessions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[SessionOut]:
    return [SessionOut.model_validate(s) for s in memory.list_sessions(db, user.id)]


@router.delete(
    "/sessions",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all my chat sessions",
)
def delete_all_sessions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    memory.delete_all_sessions(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetail,
    summary="Get a chat session with its messages",
    responses={404: {"description": "Session not found"}},
)
def get_session(
    session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SessionDetail:
    return SessionDetail.model_validate(memory.get_session(db, user.id, session_id))


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session",
    responses={404: {"description": "Session not found"}},
)
def delete_session(
    session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    memory.delete_session(db, user.id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
