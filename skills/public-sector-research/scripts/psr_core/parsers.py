"""Bounded HTML, JSON, PDF, and text extraction into inert passages."""

from __future__ import annotations

import hashlib
import io
import json
import re
from html.parser import HTMLParser
from typing import Any, ClassVar, List, Optional, Tuple

from psr_core.models import ParsedDocument, Passage

MAX_INPUT_BYTES = 20 * 1024 * 1024
MAX_PASSAGES = 2_000
MAX_PASSAGE_CHARS = 4_000
MAX_TOTAL_TEXT_CHARS = 1_000_000


class DocumentParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_document(body: bytes, media_type: Optional[str]) -> ParsedDocument:
    if len(body) > MAX_INPUT_BYTES:
        raise DocumentParseError("INPUT_TOO_LARGE", "document exceeds 20 MiB parser limit")
    kind = _detect_kind(body, media_type)
    if kind == "HTML":
        return _parse_html(body, media_type)
    if kind == "JSON":
        return _parse_json(body)
    if kind == "PDF":
        return _parse_pdf(body)
    if kind == "TEXT":
        return _parse_text_bytes(body, media_type)
    raise DocumentParseError("UNSUPPORTED_KIND", "unsupported binary document")


def extracted_markdown(document: ParsedDocument) -> str:
    lines = []
    if document.title:
        lines.extend([f"# {document.title}", ""])
    for passage in document.passages:
        if passage.heading:
            lines.extend([f"## {passage.heading}", ""])
        lines.extend([passage.text, "", f"<!-- locator: {passage.locator} -->", ""])
    return "\n".join(lines).strip() + "\n"


def _detect_kind(body: bytes, media_type: Optional[str]) -> str:
    declared = (media_type or "").split(";", 1)[0].strip().lower()
    prefix = body[:512].lstrip()
    if body.startswith(b"%PDF-") or declared == "application/pdf":
        return "PDF"
    if declared in {"application/json", "application/ld+json"}:
        return "JSON"
    if declared in {"text/html", "application/xhtml+xml"}:
        return "HTML"
    if prefix.startswith((b"{", b"[")):
        try:
            json.loads(body.decode("utf-8"))
            return "JSON"
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    lowered = prefix.lower()
    if b"<html" in lowered or b"<!doctype html" in lowered:
        return "HTML"
    if declared.startswith("text/") or _looks_textual(body):
        return "TEXT"
    return "BINARY"


def _looks_textual(body: bytes) -> bool:
    if not body:
        return True
    sample = body[:4_096]
    if b"\x00" in sample:
        return False
    printable = sum(byte in b"\t\n\r" or 32 <= byte <= 126 or byte >= 128 for byte in sample)
    return printable / len(sample) > 0.9


