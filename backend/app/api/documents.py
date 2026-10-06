import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User
from app.schemas.documents import DocumentOut, UrlIngestRequest
from app.services import documents, ingestion
from app.services.ingestion import ExtractedDoc, IngestionError

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_ERRORS = {
    400: {"description": "URL not allowed"},
    413: {"description": "File too large"},
    415: {"description": "Unsupported file type"},
    422: {"description": "No usable text, or the URL could not be fetched"},
    503: {"description": "The AI service is busy"},
}


def _store(db: Session, response: Response, doc: ExtractedDoc, user: User) -> DocumentOut:
    result = documents.ingest(db, doc, user.id)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    out = DocumentOut.model_validate(result.document)
    out.duplicate = not result.created
    return out


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF, TXT or MD file (200 with duplicate=true if already present)",
    responses=UPLOAD_ERRORS,
)
def upload_document(
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DocumentOut:
    filename = file.filename or ""
    max_bytes = get_settings().max_upload_bytes
    try:
        ingestion.check_supported(filename)
        data = file.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise IngestionError(413, f"File is larger than {get_settings().max_upload_mb} MB")
        doc = ingestion.load_upload(filename, data)
    except IngestionError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    return _store(db, response, doc, admin)


@router.post(
    "/url",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a web page by URL (200 with duplicate=true if already present)",
    responses=UPLOAD_ERRORS,
)
def add_url(
    body: UrlIngestRequest,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DocumentOut:
    try:
        doc = ingestion.fetch_url(body.url)
    except IngestionError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    return _store(db, response, doc, admin)


@router.get("", response_model=list[DocumentOut], summary="List documents, newest first")
def list_documents(
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> list[DocumentOut]:
    return [DocumentOut.model_validate(d) for d in documents.list_documents(db)]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its chunks",
    responses={404: {"description": "Document not found"}},
)
def delete_document(
    document_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> Response:
    documents.delete_document(db, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
