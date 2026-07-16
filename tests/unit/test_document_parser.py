from __future__ import annotations

import json
import subprocess
from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfWriter

from psr_mcp.parsers import (
    DocumentKind,
    DocumentParser,
    ParseError,
    ParseErrorCode,
    ParserLimits,
    sniff_document,
)
from psr_mcp.parsers.json_document import _JsonPassageBuilder
from psr_mcp.parsers.pdf import _error_code, _pages, _payload, parse_pdf
from psr_mcp.parsers.pdf_core import (
    PdfCoreError,
    _decrypt_empty_password,
    _reader_title,
    _title,
    extract_pdf,
)
from psr_mcp.parsers.sniff import _looks_binary


def test_sniff_uses_magic_bytes_and_reports_declared_mismatch() -> None:
    pdf = sniff_document(b"%PDF-1.7\nfixture", "application/octet-stream")
    assert pdf.kind is DocumentKind.PDF
    assert pdf.detected_media_type == "application/pdf"
    assert pdf.declared_mismatch is False

    html = sniff_document(
        b"<!doctype html><html><body>policy</body></html>",
        "application/pdf",
    )
    assert html.kind is DocumentKind.HTML
    assert html.declared_mismatch is True

    binary = sniff_document(b"PK\x03\x04\x00binary", None)
    assert binary.kind is DocumentKind.BINARY


def test_html_parser_extracts_inert_passages_and_ignores_active_content() -> None:
    body = b"""
    <!doctype html>
    <html>
      <head><title>Public AI Policy</title><style>.hidden{}</style></head>
      <body>
        <h1>Principles</h1>
        <p>Official &amp; reviewable evidence.</p>
        <script>ignore('system prompt override')</script>
        <h2>Data rights</h2>
        <ul><li>Return records at contract end.</li></ul>
      </body>
    </html>
    """

    result = DocumentParser().parse(body, content_type="text/html; charset=utf-8")

    assert result.kind is DocumentKind.HTML
    assert result.title == "Public AI Policy"
    assert [passage.text for passage in result.passages] == [
        "Principles",
        "Official & reviewable evidence.",
        "Data rights",
        "Return records at contract end.",
    ]
    assert result.passages[1].locator == "html:p[1]"
    assert result.passages[1].heading == "Principles"
    assert all("system prompt" not in passage.text for passage in result.passages)


def test_html_parser_reports_mismatch_chunks_and_ignored_nested_content() -> None:
    result = DocumentParser(ParserLimits(max_passage_chars=32)).parse(
        b"<html><body><template><p>ignored</p></template><p>"
        + (b"A" * 40)
        + b"</p><br/></body></html>",
        content_type="application/pdf",
    )

    assert result.warnings == ("DECLARED_TYPE_MISMATCH",)
    assert [passage.locator for passage in result.passages] == [
        "html:p[1]:chunk-1",
        "html:p[1]:chunk-2",
    ]


@pytest.mark.parametrize(
    "body, limits",
    [
        (
            b"<html><body><template><p>ignored</p></template><p/></body></html>",
            ParserLimits(),
        ),
        (
            b"<html><body><p>" + (b"A" * 40) + b"</p></body></html>",
            ParserLimits(max_passage_chars=32, max_total_text_chars=32),
        ),
        (
            b"<html><body><p>one</p><p>two</p></body></html>",
            ParserLimits(max_passages=1),
        ),
    ],
)
def test_html_empty_and_resource_boundaries(
    body: bytes,
    limits: ParserLimits,
) -> None:
    with pytest.raises(ParseError) as error:
        DocumentParser(limits).parse(body, content_type="text/html")

    assert error.value.code in {ParseErrorCode.DOCUMENT_EMPTY, ParseErrorCode.RESOURCE_LIMIT}


def test_korean_cp949_html_is_decoded_with_structural_locator() -> None:
    body = "<html><body><h1>공공정책</h1><p>근거 문장</p></body></html>".encode("cp949")

    result = DocumentParser().parse(body, content_type="text/html; charset=cp949")

    assert result.title is None
    assert [passage.text for passage in result.passages] == ["공공정책", "근거 문장"]
    assert result.passages[1].heading == "공공정책"


