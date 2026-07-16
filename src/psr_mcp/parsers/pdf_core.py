"""Bounded pypdf extraction logic executed inside an isolated worker."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from psr_mcp.parsers.models import ParseErrorCode
from psr_mcp.parsers.text import normalize_space


class PdfCoreError(ValueError):
    def __init__(self, code: ParseErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PdfPageText:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class PdfExtraction:
    title: str | None
    page_count: int
    pages: tuple[PdfPageText, ...]


def extract_pdf(
    body: bytes,
    *,
    max_pages: int,
    max_total_text_chars: int,
) -> PdfExtraction:
    try:
        reader = PdfReader(BytesIO(body), strict=False)
        if reader.is_encrypted and not _decrypt_empty_password(reader):
            raise PdfCoreError(
                ParseErrorCode.ENCRYPTED_DOCUMENT,
                "PDF requires a password and was not opened",
            )
        page_count = len(reader.pages)
    except PdfCoreError:
        raise
    except Exception:
        raise PdfCoreError(
            ParseErrorCode.INVALID_DOCUMENT,
            "PDF structure could not be read safely",
        ) from None
    if page_count == 0:
        raise PdfCoreError(
            ParseErrorCode.DOCUMENT_EMPTY,
            "PDF did not contain any pages",
        )
    if page_count > max_pages:
        raise PdfCoreError(
            ParseErrorCode.RESOURCE_LIMIT,
            "PDF exceeds the configured page limit",
        )

    pages: list[PdfPageText] = []
    total_chars = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            extracted = page.extract_text() or ""
        except Exception:
            raise PdfCoreError(
                ParseErrorCode.INVALID_DOCUMENT,
                "PDF page text could not be extracted safely",
            ) from None
        text = normalize_space(extracted.replace("\x00", " "))
        if not text:
            continue
        total_chars += len(text)
        if total_chars > max_total_text_chars:
            raise PdfCoreError(
                ParseErrorCode.RESOURCE_LIMIT,
                "PDF text exceeds the configured character limit",
            )
        pages.append(PdfPageText(page_number=page_number, text=text))
    if not pages:
        raise PdfCoreError(
            ParseErrorCode.OCR_REQUIRED,
            "PDF contains no extractable text and requires OCR review",
        )
    return PdfExtraction(
        title=_reader_title(reader),
        page_count=page_count,
        pages=tuple(pages),
    )


def _decrypt_empty_password(reader: PdfReader) -> bool:
    try:
        return bool(reader.decrypt(""))
    except Exception:
        return False


def _title(metadata: Any) -> str | None:
    raw = getattr(metadata, "title", None)
    if not isinstance(raw, str):
        return None
    return normalize_space(raw)[:500] or None


def _reader_title(reader: PdfReader) -> str | None:
    try:
        metadata = reader.metadata
    except Exception:
        return None
    return _title(metadata)
