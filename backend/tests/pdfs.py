"""Build small PDFs in memory for tests (and the sample data script)."""

from io import BytesIO

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter


def text_pdf(pages: list[str]) -> bytes:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 8, text)
    return bytes(pdf.output())


def blank_pdf() -> bytes:
    """Looks like a scanned page: a drawing but no text layer."""
    pdf = FPDF()
    pdf.add_page()
    pdf.rect(20, 20, 100, 60, style="F")
    return bytes(pdf.output())


def _encrypt(data: bytes, user_password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(data)))
    writer.encrypt(user_password=user_password, owner_password="owner-secret")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def encrypted_pdf(password: str) -> bytes:
    return _encrypt(text_pdf(["Top secret content."]), password)


def empty_password_pdf() -> bytes:
    return _encrypt(text_pdf(["Readable without a password."]), "")
