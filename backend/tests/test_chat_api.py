import uuid

import pytest
from sqlalchemy import func, select

from app.core.errors import AI_BUSY_MESSAGE, AIServiceError
from app.models import ChatMessage, ChatSession
from app.services.rag import FALLBACK_ANSWER

LATE_QUESTION = "What is the late submission policy?"


def chat(client, headers, message, session_id=None):
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    return client.post("/api/v1/chat", headers=headers, json=body)


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_chat_creates_session_and_returns_id(client, user, seeded_kb, fake_gemini, db):
    response = chat(client, user, LATE_QUESTION)
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == fake_gemini.answer
    assert body["grounded"] is True
    assert body["kind"] == "answer"
    assert body["sources"] == [
        {"title": "Course Handbook", "source_type": "text", "page": None, "url": None}
    ]
    uuid.UUID(body["session_id"])
    assert count(db, ChatSession) == 1
    assert count(db, ChatMessage) == 2


def test_out_of_scope_fallback_via_api(client, user, seeded_kb, fake_gemini):
    body = chat(client, user, "What is the capital of Australia?").json()
    assert body["answer"] == FALLBACK_ANSWER
    assert body["grounded"] is False
    assert body["kind"] == "fallback"
    assert body["sources"] == []


def test_chat_history_persisted_and_capped(client, user, seeded_kb, fake_gemini):
    session_id = chat(client, user, LATE_QUESTION).json()["session_id"]
    for _ in range(4):
        chat(client, user, LATE_QUESTION, session_id)
    assert chat(client, user, LATE_QUESTION, session_id).status_code == 200
    turns = fake_gemini.generate_calls[-1][1]
    assert len(turns) == 6 + 1
    assert [t.role for t in turns[:6]] == ["user", "model"] * 3


def test_session_detail_lists_messages_in_order(client, user, seeded_kb, fake_gemini):
    session_id = chat(client, user, "hello").json()["session_id"]
    chat(client, user, LATE_QUESTION, session_id)
    response = client.get(f"/api/v1/chat/sessions/{session_id}", headers=user)
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "hello"
    assert [(m["role"], m["kind"]) for m in body["messages"]] == [
        ("user", None),
        ("assistant", "greeting"),
        ("user", None),
        ("assistant", "answer"),
    ]
    assert body["messages"][3]["sources"][0]["title"] == "Course Handbook"


def test_session_title_truncated(client, user, fake_gemini):
    long_message = "x" * 300
    session_id = chat(client, user, long_message).json()["session_id"]
    sessions = client.get("/api/v1/chat/sessions", headers=user).json()
    assert sessions[0]["id"] == session_id
    assert len(sessions[0]["title"]) <= 60


@pytest.mark.parametrize("message", ["", "   \n\t ", "\x00\x00"])
def test_empty_or_whitespace_message_422(client, user, message):
    assert chat(client, user, message).status_code == 422


def test_message_2001_chars_422(client, user):
    assert chat(client, user, "a" * 2001).status_code == 422


def test_message_2000_chars_ok(client, user, fake_gemini):
    assert chat(client, user, "a" * 2000).status_code == 200


def test_nul_bytes_stripped(client, user, seeded_kb, fake_gemini, db):
    assert chat(client, user, "what\x00 is the late submission policy").status_code == 200
    contents = list(db.scalars(select(ChatMessage.content).where(ChatMessage.role == "user")))
    assert contents == ["what is the late submission policy"]


def test_gemini_429_returns_503_and_saves_nothing(client, user, seeded_kb, fake_gemini, db):
    fake_gemini.fail_with = AIServiceError("quota")
    response = chat(client, user, LATE_QUESTION)
    assert response.status_code == 503
    assert response.json()["detail"] == AI_BUSY_MESSAGE
    assert count(db, ChatSession) == 0
    assert count(db, ChatMessage) == 0


def test_gemini_error_in_existing_session_saves_nothing(client, user, seeded_kb, fake_gemini, db):
    session_id = chat(client, user, LATE_QUESTION).json()["session_id"]
    fake_gemini.fail_with = AIServiceError("timeout")
    assert chat(client, user, LATE_QUESTION, session_id).status_code == 503
    assert count(db, ChatMessage) == 2


@pytest.fixture
def other_users_session(client, make_user, token_for, fake_gemini) -> str:
    other = {"Authorization": f"Bearer {token_for(make_user('other@example.com'))}"}
    return chat(client, other, "hello").json()["session_id"]


def test_other_users_session_404(client, user, other_users_session, db):
    path = f"/api/v1/chat/sessions/{other_users_session}"
    assert client.get(path, headers=user).status_code == 404
    assert client.delete(path, headers=user).status_code == 404
    response = chat(client, user, "hello", other_users_session)
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
    assert count(db, ChatMessage) == 2


def test_nonexistent_session_404(client, user, fake_gemini):
    assert chat(client, user, "hello", str(uuid.uuid4())).status_code == 404
    assert client.get(f"/api/v1/chat/sessions/{uuid.uuid4()}", headers=user).status_code == 404


def test_malformed_session_id_422(client, user):
    assert chat(client, user, "hello", "not-a-uuid").status_code == 422
    assert client.get("/api/v1/chat/sessions/not-a-uuid", headers=user).status_code == 422


def test_list_sessions_only_own(client, user, other_users_session, fake_gemini):
    mine = chat(client, user, "hello").json()["session_id"]
    sessions = client.get("/api/v1/chat/sessions", headers=user).json()
    assert [s["id"] for s in sessions] == [mine]


def test_list_sessions_most_recent_first(client, user, fake_gemini):
    first = chat(client, user, "hello").json()["session_id"]
    second = chat(client, user, "hi").json()["session_id"]
    chat(client, user, "thanks", first)
    sessions = client.get("/api/v1/chat/sessions", headers=user).json()
    assert [s["id"] for s in sessions] == [first, second]


def test_delete_session_removes_messages(client, user, fake_gemini, db):
    session_id = chat(client, user, "hello").json()["session_id"]
    assert client.delete(f"/api/v1/chat/sessions/{session_id}", headers=user).status_code == 204
    assert count(db, ChatSession) == 0
    assert count(db, ChatMessage) == 0


def test_chat_requires_auth_401(client):
    assert client.post("/api/v1/chat", json={"message": "hi"}).status_code == 401
    assert client.get("/api/v1/chat/sessions").status_code == 401


def test_delete_all_sessions_keeps_other_users(client, user, other_users_session, fake_gemini, db):
    chat(client, user, "hello")
    chat(client, user, "hi")
    assert client.delete("/api/v1/chat/sessions", headers=user).status_code == 204
    assert client.get("/api/v1/chat/sessions", headers=user).json() == []
    assert db.scalars(select(ChatSession.id)).all() == [uuid.UUID(other_users_session)]
    assert count(db, ChatMessage) == 2


def test_delete_all_sessions_requires_auth_401(client):
    assert client.delete("/api/v1/chat/sessions").status_code == 401