class _PassageHTMLParser(HTMLParser):
    _BLOCK_TAGS: ClassVar[set] = {
        "p",
        "li",
        "td",
        "th",
        "blockquote",
        "pre",
        "dd",
        "dt",
        "figcaption",
    }
    _IGNORE_TAGS: ClassVar[set] = {
        "script",
        "style",
        "noscript",
        "svg",
        "template",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: List[str] = []
        self.passages: List[Tuple[Optional[str], str]] = []
        self.current_heading: Optional[str] = None
        self._heading_tag: Optional[str] = None
        self._heading_parts: List[str] = []
        self._title_depth = 0
        self._ignore_depth = 0
        self._block_tag: Optional[str] = None
        self._block_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in self._IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if tag == "title":
            self._title_depth += 1
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_tag = tag
            self._heading_parts = []
        if tag in self._BLOCK_TAGS and self._block_tag is None:
            self._block_tag = tag
            self._block_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._IGNORE_TAGS:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if self._heading_tag == tag:
            heading = _normalize(" ".join(self._heading_parts))
            if heading:
                self.current_heading = heading[:300]
            self._heading_tag = None
            self._heading_parts = []
        if self._block_tag == tag:
            text = _normalize(" ".join(self._block_parts))
            if text:
                self.passages.append((self.current_heading, text))
            self._block_tag = None
            self._block_parts = []

    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return
        if self._title_depth:
            self.title_parts.append(data)
        if self._heading_tag:
            self._heading_parts.append(data)
        if self._block_tag:
            self._block_parts.append(data)


def _parse_html(body: bytes, media_type: Optional[str]) -> ParsedDocument:
    text, warnings = _decode(body, media_type)
    parser = _PassageHTMLParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as error:
        raise DocumentParseError("INVALID_HTML", f"HTML parsing failed: {error}") from error
    title = _normalize(" ".join(parser.title_parts)) or None
    passages = []
    total = 0
    for index, (heading, content) in enumerate(parser.passages, 1):
        if len(passages) >= MAX_PASSAGES or total >= MAX_TOTAL_TEXT_CHARS:
            warnings.append("passage or total text limit reached")
            break
        for part_index, part in enumerate(_split_long(content), 1):
            locator = f"html:block:{index}"
            if len(_split_long(content)) > 1:
                locator += f":part:{part_index}"
            passages.append(_passage(locator, part, heading))
            total += len(part)
    if not passages:
        fallback = _normalize(re.sub(r"<[^>]+>", " ", text))
        if fallback:
            passages.append(_passage("html:document", fallback[:MAX_PASSAGE_CHARS], None))
    if not passages:
        raise DocumentParseError("DOCUMENT_EMPTY", "HTML contained no reviewable text")
    return ParsedDocument(kind="HTML", title=title, passages=passages, warnings=warnings)


def _parse_json(body: bytes) -> ParsedDocument:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DocumentParseError("INVALID_JSON", f"JSON parsing failed: {error}") from error
    passages: List[Passage] = []
    warnings: List[str] = []
    total = 0

    def visit(value: Any, pointer: str, depth: int) -> None:
        nonlocal total
        if depth > 32 or len(passages) >= MAX_PASSAGES or total >= MAX_TOTAL_TEXT_CHARS:
            if "JSON extraction limit reached" not in warnings:
                warnings.append("JSON extraction limit reached")
            return
        if isinstance(value, dict):
            for key, child in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                visit(child, f"{pointer}/{escaped}", depth + 1)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{pointer}/{index}", depth + 1)
            return
        if value is None:
            return
        text = _normalize(str(value))
        if not text:
            return
        for part_index, part in enumerate(_split_long(text), 1):
            locator = pointer or "/"
            if len(_split_long(text)) > 1:
                locator += f"#part-{part_index}"
            passages.append(_passage(locator, part, None))
            total += len(part)

    visit(payload, "", 0)
    if not passages:
        raise DocumentParseError("DOCUMENT_EMPTY", "JSON contained no reviewable scalar values")
    title = None
    if isinstance(payload, dict):
        for key in ("title", "name", "documentTitle", "subject"):
            value = payload.get(key)
            if isinstance(value, str) and _normalize(value):
                title = _normalize(value)[:300]
                break
    return ParsedDocument(kind="JSON", title=title, passages=passages, warnings=warnings)


def _parse_pdf(body: bytes) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise DocumentParseError(
            "PDF_DEPENDENCY_MISSING",
            "PDF extraction requires the optional pypdf package",
        ) from error
    try:
        reader = PdfReader(io.BytesIO(body), strict=False)
    except Exception as error:
        raise DocumentParseError("INVALID_PDF", f"PDF parsing failed: {error}") from error
    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as error:
            raise DocumentParseError("ENCRYPTED_PDF", "encrypted PDF cannot be read") from error
        if not unlocked:
            raise DocumentParseError("ENCRYPTED_PDF", "encrypted PDF cannot be read")
    if len(reader.pages) > 300:
        raise DocumentParseError("PDF_PAGE_LIMIT", "PDF exceeds 300 page limit")
    metadata = reader.metadata or {}
    title_value = getattr(metadata, "title", None)
    title = _normalize(str(title_value))[:300] if title_value else None
    passages: List[Passage] = []
    warnings: List[str] = []
    total = 0
    for page_number, page in enumerate(reader.pages, 1):
        try:
            text = _normalize(page.extract_text() or "")
        except Exception:
            warnings.append(f"page {page_number} text extraction failed")
            continue
        if not text:
            continue
        for part_index, part in enumerate(_split_long(text), 1):
            locator = f"pdf:page:{page_number}"
            if len(_split_long(text)) > 1:
                locator += f":part:{part_index}"
            passages.append(_passage(locator, part, f"{page_number}쪽"))
            total += len(part)
            if len(passages) >= MAX_PASSAGES or total >= MAX_TOTAL_TEXT_CHARS:
                warnings.append("PDF extraction limit reached")
                break
        if len(passages) >= MAX_PASSAGES or total >= MAX_TOTAL_TEXT_CHARS:
            break
    if not passages:
        raise DocumentParseError(
            "OCR_REQUIRED",
            "PDF contains no extractable text; OCR may be needed",
        )
    return ParsedDocument(kind="PDF", title=title, passages=passages, warnings=warnings)


def _parse_text_bytes(body: bytes, media_type: Optional[str]) -> ParsedDocument:
    text, warnings = _decode(body, media_type)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [_normalize(value) for value in re.split(r"\n\s*\n", normalized)]
    passages = []
    total = 0
    for index, block in enumerate((value for value in blocks if value), 1):
        for part_index, part in enumerate(_split_long(block), 1):
            locator = f"text:block:{index}"
            if len(_split_long(block)) > 1:
                locator += f":part:{part_index}"
            passages.append(_passage(locator, part, None))
            total += len(part)
            if len(passages) >= MAX_PASSAGES or total >= MAX_TOTAL_TEXT_CHARS:
                warnings.append("text extraction limit reached")
                break
        if len(passages) >= MAX_PASSAGES or total >= MAX_TOTAL_TEXT_CHARS:
            break
    if not passages:
        raise DocumentParseError("DOCUMENT_EMPTY", "text document is empty")
    return ParsedDocument(kind="TEXT", title=None, passages=passages, warnings=warnings)


def _decode(body: bytes, media_type: Optional[str]) -> Tuple[str, List[str]]:
    declared = ""
    if media_type and "charset=" in media_type.lower():
        declared = media_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip()
    encodings = [value for value in (declared, "utf-8", "cp949", "euc-kr") if value]
    warnings: List[str] = []
    for encoding in encodings:
        try:
            text = body.decode(encoding)
            if encoding != encodings[0]:
                warnings.append(f"decoded with fallback encoding {encoding}")
            return text, warnings
        except (LookupError, UnicodeDecodeError):
            continue
    warnings.append("invalid bytes replaced during decoding")
    return body.decode("utf-8", errors="replace"), warnings


def _passage(locator: str, text: str, heading: Optional[str]) -> Passage:
    digest = hashlib.sha256(f"{locator}\0{text}".encode("utf-8")).hexdigest()[:20]
    return Passage(id=f"psg-{digest}", text=text, locator=locator, heading=heading)


def _split_long(text: str) -> List[str]:
    if len(text) <= MAX_PASSAGE_CHARS:
        return [text]
    parts = []
    remaining = text
    while remaining:
        if len(remaining) <= MAX_PASSAGE_CHARS:
            parts.append(remaining)
            break
        cut = remaining.rfind(" ", 0, MAX_PASSAGE_CHARS)
        if cut < MAX_PASSAGE_CHARS // 2:
            cut = MAX_PASSAGE_CHARS
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [part for part in parts if part]


def _normalize(value: str) -> str:
    return " ".join(value.replace("\x00", " ").split())
