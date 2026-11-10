from __future__ import annotations

import io
from dataclasses import dataclass

from docx import Document
from pypdf import PdfReader


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    page_count: int
    parser_version: str = "local-parser-1"


class UnsupportedDocumentError(ValueError):
    pass


def parse_document(*, content: bytes, content_type: str, filename: str) -> ParsedDocument:
    name = filename.lower()
    if content_type == "application/pdf" or name.endswith(".pdf"):
        return _parse_pdf(content)
    if (
        content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or name.endswith(".docx")
    ):
        return _parse_docx(content)
    raise UnsupportedDocumentError("Unsupported file type.")


def _parse_pdf(content: bytes) -> ParsedDocument:
    reader = PdfReader(io.BytesIO(content))
    if getattr(reader, "is_encrypted", False):
        raise UnsupportedDocumentError("Encrypted PDF is not allowed.")
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()
    if not text:
        raise UnsupportedDocumentError("No extractable text. Scanned OCR is not enabled yet.")
    return ParsedDocument(text=text, page_count=len(reader.pages))


def _parse_docx(content: bytes) -> ParsedDocument:
    document = Document(io.BytesIO(content))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs).strip()
    if not text:
        raise UnsupportedDocumentError("DOCX contained no text.")
    return ParsedDocument(text=text, page_count=max(1, len(paragraphs) // 40))