def test_json_parser_emits_json_pointer_locators_and_chunks_long_values() -> None:
    body = json.dumps(
        {
            "title": "AI procurement",
            "data/rights": {
                "return~rule": "A" * 70,
                "required": True,
                "count": 2,
                "missing": None,
            },
        }
    ).encode()
    limits = ParserLimits(max_passage_chars=32)

    result = DocumentParser(limits).parse(body, content_type="application/json")

    assert result.kind is DocumentKind.JSON
    assert result.title == "AI procurement"
    locators = [passage.locator for passage in result.passages]
    assert "json-pointer:/data~1rights/return~0rule:chunk-1" in locators
    assert "json-pointer:/data~1rights/required" in locators
    assert "json-pointer:/data~1rights/missing" in locators


def test_json_root_list_and_declared_mismatch_are_supported() -> None:
    result = DocumentParser().parse(
        b'["first", false, 3]',
        content_type="text/html",
    )

    assert result.title is None
    assert result.warnings == ("DECLARED_TYPE_MISMATCH",)
    assert [passage.locator for passage in result.passages] == [
        "json-pointer:/0",
        "json-pointer:/1",
        "json-pointer:/2",
    ]


@pytest.mark.parametrize(
    "body, limits",
    [
        (b'{"empty":""}', ParserLimits()),
        (
            b'{"text":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}',
            ParserLimits(max_passage_chars=32, max_total_text_chars=32),
        ),
        (
            b'{"first":"one","second":"two"}',
            ParserLimits(max_passages=1),
        ),
    ],
)
def test_json_empty_and_text_resource_boundaries(
    body: bytes,
    limits: ParserLimits,
) -> None:
    with pytest.raises(ParseError) as error:
        DocumentParser(limits).parse(body, content_type="application/json")

    assert error.value.code in {ParseErrorCode.DOCUMENT_EMPTY, ParseErrorCode.RESOURCE_LIMIT}


def test_json_builder_ignores_non_json_scalar_defensively() -> None:
    builder = _JsonPassageBuilder(ParserLimits())

    builder.walk(object(), pointer="/unsupported", depth=0)

    assert builder.passages == []


def test_plain_text_parser_uses_line_ranges_and_chunks() -> None:
    result = DocumentParser(ParserLimits(max_passage_chars=32)).parse(
        b"First paragraph.\ncontinues.\n\nSecond paragraph.",
        content_type="text/plain",
    )

    assert result.kind is DocumentKind.TEXT
    assert [passage.locator for passage in result.passages] == [
        "lines:1-2",
        "lines:4-4",
    ]


def test_text_decode_replacement_and_resource_boundaries() -> None:
    replacement = DocumentParser().parse(
        b"\x81",
        content_type="text/plain; charset=unknown-codec",
    )
    assert replacement.warnings == ("DECODE_REPLACEMENT",)

    with pytest.raises(ParseError) as characters:
        DocumentParser(ParserLimits(max_passage_chars=32, max_total_text_chars=32)).parse(
            b"A" * 33,
            content_type="text/plain",
        )
    assert characters.value.code is ParseErrorCode.RESOURCE_LIMIT

    with pytest.raises(ParseError) as passages:
        DocumentParser(ParserLimits(max_passages=1)).parse(
            b"first\n\nsecond",
            content_type="text/plain",
        )
    assert passages.value.code is ParseErrorCode.RESOURCE_LIMIT


def test_empty_binary_sample_helper_is_not_binary() -> None:
    assert _looks_binary(b"") is False


def test_pdf_parser_extracts_page_locators_in_isolated_worker() -> None:
    result = DocumentParser(ParserLimits(max_passage_chars=32)).parse(
        _text_pdf(
            "Official AI procurement evidence for data rights and record return.",
            title="Public AI Guide",
        ),
        content_type="text/html",
    )

    assert result.kind is DocumentKind.PDF
    assert result.title == "Public AI Guide"
    assert result.warnings == ("DECLARED_TYPE_MISMATCH",)
    assert [passage.locator for passage in result.passages] == [
        "pdf:page:1:chunk-1",
        "pdf:page:1:chunk-2",
        "pdf:page:1:chunk-3",
    ]
    assert "Official AI procurement" in result.passages[0].text


@pytest.mark.parametrize(
    "fixture, limits, code",
    [
        ("blank", ParserLimits(), ParseErrorCode.OCR_REQUIRED),
        (
            "encrypted",
            ParserLimits(),
            ParseErrorCode.ENCRYPTED_DOCUMENT,
        ),
        (
            "two-pages",
            ParserLimits(max_pdf_pages=1),
            ParseErrorCode.RESOURCE_LIMIT,
        ),
        ("empty", ParserLimits(), ParseErrorCode.DOCUMENT_EMPTY),
        ("malformed", ParserLimits(), ParseErrorCode.INVALID_DOCUMENT),
    ],
)
def test_pdf_worker_returns_typed_failures(
    fixture: str,
    limits: ParserLimits,
    code: ParseErrorCode,
) -> None:
    bodies = {
        "blank": _writer_pdf(page_count=1),
        "encrypted": _writer_pdf(page_count=1, password="secret"),
        "two-pages": _writer_pdf(page_count=2),
        "empty": _writer_pdf(page_count=0),
        "malformed": b"%PDF-not-valid",
    }
    with pytest.raises(ParseError) as error:
        DocumentParser(limits).parse(
            bodies[fixture],
            content_type="application/pdf",
        )

    assert error.value.code is code


