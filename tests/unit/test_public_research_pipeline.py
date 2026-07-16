from __future__ import annotations

import ipaddress
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import cast

import pytest

from psr_mcp.application.ports import Clock
from psr_mcp.collectors.access_policy import (
    AllowAllSourceAccessPolicy,
    SourceAccessDecision,
    SourceAccessPolicy,
    SourceAccessStatus,
)
from psr_mcp.collectors.models import CollectionLimits, RawHttpResponse
from psr_mcp.collectors.safe import PinnedHttpTransport, SafeCollector
from psr_mcp.collectors.url_policy import HostResolver, IpAddress, UrlPolicy, ValidatedUrl
from psr_mcp.evidence import EvidenceComposer
from psr_mcp.parsers import DocumentParser, ParsedDocument
from psr_mcp.planner import GovernmentPlanner
from psr_mcp.planner.models import ResearchPlan, StopConditions
from psr_mcp.public.pipeline import (
    PublicResearchPipeline,
    _candidate_url_key,
    _confidence,
    _select_candidates,
)
from psr_mcp.search import (
    GovernmentQueryBuilder,
    SearchFailure,
    SearchProvider,
    SearchResult,
    SourceCandidate,
    SourceTier,
    StaticSearchProvider,
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 16, tzinfo=UTC)


class Resolver:
    def __init__(
        self,
        records: dict[str, tuple[str, ...]],
    ) -> None:
        self.records = records

    async def resolve(self, host: str, port: int) -> tuple[IpAddress, ...]:
        del port
        return tuple(ipaddress.ip_address(value) for value in self.records.get(host, ()))


