import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.core.config import get_settings


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str

    @field_validator("message")
    @classmethod
    def _clean_message(cls, value: str) -> str:
        value = value.replace("\x00", "").strip()
        if not value:
            raise ValueError("Message must not be empty")
        limit = get_settings().max_message_chars
        if len(value) > limit:
            raise ValueError(f"Message must be at most {limit} characters")
        return value


class SourceOut(BaseModel):
    document_id: uuid.UUID | None = None
    title: str
    source_type: str
    page: int | None = None
    url: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    session_id: uuid.UUID
    grounded: bool
    kind: Literal["answer", "fallback", "greeting"]


class SessionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = {"from_attributes": True}

    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceOut] | None = None
    grounded: bool | None = None
    kind: Literal["answer", "fallback", "greeting"] | None = None
    created_at: datetime


class SessionDetail(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str
    messages: list[MessageOut]
