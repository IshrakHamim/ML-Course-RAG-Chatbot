"""Turn uploads and web pages into clean text sections, then into chunks. No database access."""

import hashlib
import ipaddress
import logging
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Literal

import httpx
from bs4 import BeautifulSoup, NavigableString
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SUPPORTED_MESSAGE = "Supported: PDF, TXT, MD"
TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
URL_TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 5
USER_AGENT = "ML-Course-RAG-Chatbot/0.1 (course demo)"
BLOCK_TAGS = [
    "p", "div", "section", "article", "li", "ul", "ol", "dl", "dt", "dd", "table", "tr", "td",
    "th", "caption", "figcaption", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
]  # fmt: skip
NON_CONTENT_TAGS = [
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "aside",
    "form",
    "svg",
]

Resolver = Callable[[str], list[str]]


@dataclass
class Section:
    text: str
    page: int | None


@dataclass
class ExtractedDoc:
    title: str
    source_type: Literal["pdf", "text", "url"]
    source: str
    sections: list[Section]


@dataclass
class ChunkDraft:
    content: str
    page: int | None
    chunk_index: int


class IngestionError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# --- text cleaning and chunking ------------------------------------------------------------


def clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _pieces(text: str, budget: int) -> list[tuple[str, str]]:
    """Split text into (joiner, piece) pairs no longer than `budget`: whole paragraphs where
    they fit, otherwise sentences, otherwise hard slices."""
    pieces: list[tuple[str, str]] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= budget:
            pieces.append(("\n\n", paragraph))
            continue
        joiner = "\n\n"
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            for start in range(0, len(sentence), budget):
                pieces.append((joiner, sentence[start : start + budget]))
                joiner = " "
    return pieces


def _overlap_tail(previous: str, overlap: int) -> str:
    tail = previous[-overlap:] if overlap else ""
    if len(previous) > overlap:
        match = re.search(r"\s", tail)
        if match:
            tail = tail[match.end() :]  # start the overlap at a word boundary
    return tail.strip()


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    overlap = min(overlap, size // 2)
    budget = size - overlap - 1  # room for the overlap prefix plus a joining space
    bodies: list[str] = []
    current = ""
    for joiner, piece in _pieces(text, budget):
        candidate = f"{current}{joiner}{piece}" if current else piece
        if len(candidate) <= budget:
            current = candidate
        else:
            if current:
                bodies.append(current)
            current = piece
    if current:
        bodies.append(current)

    chunks: list[str] = []
    for body in bodies:
        tail = _overlap_tail(chunks[-1], overlap) if chunks else ""
        chunks.append(f"{tail} {body}" if tail else body)
    return chunks


def chunk_document(doc: ExtractedDoc, size: int, overlap: int) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for section in doc.sections:
        for content in chunk_text(section.text, size, overlap):
            drafts.append(ChunkDraft(content=content, page=section.page, chunk_index=len(drafts)))
    return drafts


def content_hash(doc: ExtractedDoc) -> str:
    joined = "\n\n".join(section.text for section in doc.sections)
    return hashlib.sha256(joined.encode()).hexdigest()


# --- file uploads --------------------------------------------------------------------------


def _safe_filename(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).name or "document"


def check_supported(filename: str) -> None:
    extension = PurePosixPath(_safe_filename(filename)).suffix.lower()
    if extension != ".pdf" and extension not in TEXT_EXTENSIONS:
        raise IngestionError(415, SUPPORTED_MESSAGE)


def load_upload(filename: str, data: bytes) -> ExtractedDoc:
    check_supported(filename)
    name = _safe_filename(filename)
    path = PurePosixPath(name)
    extension = path.suffix.lower()
    if not data:
        raise IngestionError(422, "The file is empty")
    title = path.stem or name
    if extension == ".pdf":
        return ExtractedDoc(title, "pdf", name, _pdf_sections(data))
    text = clean_text(data.decode("utf-8", errors="replace").removeprefix("﻿"))
    if not text:
        raise IngestionError(422, "The file has no text")
    return ExtractedDoc(title, "text", name, [Section(text, None)])


def _pdf_sections(data: bytes) -> list[Section]:
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise IngestionError(422, "The PDF is password-protected; upload an unlocked copy")
        sections = []
        for number, page in enumerate(reader.pages, start=1):
            text = clean_text(page.extract_text() or "")
            if text:
                sections.append(Section(text, number))
    except IngestionError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, OSError) as exc:
        logger.info("Unreadable PDF: %s", exc)
        raise IngestionError(422, "Could not read the PDF file (it may be damaged)") from None
    if not sections:
        raise IngestionError(422, "The PDF has no extractable text (it may be a scanned image)")
    return sections