class Transport:
    def __init__(self, responses: dict[str, RawHttpResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []
        self.limits: dict[str, int] = {}

    async def fetch(
        self,
        target: ValidatedUrl,
        limits: CollectionLimits,
    ) -> RawHttpResponse:
        self.calls.append(target.canonical_url)
        self.limits[target.canonical_url] = limits.max_response_bytes
        response = self.responses[target.canonical_url]
        if len(response.body) > limits.max_response_bytes:
            from psr_mcp.collectors.safe import CollectionError, CollectionErrorCode

            raise CollectionError(
                CollectionErrorCode.RESPONSE_TOO_LARGE,
                "fixture exceeded request limit",
                retryable=False,
            )
        return response


class ExplodingSearchProvider:
    async def search(self, query: object) -> SearchResult:
        del query
        raise RuntimeError("provider unavailable")


class ExplodingParser:
    def parse(self, body: bytes, *, content_type: str | None) -> ParsedDocument:
        del body, content_type
        raise RuntimeError("parser exploded")


class FixedSourcePolicy:
    def __init__(self, decision: SourceAccessDecision) -> None:
        self.decision = decision

    async def evaluate(
        self,
        url: str,
        *,
        max_response_bytes: int,
    ) -> SourceAccessDecision:
        del url, max_response_bytes
        return self.decision


def _plan(question: str = "공공기관 AI 구매의 데이터 권리와 업체 종속 방지 원칙") -> ResearchPlan:
    return GovernmentPlanner().plan(
        question=question,
        as_of_date=date(2026, 7, 16),
        jurisdiction="KR",
        max_sources=12,
        max_bytes=31_457_280,
        timeout_seconds=20,
    )


def _candidate(
    track_id: str,
    *,
    host: str,
    tier: SourceTier = SourceTier.OFFICIAL_PRIMARY,
    candidate_id: str | None = None,
) -> SourceCandidate:
    return SourceCandidate(
        id=candidate_id or f"candidate-{track_id}",
        track_id=track_id,
        url=f"https://{host}/{track_id}",
        title=f"{track_id} 공식 지침",
        publisher=f"{track_id} 담당기관",
        source_tier=tier,
        published_at=date(2026, 1, 1),
    )


def _body(track_id: str) -> bytes:
    return (
        "<html><body>"
        f"<h1>{track_id} AI 구매 기준</h1>"
        f"<p>공공 AI 구매의 데이터 권리와 업체 종속 방지를 위한 {track_id} 근거입니다.</p>"
        "</body></html>"
    ).encode()


def _pipeline(
    *,
    plan: ResearchPlan,
    results: dict[str, SearchResult],
    responses: dict[str, RawHttpResponse],
    records: dict[str, tuple[str, ...]],
    source_policy: SourceAccessPolicy | None = None,
) -> tuple[PublicResearchPipeline, Transport, SafeCollector]:
    del plan
    transport = Transport(responses)
    collector = SafeCollector(
        policy=UrlPolicy(cast(HostResolver, Resolver(records))),
        transport=cast(PinnedHttpTransport, transport),
        clock=cast(Clock, FixedClock()),
        limits=CollectionLimits(max_response_bytes=4_096),
    )
    return (
        PublicResearchPipeline(
            query_builder=GovernmentQueryBuilder(),
            search_provider=StaticSearchProvider(results),
            collector=collector,
            parser=DocumentParser(),
            evidence=EvidenceComposer(max_citations=12, max_per_document=1),
            source_policy=source_policy or AllowAllSourceAccessPolicy(),
        ),
        transport,
        collector,
    )


@pytest.mark.anyio
async def test_pipeline_golden_question_covers_every_track_with_cited_facts() -> None:
    plan = _plan()
    results: dict[str, SearchResult] = {}
    responses: dict[str, RawHttpResponse] = {}
    records: dict[str, tuple[str, ...]] = {}
    for index, track in enumerate(plan.tracks, start=1):
        host = f"source{index}.go.kr"
        candidate = _candidate(track.id, host=host)
        results[track.id] = SearchResult(candidates=(candidate,))
        responses[candidate.url] = RawHttpResponse(
            status=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body=_body(track.id),
        )
        records[host] = ("93.184.216.34",)
    pipeline, transport, _ = _pipeline(
        plan=plan,
        results=results,
        responses=responses,
        records=records,
    )

    draft = await pipeline.research(plan)

    assert draft.status == "SUCCEEDED"
    assert len(draft.citations) == len(plan.tracks)
    assert {citation.source_tier for citation in draft.citations} == {"OFFICIAL_PRIMARY"}
    assert all(citation.locator for citation in draft.citations)
    assert all(citation.score.overall > 0.7 for citation in draft.citations)
    assert all(finding.kind == "FACT" for finding in draft.findings)
    assert all(len(finding.citation_ids) == 1 for finding in draft.findings)
    assert draft.gaps == ()
    assert draft.failures == ()
    assert len(transport.calls) == len(plan.tracks)
    assert b"--PSR-DOCUMENT--" in draft.source_bytes
    assert b"html:p[1]" in draft.extracted_bytes


@pytest.mark.anyio
async def test_pipeline_preserves_successes_and_reports_search_collection_parse_failures() -> None:
    plan = _plan("공공기관 AI 정책과 개인정보 조달 기준 조사")
    law = _candidate("law-regulation", host="law.go.kr")
    private = _candidate("government-policy", host="private.go.kr")
    pdf = _candidate("procurement", host="procurement.go.kr")
    mismatched = _candidate("privacy", host="privacy.go.kr")
    login = _candidate(
        "privacy",
        host="login.go.kr",
        candidate_id="privacy-login",
    )
    results = {
        "law-regulation": SearchResult(candidates=(law,)),
        "government-policy": SearchResult(candidates=(private,)),
        "procurement": SearchResult(candidates=(pdf,)),
        "privacy": SearchResult(
            candidates=(
                replace(mismatched, track_id="law-regulation"),
                login,
            )
        ),
        "international-standards": SearchResult(
            candidates=(),
            failures=(
                SearchFailure(
                    query_id="fixture",
                    code="UPSTREAM_TIMEOUT",
                    message="official search timed out",
                    retryable=True,
                ),
            ),
        ),
    }
    responses = {
        law.url: RawHttpResponse(
            status=200,
            headers={"content-type": "text/html"},
            body=_body("law-regulation"),
        ),
        pdf.url: RawHttpResponse(
            status=200,
            headers={"content-type": "application/pdf"},
            body=b"%PDF-1.7\nfixture",
        ),
        login.url: RawHttpResponse(
            status=200,
            headers={"content-type": "text/html"},
            body=(
                "<html><body><p>이 문서를 보려면 로그인이 필요합니다. "
                "로그인 후 이용해 주세요.</p></body></html>"
            ).encode(),
        ),
    }
    pipeline, transport, _ = _pipeline(
        plan=plan,
        results=results,
        responses=responses,
        records={
            "law.go.kr": ("93.184.216.34",),
            "private.go.kr": ("127.0.0.1",),
            "procurement.go.kr": ("93.184.216.35",),
            "privacy.go.kr": ("93.184.216.36",),
            "login.go.kr": ("93.184.216.37",),
        },
    )

    draft = await pipeline.research(plan)

    assert draft.status == "PARTIAL"
    assert len(draft.citations) == 1
    codes = {failure.code for failure in draft.failures}
    assert "SEARCH_UPSTREAM_TIMEOUT" in codes
    assert "SEARCH_RESULT_INVALID" in codes
    assert "URL_ADDRESS_NOT_PUBLIC" in codes
    assert "PARSE_INVALID_DOCUMENT" in codes
    assert "DOCUMENT_LOGIN_REQUIRED" in codes
    assert any("공식 원문 근거" in gap for gap in draft.gaps)
    assert set(transport.calls) == {law.url, pdf.url, login.url}


@pytest.mark.anyio
async def test_pipeline_distributes_a_hard_total_byte_budget_across_sources() -> None:
    base = _plan("공공기관 AI 정책과 개인정보 조달 기준 조사")
    body = b"AI policy evidence with enough reviewable text"
    plan = replace(
        base,
        stop_conditions=StopConditions(
            max_sources=12,
            max_bytes=len(body),
            timeout_seconds=20,
            require_official_primary=True,
        ),
    )
    law = _candidate("law-regulation", host="law.go.kr")
    policy = _candidate("government-policy", host="policy.go.kr")
    results = {
        "law-regulation": SearchResult(candidates=(law,)),
        "government-policy": SearchResult(candidates=(policy,)),
    }
    responses = {
        law.url: RawHttpResponse(
            status=200,
            headers={"content-type": "text/plain"},
            body=body,
        ),
        policy.url: RawHttpResponse(
            status=200,
            headers={"content-type": "text/plain"},
            body=body,
        ),
    }
    pipeline, transport, _ = _pipeline(
        plan=plan,
        results=results,
        responses=responses,
        records={
            "law.go.kr": ("93.184.216.34",),
            "policy.go.kr": ("93.184.216.35",),
        },
    )

    draft = await pipeline.research(plan)

    assert set(transport.calls) == {law.url, policy.url}
    assert sum(transport.limits.values()) <= len(body)
    assert all(failure.code == "COLLECT_RESPONSE_TOO_LARGE" for failure in draft.failures)
    assert draft.status == "PARTIAL"


@pytest.mark.anyio
async def test_pipeline_provider_exception_is_typed_and_does_not_collect() -> None:
    plan = _plan("공공기관 AI 정책과 개인정보 조달 기준 조사")
    _, transport, collector = _pipeline(
        plan=plan,
        results={},
        responses={},
        records={},
    )
    pipeline = PublicResearchPipeline(
        query_builder=GovernmentQueryBuilder(),
        search_provider=cast(SearchProvider, ExplodingSearchProvider()),
        collector=collector,
        parser=DocumentParser(),
        evidence=EvidenceComposer(),
        source_policy=AllowAllSourceAccessPolicy(),
    )

    draft = await pipeline.research(plan)

    assert draft.status == "PARTIAL"
    assert draft.citations == ()
    assert len(draft.failures) == len(plan.tracks)
    assert {failure.code for failure in draft.failures} == {"SEARCH_PROVIDER_FAILED"}
    assert transport.calls == []


@pytest.mark.anyio
async def test_pipeline_source_limit_and_collection_failures_are_typed() -> None:
    base = _plan("공공기관 AI 정책과 개인정보 조달 기준 조사")
    plan = replace(
        base,
        stop_conditions=replace(base.stop_conditions, max_sources=2),
    )
    law = _candidate("law-regulation", host="law.go.kr")
    law_extra = _candidate(
        "law-regulation",
        host="missing.go.kr",
        candidate_id="law-extra",
    )
    policy = _candidate("government-policy", host="large.go.kr")
    procurement = _candidate("procurement", host="unused.go.kr")
    results = {
        "law-regulation": SearchResult(candidates=(law, law_extra)),
        "government-policy": SearchResult(candidates=(policy,)),
        "procurement": SearchResult(candidates=(procurement,)),
    }
    pipeline, _, _ = _pipeline(
        plan=plan,
        results=results,
        responses={
            policy.url: RawHttpResponse(
                status=200,
                headers={"content-type": "text/plain"},
                body=b"x" * 5_000,
            )
        },
        records={
            "law.go.kr": ("93.184.216.34",),
            "missing.go.kr": ("93.184.216.35",),
            "large.go.kr": ("93.184.216.36",),
            "unused.go.kr": ("93.184.216.37",),
        },
    )

    draft = await pipeline.research(plan)

    codes = {failure.code for failure in draft.failures}
    assert "SOURCE_LIMIT_REACHED" in codes
    assert "COLLECT_INTERNAL_ERROR" in codes
    assert "COLLECT_RESPONSE_TOO_LARGE" in codes


@pytest.mark.anyio
async def test_pipeline_parser_exception_and_snapshot_duplicate_are_isolated() -> None:
    plan = _plan("공공기관 AI 정책과 개인정보 조달 기준 조사")
    law = _candidate(
        "law-regulation",
        host="law.go.kr",
        tier=SourceTier.REPUTABLE_MEDIA,
    )
    policy = _candidate(
        "government-policy",
        host="policy.go.kr",
        tier=SourceTier.OFFICIAL_PRIMARY,
    )
    privacy = _candidate("privacy", host="privacy.go.kr")
    duplicate_body = b"AI policy evidence with enough reviewable text"
    results = {
        "law-regulation": SearchResult(candidates=(law,)),
        "government-policy": SearchResult(candidates=(policy,)),
        "privacy": SearchResult(candidates=(privacy,)),
    }
    _, _, collector = _pipeline(
        plan=plan,
        results=results,
        responses={
            law.url: RawHttpResponse(
                status=200,
                headers={"content-type": "text/plain"},
                body=duplicate_body,
            ),
            policy.url: RawHttpResponse(
                status=200,
                headers={"content-type": "text/plain"},
                body=duplicate_body,
            ),
            privacy.url: RawHttpResponse(
                status=200,
                headers={"content-type": "text/plain"},
                body=b"privacy evidence with enough reviewable text",
            ),
        },
        records={
            "law.go.kr": ("93.184.216.34",),
            "policy.go.kr": ("93.184.216.35",),
            "privacy.go.kr": ("93.184.216.36",),
        },
    )
    exploding = PublicResearchPipeline(
        query_builder=GovernmentQueryBuilder(),
        search_provider=StaticSearchProvider({"privacy": SearchResult(candidates=(privacy,))}),
        collector=collector,
        parser=cast(DocumentParser, ExplodingParser()),
        evidence=EvidenceComposer(),
        source_policy=AllowAllSourceAccessPolicy(),
    )

    failed = await exploding.research(plan)

    assert any(failure.code == "PARSE_INTERNAL_ERROR" for failure in failed.failures)

    working = PublicResearchPipeline(
        query_builder=GovernmentQueryBuilder(),
        search_provider=StaticSearchProvider(results),
        collector=collector,
        parser=DocumentParser(),
        evidence=EvidenceComposer(),
        source_policy=AllowAllSourceAccessPolicy(),
    )
    deduplicated = await working.research(plan)

    assert any("중복 배포본 1건" in gap for gap in deduplicated.gaps)
    assert any(
        citation.publisher == "government-policy 담당기관" for citation in deduplicated.citations
    )


def test_pipeline_candidate_normalization_and_confidence_boundaries() -> None:
    plan = _plan("공공기관 AI 정책과 개인정보 조달 기준 조사")
    primary = _candidate("law-regulation", host="LAW.GO.KR")
    duplicate = replace(
        primary,
        id="duplicate",
        url="https://law.go.kr:443/law-regulation#section",
    )
    unknown = _candidate("unknown-track", host="unknown.go.kr")

    selected = _select_candidates(plan, (duplicate, primary, unknown))

    assert len(selected) == 1
    assert _candidate_url_key("https://source.go.kr:bad/path") == ("https://source.go.kr:bad/path")
    assert _confidence(0.8) == "HIGH"
    assert _confidence(0.7) == "MEDIUM"
    assert _confidence(0.59) == "LOW"


def test_pipeline_reports_availability() -> None:
    plan = _plan()
    pipeline, _, collector = _pipeline(
        plan=plan,
        results={},
        responses={},
        records={},
    )

    assert pipeline.available is True
    with pytest.raises(ValueError, match="max_collection_concurrency"):
        PublicResearchPipeline(
            query_builder=GovernmentQueryBuilder(),
            search_provider=StaticSearchProvider({}),
            collector=collector,
            parser=DocumentParser(),
            evidence=EvidenceComposer(),
            source_policy=AllowAllSourceAccessPolicy(),
            max_collection_concurrency=0,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "decision, expected_code",
    [
        (
            SourceAccessDecision(
                SourceAccessStatus.DISALLOWED,
                "robots denied",
                retryable=False,
            ),
            "SOURCE_ACCESS_DISALLOWED",
        ),
        (
            SourceAccessDecision(
                SourceAccessStatus.ALLOWED,
                "robots consumed budget",
                retryable=False,
                bytes_consumed=100_000_000,
            ),
            "SOURCE_ACCESS_BYTE_BUDGET",
        ),
    ],
)
async def test_pipeline_honors_source_access_policy_before_document_fetch(
    decision: SourceAccessDecision,
    expected_code: str,
) -> None:
    plan = _plan("공공기관 AI 정책과 개인정보 조달 기준 조사")
    candidate = _candidate("law-regulation", host="law.go.kr")
    pipeline, transport, _ = _pipeline(
        plan=plan,
        results={"law-regulation": SearchResult(candidates=(candidate,))},
        responses={
            candidate.url: RawHttpResponse(
                status=200,
                headers={"content-type": "text/plain"},
                body=b"reviewable official evidence document",
            )
        },
        records={"law.go.kr": ("93.184.216.34",)},
        source_policy=FixedSourcePolicy(decision),
    )

    draft = await pipeline.research(plan)

    assert expected_code in {failure.code for failure in draft.failures}
    assert transport.calls == []
