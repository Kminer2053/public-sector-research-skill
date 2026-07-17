from __future__ import annotations

import json

import pytest
from psr_core.parsers import DocumentParseError, extracted_markdown, parse_document


def test_html_extracts_title_heading_and_passages() -> None:
    body = """
    <html><head><title>공식 가이드</title><style>hidden</style></head>
    <body><h1>개인정보</h1><p>보유기간과 파기 절차를 정한다.</p>
    <script>ignore me</script><li>학습 재사용 여부를 확인한다.</li></body></html>
    """.encode()

    document = parse_document(body, "text/html; charset=utf-8")

    assert document.kind == "HTML"
    assert document.title == "공식 가이드"
    assert [passage.heading for passage in document.passages] == [
        "개인정보",
        "개인정보",
    ]
    assert "ignore me" not in extracted_markdown(document)
    assert document.passages[0].locator == "html:block:1"


def test_html_ignores_navigation_forms_and_footer_furniture() -> None:
    body = """
    <html><body>
      <header><p>로그인 전체메뉴</p></header>
      <nav><ul><li>정책</li><li>법령</li></ul></nav>
      <main><h1>공식 지침</h1><p>공공기관은 위험관리 기준과 의무를 검토한다.</p></main>
      <form><button>검색</button></form>
      <footer><p>개인정보처리방침 관련사이트</p></footer>
    </body></html>
    """.encode()

    document = parse_document(body, "text/html")
    extracted = extracted_markdown(document)

    assert "공공기관은 위험관리 기준과 의무를 검토한다." in extracted
    assert "로그인" not in extracted
    assert "관련사이트" not in extracted
    assert "검색" not in extracted


def test_json_uses_json_pointer_locators() -> None:
    body = json.dumps(
        {"title": "정책", "requirements": [{"name": "데이터 삭제"}]},
        ensure_ascii=False,
    ).encode()

    document = parse_document(body, "application/json")

    assert document.kind == "JSON"
    assert document.title == "정책"
    assert any(passage.locator == "/requirements/0/name" for passage in document.passages)


def test_text_decodes_cp949_fallback() -> None:
    body = "공공기관 개인정보 보유기간\n\n파기 절차".encode("cp949")

    document = parse_document(body, "text/plain")

    assert document.kind == "TEXT"
    assert len(document.passages) == 2
    assert any("fallback encoding" in warning for warning in document.warnings)


def test_long_text_is_split_with_stable_locators() -> None:
    body = ("위험관리 " * 1_200).encode()

    document = parse_document(body, "text/plain")

    assert len(document.passages) >= 2
    assert document.passages[0].locator.startswith("text:block:1:part:")
    assert all(len(passage.text) <= 4_000 for passage in document.passages)


def test_binary_document_is_rejected() -> None:
    with pytest.raises(DocumentParseError) as captured:
        parse_document(b"\x00\x01\x02\x03", "application/octet-stream")

    assert captured.value.code == "UNSUPPORTED_KIND"


def test_input_size_limit() -> None:
    with pytest.raises(DocumentParseError) as captured:
        parse_document(b"x" * (20 * 1024 * 1024 + 1), "text/plain")

    assert captured.value.code == "INPUT_TOO_LARGE"


def test_blank_document_is_rejected() -> None:
    with pytest.raises(DocumentParseError) as captured:
        parse_document(b"   ", "text/plain")

    assert captured.value.code == "DOCUMENT_EMPTY"


def test_blank_pdf_requires_ocr_or_text() -> None:
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    from io import BytesIO

    buffer = BytesIO()
    writer.write(buffer)

    with pytest.raises(DocumentParseError) as captured:
        parse_document(buffer.getvalue(), "application/pdf")

    assert captured.value.code == "OCR_REQUIRED"
