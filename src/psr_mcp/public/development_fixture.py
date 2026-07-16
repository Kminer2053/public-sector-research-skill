"""Development-only synthetic backend that exercises the real quick pipeline."""

from __future__ import annotations

import ipaddress
from dataclasses import replace

from psr_mcp.application.ports import Clock
from psr_mcp.collectors.access_policy import AllowAllSourceAccessPolicy
from psr_mcp.collectors.models import CollectionLimits, RawHttpResponse
from psr_mcp.collectors.safe import SafeCollector
from psr_mcp.collectors.url_policy import IpAddress, UrlPolicy, ValidatedUrl
from psr_mcp.evidence import EvidenceComposer
from psr_mcp.parsers import DocumentParser
from psr_mcp.planner.models import ResearchPlan
from psr_mcp.public.pipeline import PublicResearchPipeline
from psr_mcp.public.schemas import ResearchFailure
from psr_mcp.public.service import ResearchDraft
from psr_mcp.search import (
    GovernmentQueryBuilder,
    SearchResult,
    SourceCandidate,
    SourceTier,
    StaticSearchProvider,
)


class DevelopmentFixtureResearchBackend:
    """Mark synthetic pipeline output so it can never be mistaken for research."""

    def __init__(self, pipeline: PublicResearchPipeline) -> None:
        self._pipeline = pipeline

    @property
    def available(self) -> bool:
        return True

    async def research(self, plan: ResearchPlan) -> ResearchDraft:
        draft = await self._pipeline.research(plan)
        return replace(
            draft,
            status="PARTIAL",
            summary=(
                "개발용 합성 문서로 전체 조사 파이프라인을 검증한 결과입니다. "
                "실제 외부 사실이나 공공기관 판단 근거로 사용하면 안 됩니다. " + draft.summary
            ),
            gaps=(
                "실제 SearchProvider와 공식 외부 원문은 연결되지 않았습니다.",
                *draft.gaps,
            ),
            failures=(
                ResearchFailure(
                    code="FIXTURE_ONLY",
                    message="synthetic development documents were used",
                    retryable=False,
                ),
                *draft.failures,
            ),
        )


def build_development_fixture_backend(clock: Clock) -> DevelopmentFixtureResearchBackend:
    results: dict[str, SearchResult] = {}
    responses: dict[str, RawHttpResponse] = {}
    hosts: set[str] = set()
    for index, (track_id, title) in enumerate(_TRACKS, start=1):
        host = f"fixture{index}.go.kr"
        url = f"https://{host}/{track_id}"
        candidate = SourceCandidate(
            id=f"fixture-{track_id}",
            track_id=track_id,
            url=url,
            title=f"합성 {title} 검증 문서",
            publisher="PSR 합성 fixture",
            source_tier=SourceTier.TEST_FIXTURE,
        )
        results[track_id] = SearchResult(candidates=(candidate,))
        responses[url] = RawHttpResponse(
            status=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body=_fixture_html(track_id, title),
        )
        hosts.add(host)
    collector = SafeCollector(
        policy=UrlPolicy(_FixtureResolver(frozenset(hosts))),
        transport=_FixtureTransport(responses),
        clock=clock,
        limits=CollectionLimits(max_response_bytes=1_048_576),
    )
    return DevelopmentFixtureResearchBackend(
        PublicResearchPipeline(
            query_builder=GovernmentQueryBuilder(max_results_per_track=1),
            search_provider=StaticSearchProvider(results),
            collector=collector,
            parser=DocumentParser(),
            evidence=EvidenceComposer(max_citations=12, max_per_document=1),
            source_policy=AllowAllSourceAccessPolicy(),
            source_discovery="development_fixture",
        )
    )


class _FixtureResolver:
    def __init__(self, hosts: frozenset[str]) -> None:
        self._hosts = hosts

    async def resolve(self, host: str, port: int) -> tuple[IpAddress, ...]:
        del port
        if host not in self._hosts:
            return ()
        return (ipaddress.ip_address("93.184.216.34"),)


class _FixtureTransport:
    def __init__(self, responses: dict[str, RawHttpResponse]) -> None:
        self._responses = responses

    async def fetch(
        self,
        target: ValidatedUrl,
        limits: CollectionLimits,
    ) -> RawHttpResponse:
        response = self._responses[target.canonical_url]
        if len(response.body) > limits.max_response_bytes:
            raise RuntimeError("development fixture violated its configured byte limit")
        return response


def _fixture_html(track_id: str, title: str) -> bytes:
    return (
        "<html><head>"
        f"<title>합성 {title} 검증 문서</title>"
        "</head><body>"
        f"<h1>{title}</h1>"
        f"<p>공공기관 AI 구매와 데이터 권리, 개인정보, 업체 종속 관련 {track_id} "
        "파이프라인 검증용 문장입니다.</p>"
        "</body></html>"
    ).encode()


_TRACKS = (
    ("law-regulation", "법령·규정"),
    ("government-policy", "정부 정책·가이드"),
    ("procurement", "조달·계약"),
    ("privacy", "개인정보·데이터 보호"),
    ("international-standards", "국제기구·표준"),
    ("vendor-lock-in", "업체 종속·이전성"),
    ("data-rights", "데이터 권리·학습 재사용"),
)
