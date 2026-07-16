"""Small magic-byte and declared-type document classifier."""

from __future__ import annotations

from psr_mcp.parsers.models import DocumentKind, SniffResult


def sniff_document(body: bytes, content_type: str | None) -> SniffResult:
    declared_media_type = _media_type(content_type)
    declared_kind = _declared_kind(declared_media_type)
    detected_kind, detected_media_type = _detect(body)
    mismatch = (
        declared_kind is not None
        and declared_kind is not DocumentKind.BINARY
        and declared_kind is not detected_kind
    )
    return SniffResult(
        kind=detected_kind,
        declared_media_type=declared_media_type,
        detected_media_type=detected_media_type,
        declared_mismatch=mismatch,
    )


def _detect(body: bytes) -> tuple[DocumentKind, str | None]:
    sample = body[:4_096]
    stripped = sample.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")
    lowered = stripped[:512].lower()
    if b"%PDF-" in sample[:1_024]:
        return DocumentKind.PDF, "application/pdf"
    if (
        lowered.startswith(b"<!doctype html")
        or lowered.startswith(b"<html")
        or b"<html" in lowered
        or b"<body" in lowered
    ):
        return DocumentKind.HTML, "text/html"
    if stripped.startswith((b"{", b"[")):
        return DocumentKind.JSON, "application/json"
    if not body:
        return DocumentKind.TEXT, "text/plain"
    if _looks_binary(sample):
        return DocumentKind.BINARY, "application/octet-stream"
    return DocumentKind.TEXT, "text/plain"


def _looks_binary(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    control = sum(byte < 9 or (13 < byte < 32) for byte in sample)
    return control / len(sample) > 0.05


def _media_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    value = content_type.partition(";")[0].strip().casefold()
    return value or None


def _declared_kind(media_type: str | None) -> DocumentKind | None:
    if media_type is None:
        return None
    if media_type in {"text/html", "application/xhtml+xml"}:
        return DocumentKind.HTML
    if media_type == "application/pdf":
        return DocumentKind.PDF
    if media_type == "application/json" or media_type.endswith("+json"):
        return DocumentKind.JSON
    if media_type.startswith("text/"):
        return DocumentKind.TEXT
    return DocumentKind.BINARY
