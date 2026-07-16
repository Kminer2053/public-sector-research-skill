from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import HttpUrl

from psr_mcp.public.review import evaluate_structural_review, render_human_review_packet
from psr_mcp.public.schemas import (
    AppliedScope,
    Citation,
    EvidenceScoreOutput,
    Finding,
    QuickResearchOutput,
    RetentionStatus,
    ScoreComponentOutput,
)


def _score() -> EvidenceScoreOutput:
    component = ScoreComponentOutput(value=0.9, explanation="공식 원문")
    return EvidenceScoreOutput(
        overall=0.9,
        authority=component,
        primary_source=component,
        direct_relevance=component,
        original_snapshot=component,
        specificity=component,
        freshness=component,
        independence=component,
    )


def _citation(
    *,
    citation_id: str,
    track_id: str,
    document_sha256: str,
    source_tier: str = "OFFICIAL_PRIMARY",
    locator: str = "제1조",
) -> Citation:
    return Citation(
        id=citation_id,
        track_id=track_id,
        title="공식 문서",
        publisher="공식 기관",
        url=HttpUrl(f"https://example.go.kr/{citation_id}"),
        retrieved_at=datetime(2026, 7, 16, tzinfo=UTC),
        locator=locator,
        excerpt="검토에 필요한 공식 원문 구간",
        source_tier=source_tier,
        document_sha256=document_sha256,
        score=_score(),
    )


def _output() -> QuickResearchOutput:
    citations = [
        _citation(
            citation_id="cit-law",
            track_id="law-regulation",
            document_sha256="a" * 64,
        ),
        _citation(
            citation_id="cit-privacy",
            track_id="privacy",
            document_sha256="b" * 64,
        ),
        _citation(
            citation_id="cit-privacy-shared",
            track_id="data-rights",
            document_sha256="b" * 64,
        ),
        _citation(
            citation_id="cit-secondary",
            track_id="procurement",
            document_sha256="c" * 64,
        ),
        _citation(
            citation_id="cit-secondary-context",
            track_id="procurement",
            document_sha256="d" * 64,
            source_tier="OFFICIAL_SECONDARY",
        ),
    ]
    return QuickResearchOutput(
        operation_id="operation-secret",
        status="PARTIAL",
        summary="공식 근거를 검토했습니다.",
        scope=AppliedScope(
            as_of_date=date(2026, 7, 16),
            jurisdiction="KR",
            profile="government-v0",
            source_discovery="curated_seed",
            source_tracks=[
                "law-regulation",
                "privacy",
                "data-rights",
                "procurement",
            ],
            completion_criteria=["필수 track citation"],
            stop_conditions={"max_sources": 12},
        ),
        findings=[
            Finding(
                claim="법령상 감독 근거가 있습니다.",
                kind="FACT",
                citation_ids=["cit-law"],
                confidence="HIGH",
            ),
            Finding(
                claim="데이터 조건을 계약에 명시하는 방안을 검토합니다.",
                kind="RECOMMENDATION",
                citation_ids=["cit-privacy", "cit-secondary"],
                confidence="MEDIUM",
            ),
        ],
        citations=citations,
        gaps=["실시간 검색이 아닌 curated 범위"],
        conflicts=[],
        failures=[],
        markdown="# 조사 결과\n\n근거가 연결된 검토 결과입니다.",
        feedback_token="feedback-token-must-not-appear",
        feedback_expires_at=datetime(2026, 7, 17, tzinfo=UTC),
        retention=RetentionStatus(
            purge_state="PURGED",
            purged_at=datetime(2026, 7, 16, tzinfo=UTC),
        ),
    )


def test_structural_review_counts_unique_documents_and_passes_thresholds() -> None:
    review = evaluate_structural_review(_output())

    assert review.passed is True
    assert review.fact_citation_coverage == 1.0
    assert review.recommendation_citation_coverage == 1.0
    assert review.locator_completeness == 1.0
    assert review.official_primary_document_ratio == 3 / 4
    assert review.required_track_recall == 1.0
    assert review.citation_count == 5
    assert review.unique_document_count == 4


def test_structural_review_flags_missing_support_locator_primary_source_and_track() -> None:
    output = _output()
    degraded = output.model_copy(
        update={
            "scope": output.scope.model_copy(
                update={
                    "source_tracks": [
                        *output.scope.source_tracks,
                        "international-standards",
                    ]
                }
            ),
            "findings": [
                Finding(
                    claim="근거가 없는 사실",
                    kind="FACT",
                    citation_ids=["missing-citation"],
                    confidence="LOW",
                ),
                Finding(
                    claim="근거가 없는 권고",
                    kind="RECOMMENDATION",
                    citation_ids=[],
                    confidence="LOW",
                ),
            ],
            "citations": [
                _citation(
                    citation_id="cit-only",
                    track_id="law-regulation",
                    document_sha256="d" * 64,
                    source_tier="OFFICIAL_SECONDARY",
                    locator="",
                )
            ],
        }
    )

    review = evaluate_structural_review(degraded)

    assert review.passed is False
    assert len(review.issues) == 5
    assert review.fact_citation_coverage == 0.0
    assert review.recommendation_citation_coverage == 0.0
    assert review.locator_completeness == 0.0
    assert review.official_primary_document_ratio == 0.0
    assert review.required_track_recall == 0.2


def test_structural_review_treats_no_recommendations_as_vacuously_cited() -> None:
    output = _output()
    fact = next(finding for finding in output.findings if finding.kind == "FACT")
    empty = output.model_copy(
        update={
            "scope": output.scope.model_copy(update={"source_tracks": []}),
            "findings": [fact],
            "citations": [],
        }
    )

    review = evaluate_structural_review(empty)

    assert review.recommendation_count == 0
    assert review.recommendation_citation_coverage == 1.0
    assert review.fact_citation_coverage == 0.0
    assert review.locator_completeness == 0.0
    assert review.official_primary_document_ratio == 0.0
    assert review.required_track_recall == 0.0


def test_review_packet_contains_human_rubric_but_not_capability_token() -> None:
    packet = render_human_review_packet(
        question="<script>공공기관 AI 구매 원칙</script>",
        output=_output(),
    )

    assert "# Public Research Human Review Packet" in packet
    assert "&lt;script&gt;공공기관 AI 구매 원칙&lt;/script&gt;" in packet
    assert "unsupported legal conclusion 0건" in packet
    assert "업무 적합성" in packet
    assert "feedback-token-must-not-appear" not in packet
    assert "operation-secret" not in packet
