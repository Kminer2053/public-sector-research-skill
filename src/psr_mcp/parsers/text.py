"""Encoding and plain-text passage helpers."""

from __future__ import annotations

import re

from psr_mcp.parsers.models import (
    DocumentKind,
    ParsedDocument,
    ParseError,
    ParseErrorCode,
    ParserLimits,
    Passage,
    SniffResult,
)


def decode_document(body: bytes, content_type: str | None) -> tuple[str, tuple[str, ...]]:
    candidates = _encoding_candidates(content_type)
    for encoding in candidates:
        try:
            return body.decode(encoding), ()
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace"), ("DECODE_REPLACEMENT",)


def parse_text(
    text: str,
    *,
    sniff: SniffResult,
    limits: ParserLimits,
    warnings: tuple[str, ...] = (),
) -> ParsedDocument:
    passages: list[Passage] = []
    total_chars = 0
    lines = text.splitlines()
    block_lines: list[str] = []
    block_start = 1

    def flush(end_line: int) -> None:
        nonlocal total_chars, block_lines, block_start
        value = normalize_space(" ".join(block_lines))
        block_lines = []
        if not value:
            return
        for chunk_index, chunk in enumerate(_chunks(value, limits.max_passage_chars), start=1):
            total_chars += len(chunk)
            if total_chars > limits.max_total_text_chars:
                raise ParseError(
                    ParseErrorCode.RESOURCE_LIMIT,
                    "document text exceeds the parser character limit",
                )
            if len(passages) >= limits.max_passages:
                raise ParseError(
                    ParseErrorCode.RESOURCE_LIMIT,
                    "document exceeds the parser passage limit",
                )
            suffix = f":chunk-{chunk_index}" if len(value) > limits.max_passage_chars else ""
            passages.append(
                Passage(
                    id=f"p-{len(passages) + 1:04d}",
                    text=chunk,
                    locator=f"lines:{block_start}-{end_line}{suffix}",
                )
            )

    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            if not block_lines:
                block_start = line_number
            block_lines.append(line)
        else:
            flush(line_number - 1)
    flush(len(lines))
    if not passages:
        raise ParseError(
            ParseErrorCode.DOCUMENT_EMPTY,
            "document did not contain usable text",
        )
    return ParsedDocument(
        kind=DocumentKind.TEXT,
        title=None,
        passages=tuple(passages),
        warnings=warnings,
        sniff=sniff,
    )


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def _chunks(value: str, size: int) -> list[str]:
    return [value[index : index + size] for index in range(0, len(value), size)]


def _encoding_candidates(content_type: str | None) -> tuple[str, ...]:
    declared: list[str] = []
    if content_type:
        match = re.search(r"charset\s*=\s*[\"']?([^;\"'\s]+)", content_type, re.I)
        if match:
            declared.append(match.group(1))
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        if encoding not in declared:
            declared.append(encoding)
    return tuple(declared)
