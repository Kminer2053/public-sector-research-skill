"""Conservative exclusion of login, access-denied, and error documents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from psr_mcp.parsers.models import ParsedDocument


class DocumentQualityStatus(StrEnum):
    USABLE = "USABLE"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    ACCESS_RESTRICTED = "ACCESS_RESTRICTED"
    ERROR_PAGE = "ERROR_PAGE"
    TOO_LITTLE_TEXT = "TOO_LITTLE_TEXT"


@dataclass(frozen=True, slots=True)
class DocumentQuality:
    status: DocumentQualityStatus
    explanation: str

    @property
    def usable(self) -> bool:
        return self.status is DocumentQualityStatus.USABLE


class DocumentQualityAssessor:
    def __init__(
        self,
        *,
        minimum_text_chars: int = 20,
        inspection_char_limit: int = 20_000,
    ) -> None:
        if minimum_text_chars < 1 or minimum_text_chars > 1_000:
            raise ValueError("minimum_text_chars must be 1..1000")
        if inspection_char_limit < 1_000 or inspection_char_limit > 100_000:
            raise ValueError("inspection_char_limit must be 1000..100000")
        self._minimum_text_chars = minimum_text_chars
        self._inspection_char_limit = inspection_char_limit

    def assess(self, document: ParsedDocument) -> DocumentQuality:
        text = _document_text(document, self._inspection_char_limit)
        if len(text) < self._minimum_text_chars:
            return DocumentQuality(
                DocumentQualityStatus.TOO_LITTLE_TEXT,
                "document did not contain enough reviewable text",
            )
        normalized = text.casefold()
        if _contains_any(normalized, _ACCESS_PATTERNS):
            return DocumentQuality(
                DocumentQualityStatus.ACCESS_RESTRICTED,
                "document appears to be an access restriction or bot challenge",
            )
        if _contains_any(normalized, _LOGIN_PATTERNS):
            return DocumentQuality(
                DocumentQualityStatus.LOGIN_REQUIRED,
                "document appears to require an authenticated session",
            )
        if _contains_any(normalized, _ERROR_PATTERNS):
            return DocumentQuality(
                DocumentQualityStatus.ERROR_PAGE,
                "document appears to be an error page",
            )
        return DocumentQuality(
            DocumentQualityStatus.USABLE,
            "document contains reviewable extracted text",
        )


def _document_text(document: ParsedDocument, limit: int) -> str:
    parts = [document.title or ""]
    size = len(parts[0])
    for passage in document.passages:
        heading = passage.heading or ""
        parts.append(heading)
        parts.append(passage.text)
        size += len(heading) + len(passage.text)
        if size >= limit:
            break
    return " ".join(parts)[:limit]


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


_LOGIN_PATTERNS = (
    "로그인이 필요",
    "로그인 후 이용",
    "회원 로그인",
    "please sign in",
    "sign in to continue",
    "authentication required",
)
_ACCESS_PATTERNS = (
    "접근이 거부",
    "접근 권한이 없",
    "권한이 없습니다",
    "access denied",
    "request forbidden",
    "bot verification",
    "verify you are human",
    "captcha",
    "보안문자",
)
_ERROR_PATTERNS = (
    "페이지를 찾을 수 없",
    "요청하신 페이지가 없",
    "오류가 발생",
    "서비스를 사용할 수 없",
    "404 not found",
    "service unavailable",
    "internal server error",
)
