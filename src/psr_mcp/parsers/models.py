"""Parser contracts shared by HTML, JSON, and future PDF adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DocumentKind(StrEnum):
    HTML = "HTML"
    JSON = "JSON"
    PDF = "PDF"
    TEXT = "TEXT"
    BINARY = "BINARY"


class ParseErrorCode(StrEnum):
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    INVALID_ENCODING = "INVALID_ENCODING"
    INVALID_DOCUMENT = "INVALID_DOCUMENT"
    DOCUMENT_EMPTY = "DOCUMENT_EMPTY"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    UNSUPPORTED_KIND = "UNSUPPORTED_KIND"
    OCR_REQUIRED = "OCR_REQUIRED"
    ENCRYPTED_DOCUMENT = "ENCRYPTED_DOCUMENT"


class ParseError(ValueError):
    def __init__(
        self,
        code: ParseErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_input_bytes: int = 10_485_760
    max_nodes: int = 50_000
    max_passages: int = 2_000
    max_total_text_chars: int = 1_000_000
    max_passage_chars: int = 4_000
    max_json_depth: int = 32
    max_json_items: int = 50_000
    max_pdf_pages: int = 200
    pdf_timeout_seconds: float = 5.0
    pdf_worker_memory_bytes: int = 536_870_912

    def __post_init__(self) -> None:
        bounded = {
            "max_input_bytes": (self.max_input_bytes, 1, 104_857_600),
            "max_nodes": (self.max_nodes, 1, 1_000_000),
            "max_passages": (self.max_passages, 1, 100_000),
            "max_total_text_chars": (self.max_total_text_chars, 1, 10_000_000),
            "max_passage_chars": (self.max_passage_chars, 32, 100_000),
            "max_json_depth": (self.max_json_depth, 1, 128),
            "max_json_items": (self.max_json_items, 1, 1_000_000),
            "max_pdf_pages": (self.max_pdf_pages, 1, 2_000),
            "pdf_worker_memory_bytes": (
                self.pdf_worker_memory_bytes,
                67_108_864,
                2_147_483_648,
            ),
        }
        for name, (value, minimum, maximum) in bounded.items():
            if value < minimum or value > maximum:
                raise ValueError(f"{name} must be {minimum}..{maximum}")
        if self.pdf_timeout_seconds < 0.1 or self.pdf_timeout_seconds > 20:
            raise ValueError("pdf_timeout_seconds must be 0.1..20")


@dataclass(frozen=True, slots=True)
class SniffResult:
    kind: DocumentKind
    declared_media_type: str | None
    detected_media_type: str | None
    declared_mismatch: bool


@dataclass(frozen=True, slots=True)
class Passage:
    id: str
    text: str
    locator: str
    heading: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    kind: DocumentKind
    title: str | None
    passages: tuple[Passage, ...]
    warnings: tuple[str, ...]
    sniff: SniffResult
