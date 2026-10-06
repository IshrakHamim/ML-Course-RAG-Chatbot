import re

import httpx
import pytest

from app.core.config import get_settings
from app.services import ingestion
from app.services.ingestion import (
    SUPPORTED_MESSAGE,
    ExtractedDoc,
    IngestionError,
    Section,
    chunk_document,
    chunk_text,
    clean_text,
    content_hash,
    fetch_url,
    load_upload,
    validate_public_url,
)
from tests.pdfs import blank_pdf, empty_password_pdf, encrypted_pdf, text_pdf

PUBLIC_IP = "93.184.216.34"


def public_resolver(host: str) -> list[str]:
    return [PUBLIC_IP]


def sentences(n: int, prefix: str = "Sentence") -> str:
    return " ".join(f"{prefix} number {i} talks about topic {i}." for i in range(n))


# --- cleaning and chunking ----------------------------------------------------------------


def test_clean_text_normalizes_whitespace_and_nul():
    assert clean_text("a\x00b  \r\nline two   \n\n\n\n\nend  ") == "ab\nline two\n\nend"


def test_short_text_single_chunk():
    assert chunk_text("hello world", 3000, 400) == ["hello world"]


def test_chunks_never_exceed_size():
    paragraphs = [sentences(n) for n in (5, 120, 3, 200, 12, 60)]
    text = "\n\n".join(paragraphs)
    assert len(text) > 15000
    chunks = chunk_text(text, 3000, 400)
    assert len(chunks) > 5
    assert all(0 < len(c) <= 3000 for c in chunks)


def test_consecutive_chunks_overlap():
    chunks = chunk_text(sentences(200), 1000, 200)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous[-50:] in current


def test_no_text_lost():
    text = "\n\n".join(sentences(n, prefix=f"P{n}") for n in (10, 60, 7))
    chunks = chunk_text(text, 1000, 200)
    for sentence in re.split(r"(?<=[.!?])\s+", text.replace("\n\n", " ")):
        assert any(sentence in chunk for chunk in chunks), sentence


def test_paragraph_boundaries_preferred():
    paragraphs = ["A" * 999 + ".", "B" * 999 + ".", "C" * 999 + "."]
    chunks = chunk_text("\n\n".join(paragraphs), 3000, 400)
    assert len(chunks) == 2
    assert chunks[0].endswith("B" * 999 + ".")
    assert chunks[1].endswith("C" * 999 + ".")


def test_giant_unbroken_string_terminates():
    chunks = chunk_text("a" * 10000, 3000, 400)
    assert all(len(c) <= 3000 for c in chunks)
    assert sum(len(c) for c in chunks) >= 10000


def test_whitespace_only_gives_no_chunks():
    assert chunk_text("   \n\n  \t ", 3000, 400) == []


def test_chunk_document_keeps_pages_and_global_index():
    doc = ExtractedDoc(
        title="t",
        source_type="pdf",
        source="t.pdf",
        sections=[Section(sentences(30), 1), Section("short page", 2)],
    )
    chunks = chunk_document(doc, 1000, 200)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert chunks[-1].page == 2 and chunks[-1].content == "short page"
    assert {c.page for c in chunks[:-1]} == {1}


# --- file loaders --------------------------------------------------------------------------


def test_unsupported_extension_415():
    with pytest.raises(IngestionError) as exc:
        load_upload("notes.docx", b"PK...")
    assert exc.value.status_code == 415
    assert exc.value.message == SUPPORTED_MESSAGE == "Supported: PDF, TXT, MD"


def test_no_extension_415():
    with pytest.raises(IngestionError) as exc:
        load_upload("Makefile", b"all:")
    assert exc.value.status_code == 415


def test_extension_case_insensitive():
    doc = load_upload("README.MD", b"# Title\n\nSome text.")
    assert doc.source_type == "text"
    assert doc.title == "README"


def test_empty_file_422():
    with pytest.raises(IngestionError) as exc:
        load_upload("empty.txt", b"")
    assert exc.value.status_code == 422


def test_whitespace_only_text_422():
    with pytest.raises(IngestionError) as exc:
        load_upload("blank.txt", b"  \n\n \x00 ")
    assert exc.value.status_code == 422


def test_txt_non_utf8_replaced_and_nul_stripped():
    doc = load_upload("latin.txt", b"caf\xe9 \x00ok")
    text = doc.sections[0].text
    assert "caf�" in text
    assert "\x00" not in text


def test_utf8_bom_removed():
    doc = load_upload("bom.txt", "﻿hello".encode())
    assert doc.sections[0].text == "hello"


def test_pdf_pages_keep_page_numbers():
    doc = load_upload("two.pdf", text_pdf(["alpha content", "beta content"]))
    assert doc.source_type == "pdf"
    assert [s.page for s in doc.sections] == [1, 2]
    assert "alpha" in doc.sections[0].text and "beta" in doc.sections[1].text


def test_pdf_blank_page_skipped():
    doc = load_upload("mixed.pdf", text_pdf(["first", "", "third"]))
    assert [s.page for s in doc.sections] == [1, 3]


def test_scanned_pdf_422():
    with pytest.raises(IngestionError) as exc:
        load_upload("scan.pdf", blank_pdf())
    assert exc.value.status_code == 422
    assert "no extractable text" in exc.value.message


def test_password_pdf_422():
    with pytest.raises(IngestionError) as exc:
        load_upload("locked.pdf", encrypted_pdf("pw"))
    assert exc.value.status_code == 422
    assert "password" in exc.value.message


def test_empty_password_pdf_opens():
    doc = load_upload("open.pdf", empty_password_pdf())
    assert "Readable" in doc.sections[0].text


