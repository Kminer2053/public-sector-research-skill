from __future__ import annotations

from datetime import UTC, datetime

import pytest

from psr_mcp.evidence import CitationConstrainedWriter
from psr_mcp.evidence.models import (
    EvidenceCitation,
    EvidenceScore,
    ScoreComponent,
)
from psr_mcp.search import SourceTier


def _citation(
    *,
    citation_id: str,
    track_id: str,
    excerpt: str,
    score: float = 0.85,
    tier: SourceTier = SourceTier.OFFICIAL_PRIMARY,
) -> EvidenceCitation:
    component = ScoreComponent(value=score, explanation="fixture")
    return EvidenceCitation(
        id=citation_id,
        track_id=track_id,
        title=f"{track_id} 문서",
        publisher="공식기관",
        url=f"https://example.go.kr/{citation_id}",
        retrieved_at=datetime(2026, 7, 16, tzinfo=UTC),
        locator="p.1",
        excerpt=excerpt,
        source_tier=tier,
        document_sha256=citation_id[-1] * 64,
        score=EvidenceScore(
            overall=score,
            authority=component,
            primary_source=component,
            direct_relevance=component,
            original_snapshot=component,
            specificity=component,
            freshness=component,
            independence=component,
        ),
    )


def test_writer_emits_extractive_facts_and_anchor_backed_recommendations() -> None:
    procurement = _citation(
        citation_id="cit-a",
        track_id="procurement",
        excerpt=(
            "The contract should define data ownership, access to data and "
            "data deletion at the end of service."
        ),
    )
    oversight = _citation(
        citation_id="cit-b",
        track_id="law-regulation",
        excerpt="고영향 인공지능에는 사람의 관리ㆍ감독 조치를 이행하여야 한다.",
    )

    findings = CitationConstrainedWriter().write((procurement, oversight))

    recommendations = [finding for finding in findings if finding.kind == "RECOMMENDATION"]
    facts = [finding for finding in findings if finding.kind == "FACT"]
    assert len(recommendations) == 2
    assert len(facts) == 2
    assert recommendations[0].citation_ids
    assert set(recommendations[0].citation_ids).issubset({"cit-a", "cit-b"})
    assert all(finding.citation_ids for finding in findings)
    assert all("조달 원칙 검토안:" in finding.claim for finding in recommendations)


def test_writer_does_not_invent_control_when_required_anchor_is_missing() -> None:
    citation = _citation(
        citation_id="cit-c",
        track_id="procurement",
        excerpt="The contract describes data ownership and access to data.",
    )

    findings = CitationConstrainedWriter().write((citation,))

    assert [finding.kind for finding in findings] == ["FACT"]
    assert "data ownership" in findings[0].claim


def test_writer_matches_compact_korean_and_caps_extractive_fact() -> None:
    citation = _citation(
        citation_id="cit-d",
        track_id="privacy",
        excerpt="개인정보보유기간과파기절차를정한다." + ("부록" * 100),
        tier=SourceTier.OFFICIAL_SECONDARY,
        score=0.7,
    )

    findings = CitationConstrainedWriter(max_fact_chars=100).write((citation,))

    assert findings[0].kind == "RECOMMENDATION"
    assert findings[0].confidence == "MEDIUM"
    assert findings[-1].kind == "FACT"
    assert len(findings[-1].claim.split("관련 원문: ", maxsplit=1)[1]) == 100
    assert findings[-1].claim.endswith("…")


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"max_fact_chars": 99}, "max_fact_chars"),
        ({"max_supporting_citations": 0}, "max_supporting_citations"),
    ],
)
def test_writer_validates_limits(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        CitationConstrainedWriter(**kwargs)
