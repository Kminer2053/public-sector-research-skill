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
