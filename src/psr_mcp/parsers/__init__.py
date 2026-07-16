"""Bounded parsers that turn untrusted documents into inert passages."""

from psr_mcp.parsers.dispatch import DocumentParser
from psr_mcp.parsers.models import (
    DocumentKind,
    ParsedDocument,
    ParseError,
    ParseErrorCode,
    ParserLimits,
    Passage,
    SniffResult,
)
from psr_mcp.parsers.sniff import sniff_document

__all__ = [
    "DocumentKind",
    "DocumentParser",
    "ParseError",
    "ParseErrorCode",
    "ParsedDocument",
    "ParserLimits",
    "Passage",
    "SniffResult",
    "sniff_document",
]
