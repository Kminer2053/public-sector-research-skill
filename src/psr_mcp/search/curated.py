"""Reviewed source seeds for a deliberately narrow no-key public preview."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from psr_mcp.search.models import (
    SearchFailure,
    SearchQuery,
    SearchResult,
    SourceCandidate,
    SourceTier,
)


@dataclass(frozen=True, slots=True)
class CuratedSourceSeed:
    track_id: str
    url: str
    title: str
    publisher: str
    source_tier: SourceTier
    published_at: date | None = None


class CuratedOfficialSourceProvider:
    """Return reviewed sources only for the public-sector AI procurement topic.

    This provider is a transparent discovery fallback, not a web search engine.
    Unsupported questions return a typed scope failure instead of unrelated sources.
    """

    async def search(self, query: SearchQuery) -> SearchResult:
        if (
            not query.research_question
            or len(query.research_question) > 4_000
            or query.max_results < 1
            or query.max_results > 20
        ):
            return SearchResult(
                candidates=(),
                failures=(
                    SearchFailure(
                        query_id=query.id,
                        code="QUERY_INVALID",
                        message="curated source query exceeded the configured limits",
                        retryable=False,
                    ),
                ),
            )
        if not _supports_public_ai_procurement(query.research_question):
            return SearchResult(
                candidates=(),
                failures=(
                    SearchFailure(
                        query_id=query.id,
                        code="CURATED_SCOPE_UNSUPPORTED",
                        message=(
                            "reviewed source seeds currently support only Korean "
                            "public-sector AI procurement questions"
                        ),
                        retryable=False,
                    ),
                ),
            )
        seeds = _SEEDS_BY_TRACK.get(query.track_id, ())
        candidates = tuple(_candidate(query, seed) for seed in seeds[: query.max_results])
        return SearchResult(candidates=candidates)


def _candidate(query: SearchQuery, seed: CuratedSourceSeed) -> SourceCandidate:
    digest = hashlib.sha256(f"{query.id}\0{seed.url}".encode()).hexdigest()[:16]
    return SourceCandidate(
        id=f"seed-{digest}",
        track_id=query.track_id,
        url=seed.url,
        title=seed.title,
        publisher=seed.publisher,
        source_tier=seed.source_tier,
        published_at=seed.published_at,
    )


def _supports_public_ai_procurement(question: str) -> bool:
    normalized = " ".join(question.casefold().split())
    has_ai = "인공지능" in normalized or re.search(r"\bai\b", normalized) is not None
    has_public_scope = any(term in normalized for term in _PUBLIC_SCOPE_TERMS)
    has_procurement_scope = any(term in normalized for term in _PROCUREMENT_SCOPE_TERMS)
    return has_ai and has_public_scope and has_procurement_scope


_PUBLIC_SCOPE_TERMS = (
    "공공기관",
    "공공부문",
    "공공 분야",
    "정부기관",
    "공공조달",
)
_PROCUREMENT_SCOPE_TERMS = (
    "구매",
    "조달",
    "도입",
    "계약",
    "업체 종속",
    "vendor lock",
    "데이터 권리",
    "학습 재사용",
)

_LAW_ARTICLE_34 = CuratedSourceSeed(
    track_id="law-regulation",
    url="https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1031809457",
    title="인공지능기본법 제34조 고영향 인공지능과 관련한 사업자의 책무",
    publisher="국가법령정보센터",
    source_tier=SourceTier.OFFICIAL_PRIMARY,
    published_at=date(2026, 1, 20),
)
_PIPC_PRESS = CuratedSourceSeed(
    track_id="government-policy",
    url=(
        "https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do"
        "?bbsId=BS074&mCode=C020010000&nttId=11410"
    ),
    title="생성형 인공지능 개발·활용 위한 개인정보 처리 기준 제시",
    publisher="개인정보보호위원회",
    source_tier=SourceTier.OFFICIAL_PRIMARY,
    published_at=date(2025, 8, 7),
)
_PIPC_GUIDE = CuratedSourceSeed(
    track_id="privacy",
    url=(
        "https://www.pipc.go.kr/np/cmm/fms/FileDown.do"
        "?atchFileId=FILE_000000000559959&fileSn=3&fileExtsn=pdf&cnvCnt="
    ),
    title="생성형 인공지능 개발·활용을 위한 개인정보 처리 안내서",
    publisher="개인정보보호위원회",
    source_tier=SourceTier.OFFICIAL_PRIMARY,
    published_at=date(2025, 8, 7),
)
_NIST_AI_RMF = CuratedSourceSeed(
    track_id="international-standards",
    url="https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=936225",
    title="Artificial Intelligence Risk Management Framework (AI RMF 1.0)",
    publisher="NIST",
    source_tier=SourceTier.OFFICIAL_PRIMARY,
    published_at=date(2023, 1, 26),
)
_WEF_PROCUREMENT = CuratedSourceSeed(
    track_id="procurement",
    url="https://www.nist.gov/system/files/documents/2021/08/23/ai-rmf-rfi-0039-1.pdf",
    title="AI Procurement in a Box: AI Government Procurement Guidelines",
    publisher="World Economic Forum (NIST-hosted copy)",
    source_tier=SourceTier.OFFICIAL_SECONDARY,
    published_at=date(2020, 6, 1),
)

_SEEDS_BY_TRACK: dict[str, tuple[CuratedSourceSeed, ...]] = {
    "law-regulation": (_LAW_ARTICLE_34,),
    "government-policy": (_PIPC_PRESS,),
    "procurement": (_WEF_PROCUREMENT,),
    "privacy": (_PIPC_GUIDE,),
    "international-standards": (_NIST_AI_RMF,),
    "vendor-lock-in": (
        CuratedSourceSeed(
            track_id="vendor-lock-in",
            url=_WEF_PROCUREMENT.url,
            title=_WEF_PROCUREMENT.title,
            publisher=_WEF_PROCUREMENT.publisher,
            source_tier=_WEF_PROCUREMENT.source_tier,
            published_at=_WEF_PROCUREMENT.published_at,
        ),
    ),
    "data-rights": (
        CuratedSourceSeed(
            track_id="data-rights",
            url=_PIPC_GUIDE.url,
            title=_PIPC_GUIDE.title,
            publisher=_PIPC_GUIDE.publisher,
            source_tier=_PIPC_GUIDE.source_tier,
            published_at=_PIPC_GUIDE.published_at,
        ),
    ),
}