@pytest.mark.parametrize("data", [b"%PDF-1.4 garbage", b"not a pdf at all"])
def test_corrupt_pdf_422(data):
    with pytest.raises(IngestionError) as exc:
        load_upload("broken.pdf", data)
    assert exc.value.status_code == 422


def test_pdf_title_from_filename():
    doc = load_upload("Course Handbook.pdf", text_pdf(["content"]))
    assert doc.title == "Course Handbook"
    assert doc.source == "Course Handbook.pdf"


def test_path_in_filename_is_dropped():
    doc = load_upload("../../etc/notes.txt", b"text")
    assert doc.title == "notes"
    assert doc.source == "notes.txt"


def test_same_text_same_hash_regardless_of_filename():
    first = load_upload("a.txt", b"Same content here.")
    second = load_upload("b.md", b"Same content here.\n\n")
    assert content_hash(first) == content_hash(second)
    assert content_hash(first) != content_hash(load_upload("c.txt", b"Different."))


# --- URL safety ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/a",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://localhost/",
        "http://LOCALHOST:8000/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http:///nohost",
        "not a url",
    ],
)
def test_unsafe_urls_400(url):
    with pytest.raises(IngestionError) as exc:
        validate_public_url(url, resolve=public_resolver)
    assert exc.value.status_code == 400


def test_public_url_allowed():
    validate_public_url("https://example.com/page", resolve=public_resolver)


def test_hostname_resolving_to_private_ip_400():
    with pytest.raises(IngestionError) as exc:
        validate_public_url("http://intranet.example.com/", resolve=lambda h: ["192.168.1.2"])
    assert exc.value.status_code == 400


def test_unresolvable_host_422():
    def fail(host):
        raise OSError("Name or service not known")

    with pytest.raises(IngestionError) as exc:
        validate_public_url("http://no-such-host.invalid/", resolve=fail)
    assert exc.value.status_code == 422


# --- URL fetching (no network: MockTransport + fake resolver) --------------------------------

PAGE = """<html><head><title> Course Page </title></head><body>
<nav>Home | About</nav><header>Site header</header>
<main><h1>Welcome</h1><p>The late policy is ten percent per day.</p></main>
<script>var tracking = 1;</script><footer>Copyright footer</footer></body></html>"""


def html_response(body: str = PAGE, status: int = 200, **headers) -> httpx.Response:
    return httpx.Response(
        status,
        content=body.encode(),
        headers={"content-type": "text/html; charset=utf-8", **headers},
    )


def fetch(url: str, handler) -> ExtractedDoc:
    return fetch_url(url, transport=httpx.MockTransport(handler), resolve=public_resolver)


def test_html_extraction_strips_chrome():
    doc = fetch("https://example.com/course", lambda request: html_response())
    text = doc.sections[0].text
    assert doc.source_type == "url"
    assert doc.title == "Course Page"
    assert doc.source == "https://example.com/course"
    assert "late policy is ten percent" in text
    for chrome in ("Home | About", "Site header", "tracking", "Copyright footer"):
        assert chrome not in text


def test_sends_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers.get("user-agent")
        return html_response()

    fetch("https://example.com/", handler)
    assert seen["ua"].startswith("ML-Course-RAG-Chatbot")


def test_redirect_followed_and_final_url_recorded():
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return html_response()

    doc = fetch("https://example.com/old", handler)
    assert doc.source == "https://example.com/new"


def test_redirect_to_private_ip_400():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with pytest.raises(IngestionError) as exc:
        fetch("https://example.com/", handler)
    assert exc.value.status_code == 400
    assert requested == ["https://example.com/"]


def test_too_many_redirects_422():
    with pytest.raises(IngestionError) as exc:
        fetch("https://example.com/", lambda r: httpx.Response(302, headers={"location": "/loop"}))
    assert exc.value.status_code == 422
    assert "redirect" in exc.value.message


def test_non_html_422():
    def pdf(request):
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    with pytest.raises(IngestionError) as exc:
        fetch("https://example.com/file", pdf)
    assert exc.value.status_code == 422


def test_http_error_422():
    with pytest.raises(IngestionError) as exc:
        fetch("https://example.com/missing", lambda r: html_response(status=404))
    assert exc.value.status_code == 422
    assert "404" in exc.value.message


def test_timeout_422():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(IngestionError) as exc:
        fetch("https://example.com/", handler)
    assert exc.value.status_code == 422
    assert "timed out" in exc.value.message


def test_connection_error_422():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(IngestionError) as exc:
        fetch("https://example.com/", handler)
    assert exc.value.status_code == 422


def test_page_without_text_422():
    empty = "<html><body><script>render()</script><div id='root'></div></body></html>"
    with pytest.raises(IngestionError) as exc:
        fetch("https://example.com/app", lambda r: html_response(empty))
    assert exc.value.status_code == 422
    assert "no readable text" in exc.value.message


def test_title_falls_back_to_url():
    doc = fetch("https://example.com/x", lambda r: html_response("<p>Just text here.</p>"))
    assert doc.title == "https://example.com/x"


def test_oversized_page_422(monkeypatch):
    settings = get_settings().model_copy(update={"max_upload_mb": 1})
    monkeypatch.setattr(ingestion, "get_settings", lambda: settings)
    huge = "<p>" + "x" * (1024 * 1024 + 10) + "</p>"
    with pytest.raises(IngestionError) as exc:
        fetch("https://example.com/huge", lambda r: html_response(huge))
    assert exc.value.status_code == 422
    assert "too large" in exc.value.message
