from __future__ import annotations

from datetime import date

import pytest

from psr_mcp.planner import GovernmentPlanner
from psr_mcp.planner.government import _deduplicate
from psr_mcp.planner.models import ResearchPlan


def _plan(question: str) -> ResearchPlan:
    return GovernmentPlanner().plan(
        question=question,
        as_of_date=date(2026, 7, 16),
        jurisdiction="KR",
        max_sources=12,
        max_bytes=31_457_280,
        timeout_seconds=20,
    )


def test_ai_procurement_question_has_required_government_tracks() -> None:
    plan = _plan(
        "공공기관 AI 구매 원칙에 데이터 권리, 학습 재사용, 업체 종속과 반환 조건을 포함해줘"
    )
    track_ids = [track.id for track in plan.tracks]

    assert track_ids[:5] == [
        "law-regulation",
        "government-policy",
        "procurement",
        "privacy",
        "international-standards",
    ]
    assert "vendor-lock-in" in track_ids
    assert "data-rights" in track_ids
    assert plan.stop_conditions.max_sources == 12
    assert plan.stop_conditions.require_official_primary is True
    assert all(track.source_tiers for track in plan.tracks)
    data_rights = next(track for track in plan.tracks if track.id == "data-rights")
    assert "data ownership" in data_rights.selection_terms
    assert "학습 재사용" in data_rights.selection_terms


def test_planner_is_deterministic_and_deduplicates_keyword_tracks() -> None:
    question = "공공 조달 구매 데이터 권리와 데이터 반환 및 업체 종속을 조사해줘"
    first = _plan(question)
    second = _plan(question)

    assert first == second
    ids = [track.id for track in first.tracks]
    assert len(ids) == len(set(ids))
    assert _deduplicate([first.tracks[0], first.tracks[0]]) == [first.tracks[0]]


@pytest.mark.parametrize(
    "question, jurisdiction, message",
    [
        ("짧은질문", "KR", "10..4000"),
        ("공공기관 정책을 조사할 수 있을 만큼 충분히 긴 질문입니다.", "US", "KR only"),
    ],
)
def test_planner_rejects_unbounded_or_unsupported_scope(
    question: str,
    jurisdiction: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        GovernmentPlanner().plan(
            question=question,
            as_of_date=date(2026, 7, 16),
            jurisdiction=jurisdiction,
            max_sources=12,
            max_bytes=31_457_280,
            timeout_seconds=20,
        )