# --- web pages -----------------------------------------------------------------------------


def _resolve(host: str) -> list[str]:
    return [info[4][0].split("%")[0] for info in socket.getaddrinfo(host, None)]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_public_url(url: str, resolve: Resolver = _resolve) -> None:
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, TypeError):
        raise IngestionError(400, "Invalid URL") from None
    if parsed.scheme not in ("http", "https"):
        raise IngestionError(400, "Only http and https URLs are allowed")
    host = parsed.host.lower()
    if not host:
        raise IngestionError(400, "Invalid URL")
    if host == "localhost" or host.endswith(".localhost"):
        raise IngestionError(400, "URLs pointing to this machine are not allowed")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = resolve(host)
        except OSError:
            raise IngestionError(422, f"Could not resolve host {host}") from None
    if not addresses or not all(_is_public(address) for address in addresses):
        raise IngestionError(400, "URLs pointing to private or local addresses are not allowed")


def _html_to_doc(html: str, url: str) -> ExtractedDoc:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(NON_CONTENT_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    # Inline elements (links, bold, citations) stay on one line; block elements get line breaks.
    for node in root.find_all(string=True):
        if type(node) is NavigableString:
            node.replace_with(re.sub(r"\s+", " ", str(node)))
        else:  # comments, doctype, CDATA, processing instructions
            node.extract()
    for br in root.find_all("br"):
        br.replace_with("\n")
    for block in root.find_all(BLOCK_TAGS):
        block.insert_before("\n")
        block.append("\n")
    lines = (line.strip() for line in root.get_text().split("\n"))
    text = clean_text("\n".join(lines))
    if not text:
        raise IngestionError(422, "The page has no readable text (it may need JavaScript)")
    return ExtractedDoc(title or url, "url", url, [Section(text, None)])


def _read_page(response: httpx.Response, max_bytes: int) -> str:
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in HTML_CONTENT_TYPES:
        raise IngestionError(422, f"The URL is not an HTML page ({content_type or 'unknown type'})")
    body = bytearray()
    for part in response.iter_bytes():
        body.extend(part)
        if len(body) > max_bytes:
            raise IngestionError(422, "The page is too large")
    try:
        return body.decode(response.encoding or "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch_url(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    resolve: Resolver = _resolve,
) -> ExtractedDoc:
    max_bytes = get_settings().max_upload_bytes
    current = url.strip()
    with httpx.Client(
        timeout=URL_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
        transport=transport,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_public_url(current, resolve)
            try:
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        current = str(response.url.join(response.headers["location"]))
                        continue
                    if response.status_code >= 400:
                        raise IngestionError(422, f"The URL returned HTTP {response.status_code}")
                    return _html_to_doc(_read_page(response, max_bytes), current)
            except httpx.TimeoutException:
                raise IngestionError(
                    422, f"The URL timed out after {URL_TIMEOUT_SECONDS} seconds"
                ) from None
            except httpx.HTTPError as exc:
                logger.info("Fetching %s failed: %s", current, exc)
                raise IngestionError(422, "Could not reach the URL") from None
    raise IngestionError(422, "The URL has too many redirects")
