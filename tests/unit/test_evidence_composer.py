from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from psr_mcp.collectors.models import CollectedDocument
from psr_mcp.evidence import EvidenceComposer, EvidenceDocument
from psr_mcp.parsers.models import (
    DocumentKind,
    ParsedDocument,
    Passage,
    SniffResult,
)
from psr_mcp.search.models import SourceCandidate, SourceTier


def _document(
    *,
    candidate_id: str,
    tier: SourceTier,
    text: str,
    locator: str,
    publisher: str,
    published_at: date | None = None,
) -> EvidenceDocument:
    candidate = SourceCandidate(
        id=candidate_id,
        track_id="data-rights",
        url=f"https://{candidate_id}.go.kr/source",
        title=f"{publisher} AI 조달 지침",
        publisher=publisher,
        source_tier=tier,
        published_at=published_at,
    )
    collected = CollectedDocument(
        requested_url=candidate.url,
        final_url=candidate.url,
        redirect_chain=(),
        status=200,
        headers={"content-type": "text/html"},
        content_type="text/html",
        body=text.encode(),
        sha256=(candidate_id * 64)[:64],
        retrieved_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    parsed = ParsedDocument(
        kind=DocumentKind.HTML,
        title=candidate.title,
        passages=(
            Passage(
                id="p-0001",
                text=text,
                locator=locator,
                heading="데이터 권리",
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
    return EvidenceDocument(candidate=candidate, collected=collected, parsed=parsed)


def test_composer_deduplicates_reprints_and_prefers_official_primary() -> None:
    text = "계약 종료 시 데이터와 기록을 이용기관에 반환해야 한다."
    official = _document(
        candidate_id="a",
        tier=SourceTier.OFFICIAL_PRIMARY,
        text=text,
        locator="제10조",
        publisher="조달청",
        published_at=date(2026, 1, 1),
    )
    secondary = _document(
        candidate_id="b",
        tier=SourceTier.REPUTABLE_MEDIA,
        text=text,
        locator="기사 본문",
        publisher="보조 언론",
    )

    pack = EvidenceComposer().compose(
        question="데이터 권리와 계약 종료 시 기록 반환 원칙",
        as_of_date=date(2026, 7, 16),
        documents=(secondary, official),
    )

    assert len(pack.citations) == 1
    assert pack.deduplicated_count == 1
    citation = pack.citations[0]
    assert citation.publisher == "조달청"
    assert citation.source_tier is SourceTier.OFFICIAL_PRIMARY
    assert citation.locator == "제10조"
    assert citation.score.primary_source.value == 1.0
    assert citation.score.direct_relevance.value > 0.2
    assert citation.score.freshness.explanation.endswith("일 경과")
    assert citation.id.startswith("cit-")


def test_composer_is_stable_caps_excerpt_and_explains_unknown_freshness() -> None:
    document = _document(
        candidate_id="c",
        tier=SourceTier.OFFICIAL_SECONDARY,
        text="데이터 권리 " + ("A" * 600),
        locator="p.12",
        publisher="공공기관",
    )
    composer = EvidenceComposer(max_excerpt_chars=100)

    first = composer.compose(
        question="데이터 권리",
        as_of_date=date(2026, 7, 16),
        documents=(document,),
    )
    second = composer.compose(
        question="데이터 권리",
        as_of_date=date(2026, 7, 16),
        documents=(document,),
    )

    assert first == second
    assert len(first.citations[0].excerpt) == 100
    assert first.citations[0].score.freshness.value == 0.5
    assert "미확인" in first.citations[0].score.freshness.explanation
    assert first.citations[0].score.original_snapshot.value == 1.0


def test_composer_returns_gap_without_documents_and_falls_back_to_first_passage() -> None:
    composer = EvidenceComposer()
    empty = composer.compose(
        question="관련 없는 질문",
        as_of_date=date(2026, 7, 16),
        documents=(),
    )
    assert empty.citations == ()
    assert empty.gaps

    document = _document(
        candidate_id="d",
        tier=SourceTier.COMMUNITY,
        text="완전히 다른 문장",
        locator="paragraph 1",
        publisher="커뮤니티",
    )
    fallback = composer.compose(
        question="데이터 권리",
        as_of_date=date(2026, 7, 16),
        documents=(document,),
    )
    assert len(fallback.citations) == 1
    assert fallback.citations[0].score.authority.value == 0.2


def test_composer_reserves_a_citation_for_each_represented_track() -> None:
    first = _document(
        candidate_id="e",
        tier=SourceTier.OFFICIAL_PRIMARY,
        text="데이터 권리 반환 규정",
        locator="제1조",
        publisher="기관 A",
    )
    second = _document(
        candidate_id="f",
        tier=SourceTier.OFFICIAL_PRIMARY,
        text="개인정보 보호 규정",
        locator="제2조",
        publisher="기관 B",
    )
    second = EvidenceDocument(
        candidate=SourceCandidate(
            id=second.candidate.id,
            track_id="privacy",
            url=second.candidate.url,
            title=second.candidate.title,
            publisher=second.candidate.publisher,
            source_tier=second.candidate.source_tier,
            published_at=second.candidate.published_at,
        ),
        collected=second.collected,
        parsed=ParsedDocument(
            kind=second.parsed.kind,
            title=second.parsed.title,
            passages=(
                Passage(
                    id="p-0001",
                    text="개인정보 보호 규정",
                    locator="제2조",
                ),
                Passage(
                    id="p-0002",
                    text="데이터 권리 추가 설명",
                    locator="제3조",
                ),
            ),
            warnings=second.parsed.warnings,
            sniff=second.parsed.sniff,
        ),
    )

    pack = EvidenceComposer(max_citations=2, max_per_document=2).compose(
        question="데이터 권리 개인정보 보호",
        as_of_date=date(2026, 7, 16),
        documents=(first, second),
    )

    assert {citation.track_id for citation in pack.citations} == {
        "data-rights",
        "privacy",
    }


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"max_citations": 0}, "max_citations"),
        ({"max_per_document": 0}, "max_per_document"),
        ({"max_excerpt_chars": 99}, "max_excerpt_chars"),
    ],
)
def test_composer_configuration_fails_closed(
    kwargs: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        EvidenceComposer(**kwargs)