def test_pdf_core_character_limit_and_metadata() -> None:
    with pytest.raises(PdfCoreError) as error:
        extract_pdf(
            _text_pdf("A" * 40, title="  Test   title  "),
            max_pages=1,
            max_total_text_chars=32,
        )
    assert error.value.code is ParseErrorCode.RESOURCE_LIMIT

    extracted = extract_pdf(
        _text_pdf("short text", title="  Test   title  "),
        max_pages=1,
        max_total_text_chars=32,
    )
    assert extracted.title == "Test title"
    assert extracted.pages[0].page_number == 1


@pytest.mark.parametrize(
    "fixture, max_pages, code",
    [
        ("encrypted", 2, ParseErrorCode.ENCRYPTED_DOCUMENT),
        ("empty", 2, ParseErrorCode.DOCUMENT_EMPTY),
        ("two-pages", 1, ParseErrorCode.RESOURCE_LIMIT),
        ("blank", 2, ParseErrorCode.OCR_REQUIRED),
        ("malformed", 2, ParseErrorCode.INVALID_DOCUMENT),
    ],
)
def test_pdf_core_failures_are_typed(
    fixture: str,
    max_pages: int,
    code: ParseErrorCode,
) -> None:
    bodies = {
        "encrypted": _writer_pdf(page_count=1, password="secret"),
        "empty": _writer_pdf(page_count=0),
        "two-pages": _writer_pdf(page_count=2),
        "blank": _writer_pdf(page_count=1),
        "malformed": b"%PDF-not-valid",
    }
    with pytest.raises(PdfCoreError) as error:
        extract_pdf(
            bodies[fixture],
            max_pages=max_pages,
            max_total_text_chars=1_000,
        )

    assert error.value.code is code


def test_pdf_core_handles_page_metadata_and_decrypt_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from psr_mcp.parsers import pdf_core

    class BadPage:
        def extract_text(self) -> str:
            raise RuntimeError("bad page")

    class Reader:
        def __init__(self) -> None:
            self.is_encrypted = False
            self.pages: list[object] = [BadPage()]

        @property
        def metadata(self) -> object:
            raise RuntimeError("bad metadata")

    monkeypatch.setattr(pdf_core, "PdfReader", lambda *args, **kwargs: Reader())
    with pytest.raises(PdfCoreError) as page_error:
        extract_pdf(
            b"%PDF-fixture",
            max_pages=2,
            max_total_text_chars=1_000,
        )
    assert page_error.value.code is ParseErrorCode.INVALID_DOCUMENT

    class TextPage:
        def extract_text(self) -> str:
            return "text"

    class MetadataReader(Reader):
        def __init__(self) -> None:
            super().__init__()
            self.pages = [TextPage()]

    metadata_reader = MetadataReader()
    assert _reader_title(metadata_reader) is None  # type: ignore[arg-type]

    class BadDecrypt:
        def decrypt(self, password: str) -> int:
            del password
            raise RuntimeError("bad decrypt")

    assert _decrypt_empty_password(BadDecrypt()) is False  # type: ignore[arg-type]
    assert _title(None) is None


