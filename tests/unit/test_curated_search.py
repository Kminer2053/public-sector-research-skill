from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from psr_mcp.planner import GovernmentPlanner
from psr_mcp.search import (
    CuratedOfficialSourceProvider,
    GovernmentQueryBuilder,
    SearchQuery,
    SourceTier,
)


def _queries(question: str) -> tuple[SearchQuery, ...]:
    plan = GovernmentPlanner().plan(
        question=question,
        as_of_date=date(2026, 7, 16),
        jurisdiction="KR",
        max_sources=12,
        max_bytes=31_457_280,
        timeout_seconds=20,
    )
    return GovernmentQueryBuilder(max_results_per_track=2).build(plan)


@pytest.mark.anyio
async def test_curated_provider_returns_reviewed_ai_procurement_sources_by_track() -> None:
    provider = CuratedOfficialSourceProvider()
    queries = _queries(
        "공공기관 AI 구매 원칙에 데이터 권리, 학습 재사용과 업체 종속 방지를 포함해줘"
    )

    results = {query.track_id: await provider.search(query) for query in queries}

    assert all(not result.failures for result in results.values())
    assert results["law-regulation"].candidates[0].url.startswith("https://www.law.go.kr/")
    assert results["privacy"].candidates[0].url == results["data-rights"].candidates[0].url
    assert results["procurement"].candidates[0].url == results["vendor-lock-in"].candidates[0].url
    assert (
        results["international-standards"].candidates[0].source_tier is SourceTier.OFFICIAL_PRIMARY
    )
    assert results["procurement"].candidates[0].source_tier is SourceTier.OFFICIAL_SECONDARY
    assert "World Economic Forum" in results["procurement"].candidates[0].publisher


@pytest.mark.anyio
async def test_curated_provider_rejects_questions_outside_reviewed_scope() -> None:
    provider = CuratedOfficialSourceProvider()
    query = _queries("공공기관 도로 유지보수 안전기준과 계약 지침을 조사해줘")[0]

    result = await provider.search(query)

    assert result.candidates == ()
    assert result.failures[0].code == "CURATED_SCOPE_UNSUPPORTED"
    assert result.failures[0].retryable is False


@pytest.mark.anyio
async def test_curated_provider_respects_track_and_result_limit() -> None:
    provider = CuratedOfficialSourceProvider()
    query = _queries("공공기관 인공지능 도입 계약과 구매 기준을 조사해줘")[0]

    unknown = await provider.search(replace(query, track_id="unknown"))
    limited = await provider.search(replace(query, max_results=0))

    assert unknown.candidates == ()
    assert limited.candidates == ()
    assert limited.failures[0].code == "QUERY_INVALID"
