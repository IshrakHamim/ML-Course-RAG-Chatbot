"""Knowledge-base operations: add (embed only the new document), list, delete, re-embed."""

import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import Chunk, Document
from app.services import gemini
from app.services.ingestion import ExtractedDoc, IngestionError, chunk_document, content_hash

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    document: Document
    created: bool


def _find_by_hash(db: Session, digest: str) -> Document | None:
    return db.scalar(select(Document).where(Document.content_hash == digest))


def ingest(db: Session, doc: ExtractedDoc, user_id: uuid.UUID | None) -> IngestResult:
    settings = get_settings()
    digest = content_hash(doc)
    existing = _find_by_hash(db, digest)
    if existing is not None:
        logger.info("Document already ingested title=%r id=%s", doc.title, existing.id)
        return IngestResult(existing, created=False)

    start = time.perf_counter()
    drafts = chunk_document(doc, settings.chunk_size, settings.chunk_overlap)
    if not drafts:
        raise IngestionError(422, "No text found in document")
    try:
        vectors = gemini.embed_texts([d.content for d in drafts], "RETRIEVAL_DOCUMENT")
    except Exception:
        logger.warning("Ingestion failed title=%r: embedding error", doc.title)
        raise

    document = Document(
        title=doc.title[:500],
        source_type=doc.source_type,
        source=doc.source[:2048],
        content_hash=digest,
        chunk_count=len(drafts),
        created_by=user_id,
        chunks=[
            Chunk(
                chunk_index=draft.chunk_index,
                content=draft.content,
                page=draft.page,
                embedding=vector,
                embedding_model=settings.gemini_embedding_model,
            )
            for draft, vector in zip(drafts, vectors, strict=True)
        ],
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_by_hash(db, digest)
        if existing is None:
            raise
        return IngestResult(existing, created=False)
    logger.info(
        "Ingested document title=%r type=%s chunks=%d in %.0fms",
        document.title, document.source_type, len(drafts), (time.perf_counter() - start) * 1000,
    )  # fmt: skip
    return IngestResult(document, created=True)


def list_documents(db: Session) -> list[Document]:
    return list(db.scalars(select(Document).order_by(Document.created_at.desc())))


def delete_document(db: Session, document_id: uuid.UUID) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found")
    db.delete(document)
    db.commit()
    logger.info("Deleted document title=%r id=%s", document.title, document_id)


def count_stale_chunks(db: Session) -> int:
    current = get_settings().gemini_embedding_model
    return db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.embedding_model != current)
    )


def reindex_all(db: Session) -> int:
    """Re-embed every chunk made with a different embedding model, one document at a time."""
    current = get_settings().gemini_embedding_model
    document_ids = db.scalars(
        select(Chunk.document_id).where(Chunk.embedding_model != current).distinct()
    ).all()
    total = 0
    for document_id in document_ids:
        chunks = db.scalars(
            select(Chunk)
            .where(Chunk.document_id == document_id, Chunk.embedding_model != current)
            .order_by(Chunk.chunk_index)
        ).all()
        vectors = gemini.embed_texts([c.content for c in chunks], "RETRIEVAL_DOCUMENT")
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_model = current
        db.commit()
        total += len(chunks)
        logger.info("Re-embedded %d chunks for document %s", len(chunks), document_id)
    return total
