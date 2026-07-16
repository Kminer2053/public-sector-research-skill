"""Parent-side PDF parser that delegates untrusted work to a subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

from psr_mcp.parsers.models import (
    DocumentKind,
    ParsedDocument,
    ParseError,
    ParseErrorCode,
    ParserLimits,
    Passage,
    SniffResult,
)


def parse_pdf(
    body: bytes,
    *,
    sniff: SniffResult,
    limits: ParserLimits,
) -> ParsedDocument:
    command = (
        sys.executable,
        "-m",
        "psr_mcp.parser_workers.pdf",
        "--max-input-bytes",
        str(limits.max_input_bytes),
        "--max-pages",
        str(limits.max_pdf_pages),
        "--max-text-chars",
        str(limits.max_total_text_chars),
        "--memory-bytes",
        str(limits.pdf_worker_memory_bytes),
        "--cpu-seconds",
        str(max(1, int(limits.pdf_timeout_seconds) + 1)),
    )
    try:
        completed = subprocess.run(
            command,
            input=body,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=limits.pdf_timeout_seconds,
            check=False,
            env={
                "PYTHONHASHSEED": "0",
                "PYTHONUTF8": "1",
            },
        )
    except subprocess.TimeoutExpired:
        raise ParseError(
            ParseErrorCode.RESOURCE_LIMIT,
            "PDF parser exceeded its wall-time limit",
        ) from None
    if completed.returncode != 0:
        raise ParseError(
            ParseErrorCode.INVALID_DOCUMENT,
            "PDF parser worker exited unexpectedly",
        )
    payload = _payload(completed.stdout)
    if payload.get("status") == "error":
        raise ParseError(
            _error_code(payload.get("code")),
            "PDF could not be converted into reviewable text",
        )
    if payload.get("status") != "ok":
        raise ParseError(
            ParseErrorCode.INVALID_DOCUMENT,
            "PDF parser worker returned an invalid result",
        )
    pages = _pages(payload.get("pages"), limits)
    if not pages:
        raise ParseError(
            ParseErrorCode.DOCUMENT_EMPTY,
            "PDF parser returned no usable passages",
        )
    warnings = ("DECLARED_TYPE_MISMATCH",) if sniff.declared_mismatch else ()
    title = payload.get("title")
    return ParsedDocument(
        kind=DocumentKind.PDF,
        title=title if isinstance(title, str) else None,
        passages=tuple(pages),
        warnings=warnings,
        sniff=sniff,
    )


def _payload(raw: bytes) -> Mapping[str, Any]:
    if len(raw) > 8_388_608:
        raise ParseError(
            ParseErrorCode.RESOURCE_LIMIT,
            "PDF parser output exceeded its byte limit",
        )
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ParseError(
            ParseErrorCode.INVALID_DOCUMENT,
            "PDF parser worker returned malformed output",
        ) from None
    if not isinstance(payload, dict):
        raise ParseError(
            ParseErrorCode.INVALID_DOCUMENT,
            "PDF parser worker output must be an object",
        )
    return payload


def _pages(value: object, limits: ParserLimits) -> list[Passage]:
    if not isinstance(value, list):
        raise ParseError(
            ParseErrorCode.INVALID_DOCUMENT,
            "PDF parser pages must be an array",
        )
    passages: list[Passage] = []
    total_chars = 0
    for record in value:
        if not isinstance(record, dict):
            raise ParseError(
                ParseErrorCode.INVALID_DOCUMENT,
                "PDF parser page entry must be an object",
            )
        page_number = record.get("page_number")
        text = record.get("text")
        if (
            isinstance(page_number, bool)
            or not isinstance(page_number, int)
            or page_number < 1
            or not isinstance(text, str)
            or not text
        ):
            raise ParseError(
                ParseErrorCode.INVALID_DOCUMENT,
                "PDF parser page entry is invalid",
            )
        for chunk_index, chunk in enumerate(
            _chunks(text, limits.max_passage_chars),
            start=1,
        ):
            total_chars += len(chunk)
            if total_chars > limits.max_total_text_chars or len(passages) >= limits.max_passages:
                raise ParseError(
                    ParseErrorCode.RESOURCE_LIMIT,
                    "PDF passages exceeded the parser output limit",
                )
            locator = f"pdf:page:{page_number}"
            if len(text) > limits.max_passage_chars:
                locator = f"{locator}:chunk-{chunk_index}"
            passages.append(
                Passage(
                    id=f"p-{len(passages) + 1:04d}",
                    text=chunk,
                    locator=locator,
                )
            )
    return passages


def _error_code(value: object) -> ParseErrorCode:
    if isinstance(value, str):
        try:
            return ParseErrorCode(value)
        except ValueError:
            pass
    return ParseErrorCode.INVALID_DOCUMENT


def _chunks(value: str, size: int) -> list[str]:
    return [value[index : index + size] for index in range(0, len(value), size)]
