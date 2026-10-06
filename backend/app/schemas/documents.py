import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str
    source_type: str
    source: str
    chunk_count: int
    created_at: datetime
    has_file: bool = False
    duplicate: bool = False


class UrlIngestRequest(BaseModel):
    url: str = Field(
        min_length=1,
        max_length=2048,
        examples=["https://en.wikipedia.org/wiki/Retrieval-augmented_generation"],
    )