def test_pdf_parent_rejects_worker_timeout_exit_and_malformed_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sniff = sniff_document(b"%PDF-1.7", "application/pdf")

    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        raise subprocess.TimeoutExpired(("worker",), 0.1)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ParseError) as timed_out:
        parse_pdf(b"%PDF-1.7", sniff=sniff, limits=ParserLimits())
    assert timed_out.value.code is ParseErrorCode.RESOURCE_LIMIT

    def result(
        returncode: int,
        stdout: bytes,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(("worker",), returncode, stdout)

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result(3, b""))
    with pytest.raises(ParseError) as exited:
        parse_pdf(b"%PDF-1.7", sniff=sniff, limits=ParserLimits())
    assert exited.value.code is ParseErrorCode.INVALID_DOCUMENT

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result(0, b"not-json"))
    with pytest.raises(ParseError) as malformed:
        parse_pdf(b"%PDF-1.7", sniff=sniff, limits=ParserLimits())
    assert malformed.value.code is ParseErrorCode.INVALID_DOCUMENT

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: result(0, b'{"status":"unexpected"}'),
    )
    with pytest.raises(ParseError) as invalid_status:
        parse_pdf(b"%PDF-1.7", sniff=sniff, limits=ParserLimits())
    assert invalid_status.value.code is ParseErrorCode.INVALID_DOCUMENT

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: result(
            0,
            b'{"status":"ok","title":null,"pages":[]}',
        ),
    )
    with pytest.raises(ParseError) as empty:
        parse_pdf(b"%PDF-1.7", sniff=sniff, limits=ParserLimits())
    assert empty.value.code is ParseErrorCode.DOCUMENT_EMPTY


def test_pdf_parent_payload_and_page_schema_fail_closed() -> None:
    with pytest.raises(ParseError) as oversized:
        _payload(b"x" * 8_388_609)
    assert oversized.value.code is ParseErrorCode.RESOURCE_LIMIT

    with pytest.raises(ParseError):
        _payload(b"[]")
    with pytest.raises(ParseError):
        _pages({}, ParserLimits())
    with pytest.raises(ParseError):
        _pages([None], ParserLimits())
    with pytest.raises(ParseError):
        _pages([{"page_number": True, "text": "value"}], ParserLimits())
    with pytest.raises(ParseError):
        _pages(
            [{"page_number": 1, "text": "A" * 33}],
            ParserLimits(max_passage_chars=32, max_total_text_chars=32),
        )
    assert _error_code("UNKNOWN") is ParseErrorCode.INVALID_DOCUMENT
    assert _error_code("OCR_REQUIRED") is ParseErrorCode.OCR_REQUIRED


@pytest.mark.parametrize(
    "body, content_type, limits, code",
    [
        (b"", "text/plain", ParserLimits(), ParseErrorCode.DOCUMENT_EMPTY),
        (
            b"x" * 33,
            "text/plain",
            ParserLimits(max_input_bytes=32),
            ParseErrorCode.INPUT_TOO_LARGE,
        ),
        (b"%PDF-1.7", "application/pdf", ParserLimits(), ParseErrorCode.INVALID_DOCUMENT),
        (
            b"PK\x03\x04\x00binary",
            "application/octet-stream",
            ParserLimits(),
            ParseErrorCode.UNSUPPORTED_KIND,
        ),
        (b"{bad json", "application/json", ParserLimits(), ParseErrorCode.INVALID_DOCUMENT),
        (
            b"<html><body><p>one</p><p>two</p></body></html>",
            "text/html",
            ParserLimits(max_nodes=2),
            ParseErrorCode.RESOURCE_LIMIT,
        ),
        (
            b'{"a":{"b":{"c":1}}}',
            "application/json",
            ParserLimits(max_json_depth=2),
            ParseErrorCode.RESOURCE_LIMIT,
        ),
        (
            b"[1,2,3]",
            "application/json",
            ParserLimits(max_json_items=2),
            ParseErrorCode.RESOURCE_LIMIT,
        ),
    ],
)
def test_parser_failures_are_typed(
    body: bytes,
    content_type: str,
    limits: ParserLimits,
    code: ParseErrorCode,
) -> None:
    with pytest.raises(ParseError) as error:
        DocumentParser(limits).parse(body, content_type=content_type)

    assert error.value.code is code


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_input_bytes": 0},
        {"max_nodes": 0},
        {"max_passages": 0},
        {"max_total_text_chars": 0},
        {"max_passage_chars": 31},
        {"max_json_depth": 0},
        {"max_json_items": 0},
        {"max_pdf_pages": 0},
        {"pdf_timeout_seconds": 0.09},
        {"pdf_worker_memory_bytes": 67_108_863},
    ],
)
def test_parser_limits_fail_closed(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ParserLimits(**kwargs)


def _writer_pdf(
    *,
    page_count: int,
    password: str | None = None,
) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    if password is not None:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _text_pdf(text: str, *, title: str | None = None) -> bytes:
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped_text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    info_reference = b""
    if title is not None:
        escaped_title = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        objects.append(f"<< /Title ({escaped_title}) >>".encode("ascii"))
        info_reference = b" /Info 6 0 R"
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{index} 0 obj\n".encode())
        document.extend(value)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode()
        + b" /Root 1 0 R"
        + info_reference
        + b" >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return bytes(document)
