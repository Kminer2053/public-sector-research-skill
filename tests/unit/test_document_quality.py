from __future__ import annotations

import pytest

from psr_mcp.evidence import (
    DocumentQualityAssessor,
    DocumentQualityStatus,
)
from psr_mcp.parsers import (
    DocumentKind,
    ParsedDocument,
    Passage,
    SniffResult,
)


def _document(text: str, *, title: str | None = None) -> ParsedDocument:
    return ParsedDocument(
        kind=DocumentKind.HTML,
        title=title,
        passages=(
            Passage(
                id="p-0001",
                text=text,
                locator="html:p[1]",
            ),
        ),
        warnings=(),
        sniff=SniffResult(
            kind=DocumentKind.HTML,
            declared_media_type="text/html",
            detected_media_type="text/html",
            declared_mismatch=False,
        ),
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "이 자료를 열람하려면 로그인이 필요합니다. 로그인 후 이용해 주세요.",
            DocumentQualityStatus.LOGIN_REQUIRED,
        ),
        (
            "Access denied. Verify you are human using the captcha challenge.",
            DocumentQualityStatus.ACCESS_RESTRICTED,
        ),
        (
            "404 Not Found. 요청하신 페이지가 없습니다.",
            DocumentQualityStatus.ERROR_PAGE,
        ),
        ("짧음", DocumentQualityStatus.TOO_LITTLE_TEXT),
        (
            "공공기관 AI 구매 시 데이터 반환과 기록 이전 조건을 계약서에 명시한다.",
            DocumentQualityStatus.USABLE,
        ),
    ],
)
def test_document_quality_classifies_non_evidence_pages(
    text: str,
    expected: DocumentQualityStatus,
) -> None:
    quality = DocumentQualityAssessor().assess(_document(text))

    assert quality.status is expected
    assert quality.usable is (expected is DocumentQualityStatus.USABLE)
    assert quality.explanation


def test_document_quality_uses_title_and_bounded_inspection() -> None:
    quality = DocumentQualityAssessor(inspection_char_limit=1_000).assess(
        _document("A" * 2_000, title="Service Unavailable")
    )

    assert quality.status is DocumentQualityStatus.ERROR_PAGE


def test_document_quality_rejects_law_shell_without_article_body() -> None:
    shell = _document("본문목록열림 본문 제정·개정이유 원문다운로드 조문 선택 화면내검색")
    rejected = DocumentQualityAssessor().assess(
        shell,
        source_url="https://www.law.go.kr/LSW/lsInfoP.do?lsId=014820",
    )
    article = DocumentQualityAssessor().assess(
        _document("본문목록열림 원문다운로드 제34조(고영향 인공지능과 관련한 사업자의 책무)"),
        source_url="https://www.law.go.kr/LSW/lsInfoP.do?lsId=014820",
    )
    common_info = DocumentQualityAssessor().assess(
        shell,
        source_url="https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1",
    )

    assert rejected.status is DocumentQualityStatus.DYNAMIC_CONTENT_MISSING
    assert article.status is DocumentQualityStatus.USABLE
    assert common_info.status is DocumentQualityStatus.USABLE


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"minimum_text_chars": 0}, "minimum_text_chars"),
        ({"inspection_char_limit": 999}, "inspection_char_limit"),
    ],
)
def test_document_quality_configuration_fails_closed(
    kwargs: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        DocumentQualityAssessor(**kwargs)
