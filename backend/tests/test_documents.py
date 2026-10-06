import uuid

import pytest
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.errors import AI_BUSY_MESSAGE, AIServiceError
from app.models import Chunk, Document
from app.services import documents, ingestion
from app.services.ingestion import ExtractedDoc, Section
from tests.pdfs import blank_pdf, text_pdf

HANDBOOK = b"""# Course Handbook

The late submission policy deducts ten percent per day.

Office hours are on Tuesdays at 3pm in room 204.
"""


def upload(client, headers, name="handbook.md", data=HANDBOOK):
    return client.post("/api/v1/documents", headers=headers, files={"file": (name, data)})


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_upload_txt_creates_doc_and_chunks(client, admin, fake_gemini, db):
    response = upload(client, admin)
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "handbook"
    assert body["source_type"] == "text"
    assert body["duplicate"] is False
    assert body["chunk_count"] >= 1
    assert count(db, Chunk) == body["chunk_count"]
    models = set(db.scalars(select(Chunk.embedding_model)))
    assert models == {get_settings().gemini_embedding_model}


def test_upload_pdf_records_pages(client, admin, fake_gemini, db):
    response = upload(client, admin, "guide.pdf", text_pdf(["Page one text.", "Page two text."]))
    assert response.status_code == 201
    assert sorted(db.scalars(select(Chunk.page))) == [1, 2]


def test_embeds_with_retrieval_document(client, admin, fake_gemini):
    upload(client, admin)
    assert fake_gemini.embed_calls[0][1] == "RETRIEVAL_DOCUMENT"


def test_duplicate_upload_returns_existing(client, admin, fake_gemini, db):
    first = upload(client, admin).json()
    chunks_before = count(db, Chunk)
    second = upload(client, admin, name="copy-of-handbook.txt")
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert second.json()["duplicate"] is True
    assert count(db, Chunk) == chunks_before
    assert count(db, Document) == 1
    assert len(fake_gemini.embed_calls) == 1


def test_upload_unsupported_415(client, admin, db):
    response = upload(client, admin, "notes.docx", b"PK\x03\x04")
    assert response.status_code == 415
    assert response.json()["detail"] == "Supported: PDF, TXT, MD"
    assert count(db, Document) == 0


def test_upload_too_large_413(client, admin, db, monkeypatch):
    settings = get_settings().model_copy(update={"max_upload_mb": 1})
    monkeypatch.setattr("app.api.documents.get_settings", lambda: settings)
    response = upload(client, admin, "big.txt", b"a" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert count(db, Document) == 0


def test_upload_scanned_pdf_422_nothing_saved(client, admin, fake_gemini, db):
    response = upload(client, admin, "scan.pdf", blank_pdf())
    assert response.status_code == 422
    assert "no extractable text" in response.json()["detail"]
    assert count(db, Document) == 0
    assert fake_gemini.embed_calls == []


def test_upload_missing_file_422(client, admin):
    assert client.post("/api/v1/documents", headers=admin).status_code == 422


def test_embedding_failure_saves_nothing(client, admin, fake_gemini, db):
    fake_gemini.fail_with = AIServiceError("quota")
    response = upload(client, admin)
    assert response.status_code == 503
    assert response.json()["detail"] == AI_BUSY_MESSAGE
    assert count(db, Document) == 0
    assert count(db, Chunk) == 0


def test_url_ingest_private_ip_400(client, admin, db):
    response = client.post(
        "/api/v1/documents/url", headers=admin, json={"url": "http://127.0.0.1/x"}
    )
    assert response.status_code == 400
    assert count(db, Document) == 0


def test_url_ingest_success(client, admin, fake_gemini, monkeypatch):
    page = ExtractedDoc(
        "Course page", "url", "https://example.com/course", [Section("Grading uses a curve.", None)]
    )
    monkeypatch.setattr(ingestion, "fetch_url", lambda url: page)
    response = client.post(
        "/api/v1/documents/url", headers=admin, json={"url": "https://example.com/course"}
    )
    assert response.status_code == 201
    assert response.json()["source_type"] == "url"
    assert response.json()["source"] == "https://example.com/course"


def test_url_too_long_422(client, admin):
    response = client.post(
        "/api/v1/documents/url", headers=admin, json={"url": "https://e.com/" + "a" * 2050}
    )
    assert response.status_code == 422


def test_list_documents_newest_first(client, admin, fake_gemini):
    upload(client, admin, "first.md", b"First document text.")
    upload(client, admin, "second.md", b"Second document text.")
    response = client.get("/api/v1/documents", headers=admin)
    assert response.status_code == 200
    assert [d["title"] for d in response.json()] == ["second", "first"]


def test_delete_removes_chunks(client, admin, fake_gemini, db):
    document_id = upload(client, admin).json()["id"]
    response = client.delete(f"/api/v1/documents/{document_id}", headers=admin)
    assert response.status_code == 204
    assert count(db, Document) == 0
    assert count(db, Chunk) == 0


def test_delete_missing_404(client, admin):
    response = client.delete(f"/api/v1/documents/{uuid.uuid4()}", headers=admin)
    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/documents"),
        ("post", "/api/v1/documents"),
        ("post", "/api/v1/documents/url"),
        ("delete", f"/api/v1/documents/{uuid.uuid4()}"),
    ],
)
def test_user_gets_403(client, user, method, path):
    assert client.request(method, path, headers=user).status_code == 403


