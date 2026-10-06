"""Similarity search over chunk embeddings with pgvector."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Chunk, Document


@dataclass
class RetrievedChunk:
    document_id: uuid.UUID
    title: str
    source_type: str
    source: str
    page: int | None
    content: str
    score: float


def has_chunks(db: Session) -> bool:
    """True if any chunk was embedded with the current embedding model."""
    current = get_settings().gemini_embedding_model
    return db.scalar(select(Chunk.id).where(Chunk.embedding_model == current).limit(1)) is not None


def search(db: Session, query_vector: list[float], top_k: int) -> list[RetrievedChunk]:
    """Top-k chunks by cosine similarity, best first. score = 1 - cosine distance."""
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    rows = db.execute(
        select(
            Chunk.document_id,
            Document.title,
            Document.source_type,
            Document.source,
            Chunk.page,
            Chunk.content,
            distance,
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.embedding_model == get_settings().gemini_embedding_model)
        .order_by(distance)
        .limit(top_k)
    ).all()
    return [
        RetrievedChunk(
            document_id=row.document_id,
            title=row.title,
            source_type=row.source_type,
            source=row.source,
            page=row.page,
            content=row.content,
            score=1.0 - row.distance,
        )
        for row in rows
    ]
