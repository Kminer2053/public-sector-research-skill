from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from psr_mcp.planner import GovernmentPlanner
from psr_mcp.planner.models import ResearchPlan
from psr_mcp.search import GovernmentQueryBuilder


def _plan() -> ResearchPlan:
    return GovernmentPlanner().plan(
        question="공공기관 AI 구매의 데이터 권리와 업체 종속 방지 원칙을 조사해줘",
        as_of_date=date(2026, 7, 16),
        jurisdiction="KR",
        max_sources=12,
        max_bytes=31_457_280,
        timeout_seconds=20,
    )


def test_government_queries_are_deterministic_and_official_domain_first() -> None:
    builder = GovernmentQueryBuilder(max_results_per_track=3)

    first = builder.build(_plan())
    second = builder.build(_plan())

    assert first == second
    by_track = {query.track_id: query for query in first}
    assert by_track["law-regulation"].preferred_domains[0] == "law.go.kr"
    assert "site:law.go.kr" in by_track["law-regulation"].text
    assert by_track["privacy"].preferred_domains[0] == "pipc.go.kr"
    assert by_track["procurement"].max_results == 3
    assert all(query.id.startswith("qry-") for query in first)
    assert all(len(query.text) <= 512 for query in first)


def test_query_builder_limits_and_profile_fail_closed() -> None:
    with pytest.raises(ValueError, match="max_query_chars"):
        GovernmentQueryBuilder(max_query_chars=63)
    with pytest.raises(ValueError, match="max_results_per_track"):
        GovernmentQueryBuilder(max_results_per_track=21)
    with pytest.raises(ValueError, match="max_query_words"):
        GovernmentQueryBuilder(max_query_words=9)

    plan = replace(_plan(), profile="unsupported")
    with pytest.raises(ValueError, match="government-v0"):
        GovernmentQueryBuilder().build(plan)


def test_query_builder_preserves_official_domains_for_long_question() -> None:
    plan = replace(_plan(), question="긴질문 " * 650)

    query = GovernmentQueryBuilder(max_query_chars=128).build(plan)[0]

    assert len(query.text) <= 128
    assert len(query.text.split()) <= 50
    assert "(site:law.go.kr OR site:moleg.go.kr)" in query.text


def test_query_builder_rejects_suffix_that_cannot_fit_provider_limits() -> None:
    with pytest.raises(ValueError, match="max_query_words"):
        GovernmentQueryBuilder(max_query_words=10).build(_plan())
    with pytest.raises(ValueError, match="max_query_chars"):
        GovernmentQueryBuilder(
            max_query_chars=64,
            max_query_words=100,
        ).build(_plan())


@pytest.mark.anyio
async def test_static_search_provider_returns_configured_or_empty_result() -> None:
    from psr_mcp.search import SearchResult, StaticSearchProvider

    query = GovernmentQueryBuilder().build(_plan())[0]
    expected = SearchResult(candidates=())
    provider = StaticSearchProvider({query.track_id: expected})

    assert await provider.search(query) == expected
    unknown = replace(query, track_id="unknown")
    assert await provider.search(unknown) == SearchResult(candidates=())
