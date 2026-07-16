"""Document parser dispatch with a hard input-size boundary."""

from __future__ import annotations

from psr_mcp.parsers.html import parse_html
from psr_mcp.parsers.json_document import parse_json
from psr_mcp.parsers.models import (
    DocumentKind,
    ParsedDocument,
    ParseError,
    ParseErrorCode,
    ParserLimits,
)
from psr_mcp.parsers.pdf import parse_pdf
from psr_mcp.parsers.sniff import sniff_document
from psr_mcp.parsers.text import decode_document, parse_text


class DocumentParser:
    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()

    def parse(self, body: bytes, *, content_type: str | None) -> ParsedDocument:
        if len(body) > self._limits.max_input_bytes:
            raise ParseError(
                ParseErrorCode.INPUT_TOO_LARGE,
                "document exceeds the parser input limit",
            )
        sniff = sniff_document(body, content_type)
        if sniff.kind is DocumentKind.HTML:
            return parse_html(
                body,
                content_type=content_type,
                sniff=sniff,
                limits=self._limits,
            )
        if sniff.kind is DocumentKind.JSON:
            return parse_json(
                body,
                content_type=content_type,
                sniff=sniff,
                limits=self._limits,
            )
        if sniff.kind is DocumentKind.PDF:
            return parse_pdf(
                body,
                sniff=sniff,
                limits=self._limits,
            )
        if sniff.kind is DocumentKind.TEXT:
            text, warnings = decode_document(body, content_type)
            return parse_text(
                text,
                sniff=sniff,
                limits=self._limits,
                warnings=warnings,
            )
        raise ParseError(
            ParseErrorCode.UNSUPPORTED_KIND,
            f"{sniff.kind.value} parser is not available",
        )
