"""Bounded stdlib HTML extraction with stable structural locators."""

from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser

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


def parse_html(
    body: bytes,
    *,
    content_type: str | None,
    sniff: SniffResult,
    limits: ParserLimits,
) -> ParsedDocument:
    text, decode_warnings = decode_document(body, content_type)
    extractor = _HtmlExtractor(limits)
    try:
        extractor.feed(text)
        extractor.close()
    except _HtmlLimitExceeded as error:
        raise ParseError(
            ParseErrorCode.RESOURCE_LIMIT,
            str(error),
        ) from None
    if not extractor.passages:
        raise ParseError(
            ParseErrorCode.DOCUMENT_EMPTY,
            "HTML document did not contain usable passages",
        )
    warnings = list(decode_warnings)
    if sniff.declared_mismatch:
        warnings.append("DECLARED_TYPE_MISMATCH")
    return ParsedDocument(
        kind=DocumentKind.HTML,
        title=extractor.title,
        passages=tuple(extractor.passages),
        warnings=tuple(warnings),
        sniff=sniff,
    )


class _HtmlExtractor(HTMLParser):
    def __init__(self, limits: ParserLimits) -> None:
        super().__init__(convert_charrefs=True)
        self._limits = limits
        self._node_count = 0
        self._total_chars = 0
        self._ignored_depth = 0
        self._title_depth = 0
        self._title_parts: list[str] = []
        self._block_tag: str | None = None
        self._block_parts: list[str] = []
        self._block_heading: str | None = None
        self._current_heading: str | None = None
        self._tag_counts: defaultdict[str, int] = defaultdict(int)
        self.title: str | None = None
        self.passages: list[Passage] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        self._touch_node()
        normalized = tag.casefold()
        if normalized in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if normalized == "title":
            self._title_depth += 1
            return
        if normalized in _BLOCK_TAGS and self._block_tag is None:
            self._block_tag = normalized
            self._block_parts = []
            self._block_heading = self._current_heading

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in _IGNORED_TAGS:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if normalized == "title" and self._title_depth:
            self._title_depth -= 1
            self.title = normalize_space(" ".join(self._title_parts)) or None
            return
        if normalized == self._block_tag:
            self._flush_block(normalized)

    def handle_data(self, data: str) -> None:
        self._touch_node()
        if self._ignored_depth:
            return
        if self._title_depth:
            self._title_parts.append(data)
        if self._block_tag is not None:
            self._block_parts.append(data)

    def _touch_node(self) -> None:
        self._node_count += 1
        if self._node_count > self._limits.max_nodes:
            raise _HtmlLimitExceeded("HTML document exceeds the parser node limit")

    def _flush_block(self, tag: str) -> None:
        text = normalize_space(" ".join(self._block_parts))
        heading = self._block_heading
        self._block_tag = None
        self._block_parts = []
        self._block_heading = None
        if not text:
            return
        self._tag_counts[tag] += 1
        if tag in _HEADING_TAGS:
            self._current_heading = text
            heading = text
        for chunk_index, chunk in enumerate(
            _chunks(text, self._limits.max_passage_chars),
            start=1,
        ):
            self._total_chars += len(chunk)
            if self._total_chars > self._limits.max_total_text_chars:
                raise _HtmlLimitExceeded("HTML text exceeds the parser character limit")
            if len(self.passages) >= self._limits.max_passages:
                raise _HtmlLimitExceeded("HTML document exceeds the parser passage limit")
            locator = f"html:{tag}[{self._tag_counts[tag]}]"
            if len(text) > self._limits.max_passage_chars:
                locator = f"{locator}:chunk-{chunk_index}"
            self.passages.append(
                Passage(
                    id=f"p-{len(self.passages) + 1:04d}",
                    text=chunk,
                    locator=locator,
                    heading=heading,
                )
            )


class _HtmlLimitExceeded(RuntimeError):
    pass


def _chunks(value: str, size: int) -> list[str]:
    return [value[index : index + size] for index in range(0, len(value), size)]


_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BLOCK_TAGS = _HEADING_TAGS | frozenset(
    {
        "p",
        "li",
        "dt",
        "dd",
        "blockquote",
        "pre",
        "td",
        "th",
    }
)
_IGNORED_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "svg",
        "canvas",
        "template",
    }
)