def test_anonymous_gets_401(client):
    assert client.get("/api/v1/documents").status_code == 401


def test_reindex_reembeds_stale_chunks(client, admin, fake_gemini, db):
    upload(client, admin)
    db.execute(update(Chunk).values(embedding_model="old-model"))
    db.commit()
    assert documents.count_stale_chunks(db) == count(db, Chunk)
    assert documents.reindex_all(db) == count(db, Chunk)
    assert documents.count_stale_chunks(db) == 0


def test_cli_ingest_directory(tmp_path, fake_gemini, db, capsys):
    from app import cli

    (tmp_path / "lesson.md").write_text("Lesson about gradient descent.")
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4 garbage")
    (tmp_path / "report.docx").write_bytes(b"PK")
    assert cli.main(["ingest", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "lesson.md: added" in output
    assert "broken.pdf: failed: Could not read the PDF file" in output
    assert "report.docx: skipped (Supported: PDF, TXT, MD)" in output
    assert count(db, Document) == 1


def test_cli_ingest_urls_file(tmp_path, fake_gemini, db, capsys, monkeypatch):
    from app import cli

    page = ExtractedDoc("Page", "url", "https://example.com/", [Section("Some page text.", None)])
    monkeypatch.setattr(ingestion, "fetch_url", lambda url: page)
    (tmp_path / "urls.txt").write_text("# comment\n\nhttps://example.com/\n")
    assert cli.main(["ingest", str(tmp_path)]) == 0
    assert "https://example.com/: added" in capsys.readouterr().out


def test_cli_ingest_twice_reports_exists(tmp_path, fake_gemini, capsys):
    from app import cli

    (tmp_path / "lesson.md").write_text("Lesson about gradient descent.")
    cli.main(["ingest", str(tmp_path)])
    assert cli.main(["ingest", str(tmp_path)]) == 0
    assert "exists" in capsys.readouterr().out


def test_cli_reindex(client, admin, fake_gemini, db, capsys):
    from app import cli

    upload(client, admin)
    db.execute(update(Chunk).values(embedding_model="old-model"))
    db.commit()
    assert cli.main(["reindex"]) == 0
    assert "Re-embedded" in capsys.readouterr().out
    assert documents.count_stale_chunks(db) == 0


def test_pdf_file_can_be_viewed_by_any_user(client, admin, user, fake_gemini):
    data = text_pdf(["Page one text.", "Page two text."])
    document_id = upload(client, admin, "guide.pdf", data).json()["id"]
    listed = client.get("/api/v1/documents", headers=admin).json()
    assert listed[0]["has_file"] is True
    response = client.get(f"/api/v1/documents/{document_id}/file", headers=user)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == "inline; filename*=UTF-8''guide.pdf"
    assert response.content == data


def test_text_document_has_no_file_404(client, admin, fake_gemini):
    document_id = upload(client, admin).json()["id"]
    assert client.get("/api/v1/documents", headers=admin).json()[0]["has_file"] is False
    response = client.get(f"/api/v1/documents/{document_id}/file", headers=admin)
    assert response.status_code == 404
    assert response.json()["detail"] == "Document file not found"


def test_missing_document_file_404(client, user):
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/file", headers=user).status_code == 404


def test_document_file_requires_login_401(client):
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/file").status_code == 401


def test_reupload_adds_file_to_older_pdf_document(client, admin, fake_gemini, db):
    data = text_pdf(["Page one text."])
    document_id = upload(client, admin, "guide.pdf", data).json()["id"]
    db.execute(update(Document).values(file_data=None))
    db.commit()
    response = upload(client, admin, "guide.pdf", data)
    assert response.status_code == 200
    assert response.json()["duplicate"] is True
    assert response.json()["has_file"] is True
    assert client.get(f"/api/v1/documents/{document_id}/file", headers=admin).content == data
    assert count(db, Document) == 1
