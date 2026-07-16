"""Bounded JSON traversal that emits JSON Pointer passages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
from psr_mcp.parsers.text import decode_document, normalize_space


def parse_json(
    body: bytes,
    *,
    content_type: str | None,
    sniff: SniffResult,
    limits: ParserLimits,
) -> ParsedDocument:
    text, decode_warnings = decode_document(body, content_type)
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        raise ParseError(
            ParseErrorCode.INVALID_DOCUMENT,
            "JSON document is malformed or too deeply nested",
        ) from None
    builder = _JsonPassageBuilder(limits)
    builder.walk(payload, pointer="", depth=0)
    if not builder.passages:
        raise ParseError(
            ParseErrorCode.DOCUMENT_EMPTY,
            "JSON document did not contain usable scalar values",
        )
    warnings = list(decode_warnings)
    if sniff.declared_mismatch:
        warnings.append("DECLARED_TYPE_MISMATCH")
    title = payload.get("title") if isinstance(payload, dict) else None
    return ParsedDocument(
        kind=DocumentKind.JSON,
        title=normalize_space(title) if isinstance(title, str) else None,
        passages=tuple(builder.passages),
        warnings=tuple(warnings),
        sniff=sniff,
    )


@dataclass(slots=True)
class _JsonPassageBuilder:
    limits: ParserLimits
    passages: list[Passage] = field(init=False, default_factory=list)
    items: int = field(init=False, default=0)
    total_chars: int = field(init=False, default=0)

    def walk(self, value: Any, *, pointer: str, depth: int) -> None:
        if depth > self.limits.max_json_depth:
            raise ParseError(
                ParseErrorCode.RESOURCE_LIMIT,
                "JSON document exceeds the parser depth limit",
            )
        self.items += 1
        if self.items > self.limits.max_json_items:
            raise ParseError(
                ParseErrorCode.RESOURCE_LIMIT,
                "JSON document exceeds the parser item limit",
            )
        if isinstance(value, dict):
            for key, item in value.items():
                self.walk(
                    item,
                    pointer=f"{pointer}/{_pointer_token(str(key))}",
                    depth=depth + 1,
                )
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self.walk(item, pointer=f"{pointer}/{index}", depth=depth + 1)
            return
        self._add_scalar(value, pointer or "/")

    def _add_scalar(self, value: Any, pointer: str) -> None:
        if value is None:
            text = "null"
        elif isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, (int, float)):
            text = str(value)
        elif isinstance(value, str):
            text = normalize_space(value)
        else:
            return
        if not text:
            return
        for chunk_index, chunk in enumerate(
            _chunks(text, self.limits.max_passage_chars),
            start=1,
        ):
            self.total_chars += len(chunk)
            if self.total_chars > self.limits.max_total_text_chars:
                raise ParseError(
                    ParseErrorCode.RESOURCE_LIMIT,
                    "JSON text exceeds the parser character limit",
                )
            if len(self.passages) >= self.limits.max_passages:
                raise ParseError(
                    ParseErrorCode.RESOURCE_LIMIT,
                    "JSON document exceeds the parser passage limit",
                )
            locator = f"json-pointer:{pointer}"
            if len(text) > self.limits.max_passage_chars:
                locator = f"{locator}:chunk-{chunk_index}"
            self.passages.append(
                Passage(
                    id=f"p-{len(self.passages) + 1:04d}",
                    text=chunk,
                    locator=locator,
                )
            )


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _chunks(value: str, size: int) -> list[str]:
    return [value[index : index + size] for index in range(0, len(value), size)]
