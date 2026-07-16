"""Official-first quick research pipeline with partial-success semantics."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import HttpUrl

from psr_mcp.collectors.access_policy import SourceAccessPolicy
from psr_mcp.collectors.safe import CollectionError, SafeCollector
from psr_mcp.collectors.url_policy import UrlPolicyError
from psr_mcp.evidence import (
    CitationConstrainedWriter,
    DocumentQualityAssessor,
    EvidenceComposer,
    EvidenceDocument,
    EvidencePack,
)
from psr_mcp.evidence.models import (
    EvidenceCitation,
    EvidenceFinding,
    EvidenceScore,
    ScoreComponent,
)
from psr_mcp.parsers import DocumentParser, ParseError
from psr_mcp.planner.models import ResearchPlan
from psr_mcp.public.schemas import (
    Citation,
    EvidenceScoreOutput,
    Finding,
    ResearchFailure,
    ScoreComponentOutput,
    SourceDiscoveryMode,
)
from psr_mcp.public.service import ResearchDraft
from psr_mcp.search import (
    GovernmentQueryBuilder,
    SearchFailure,
    SearchProvider,
    SearchQuery,
    SourceCandidate,
    SourceTier,
)


class PublicResearchPipeline:
    """Run search, collection, parsing, and evidence composition in memory."""

    def __init__(
        self,
        *,
        query_builder: GovernmentQueryBuilder,
        search_provider: SearchProvider,
        collector: SafeCollector,
        parser: DocumentParser,
        evidence: EvidenceComposer,
        source_policy: SourceAccessPolicy,
        quality: DocumentQualityAssessor | None = None,
        writer: CitationConstrainedWriter | None = None,
        max_collection_concurrency: int = 4,
        source_discovery: SourceDiscoveryMode = "test_static",
    ) -> None:
        if max_collection_concurrency < 1 or max_collection_concurrency > 20:
            raise ValueError("max_collection_concurrency must be 1..20")
        self._query_builder = query_builder
        self._search_provider = search_provider
        self._collector = collector
        self._parser = parser
        self._evidence = evidence
        self._source_policy = source_policy
        self._quality = quality or DocumentQualityAssessor()
        self._writer = writer or CitationConstrainedWriter()
        self._collection_semaphore = asyncio.Semaphore(max_collection_concurrency)
        self._source_discovery = source_discovery

    @property
    def available(self) -> bool:
        return True

    async def research(self, plan: ResearchPlan) -> ResearchDraft:
        queries = self._query_builder.build(plan)
        search_batches = await asyncio.gather(*(self._search(query) for query in queries))
        failures = [failure for batch in search_batches for failure in batch.failures]
        candidates = _select_candidates(
            plan,
            tuple(candidate for batch in search_batches for candidate in batch.candidates),
        )
        selected, omitted_sources = _limit_candidates_by_source(
            candidates,
            plan.stop_conditions.max_sources,
        )
        if omitted_sources:
            failures.append(
                ResearchFailure(
                    code="SOURCE_LIMIT_REACHED",
                    message="candidate sources exceeded the configured source limit",
                    retryable=False,
                )
            )

        collection_groups = _group_candidates_by_url(selected)
        per_source_budget = (
            max(1, plan.stop_conditions.max_bytes // len(collection_groups))
            if collection_groups
            else 0
        )
        collection_results = await asyncio.gather(
            *(self._collect_candidate(group[0], per_source_budget) for group in collection_groups)
        )
        documents: list[EvidenceDocument] = []
        for group, result in zip(collection_groups, collection_results, strict=True):
            if result.failure is not None:
                failures.append(result.failure)
            if result.document is not None:
                documents.extend(
                    EvidenceDocument(
                        candidate=candidate,
                        collected=result.document.collected,
                        parsed=result.document.parsed,
                    )
                    for candidate in group
                )

        unique_documents, document_duplicates = _deduplicate_documents(documents)
        evidence_pack = self._evidence.compose(
            question=plan.question,
            as_of_date=plan.as_of_date,
            documents=tuple(unique_documents),
            terms_by_track={track.id: track.selection_terms for track in plan.tracks},
        )
        citations = tuple(_citation(citation) for citation in evidence_pack.citations)
        findings = tuple(
            _finding(finding) for finding in self._writer.write(evidence_pack.citations)
        )
        gaps = _gaps(plan, evidence_pack)
        if self._source_discovery == "curated_seed":
            gaps = (
                *gaps,
                "실시간 웹 검색이 아니라 검토된 제한적 공식자료 "
                "seed catalog 범위에서 조사했습니다.",
            )
        if document_duplicates:
            gaps = (
                *gaps,
                (
                    f"동일 원문 hash의 중복 배포본 {document_duplicates}건을 "
                    "독립 근거에서 제외했습니다."
                ),
            )
        status: Literal["PARTIAL", "SUCCEEDED"] = (
            "SUCCEEDED" if citations and not gaps and not failures else "PARTIAL"
        )
        official_primary = sum(
            citation.source_tier is SourceTier.OFFICIAL_PRIMARY
            for citation in evidence_pack.citations
        )
        recommendation_count = sum(finding.kind == "RECOMMENDATION" for finding in findings)
        summary = (
            f"공식자료 우선 조사에서 인용 가능한 원문 구간 {len(citations)}건을 확인했습니다. "
            f"그중 공식 1차자료는 {official_primary}건입니다. "
            f"근거 anchor가 충족된 조달 원칙 검토안은 {recommendation_count}건입니다. "
            "확정적 법률·적용 판단은 자동 생성하지 않고 확인된 원문과 미확인 범위를 분리했습니다."
        )
        return ResearchDraft(
            status=status,
            source_discovery=self._source_discovery,
            summary=summary,
            findings=findings,
            citations=citations,
            gaps=gaps,
            conflicts=(),
            failures=tuple(failures),
            source_bytes=_source_bundle(unique_documents),
            extracted_bytes=_extracted_bundle(unique_documents),
        )

    async def _collect_candidate(
        self,
        candidate: SourceCandidate,
        max_response_bytes: int,
    ) -> _CollectionResult:
        async with self._collection_semaphore:
            access = await self._source_policy.evaluate(
                candidate.url,
                max_response_bytes=max_response_bytes,
            )
            if not access.allowed:
                return _CollectionResult(
                    document=None,
                    failure=_failure(
                        code=f"SOURCE_ACCESS_{access.status.value}",
                        message=access.explanation,
                        retryable=access.retryable,
                    ),
                )
            document_budget = max_response_bytes - access.bytes_consumed
            if document_budget < 1:
                return _CollectionResult(
                    document=None,
                    failure=_failure(
                        code="SOURCE_ACCESS_BYTE_BUDGET",
                        message="robots policy consumed the source byte budget",
                        retryable=False,
                    ),
                )
            try:
                collected = await self._collector.collect(
                    candidate.url,
                    max_response_bytes=document_budget,
                )
            except UrlPolicyError as error:
                return _CollectionResult(
                    document=None,
                    failure=_failure(
                        code=f"URL_{error.code.value}",
                        message="candidate source failed the public URL policy",
                        retryable=error.retryable,
                    ),
                )
            except CollectionError as error:
                return _CollectionResult(
                    document=None,
                    failure=_failure(
                        code=f"COLLECT_{error.code.value}",
                        message="candidate source could not be collected safely",
                        retryable=error.retryable,
                    ),
                )
            except Exception:
                return _CollectionResult(
                    document=None,
                    failure=_failure(
                        code="COLLECT_INTERNAL_ERROR",
                        message="candidate source collection failed safely",
                        retryable=False,
                    ),
                )
            try:
                parsed = await asyncio.to_thread(
                    self._parser.parse,
                    collected.body,
                    content_type=collected.content_type,
                )
            except ParseError as error:
                return _CollectionResult(
                    document=None,
                    failure=_failure(
                        code=f"PARSE_{error.code.value}",
                        message="collected source could not be parsed safely",
                        retryable=error.retryable,
                    ),
                )
            except Exception:
                return _CollectionResult(
                    document=None,
                    failure=_failure(
                        code="PARSE_INTERNAL_ERROR",
                        message="collected source parsing failed safely",
                        retryable=False,
                    ),
                )
            quality = self._quality.assess(
                parsed,
                source_url=collected.final_url,
            )
            if not quality.usable:
                return _CollectionResult(
                    document=None,
                    failure=_failure(
                        code=f"DOCUMENT_{quality.status.value}",
                        message=quality.explanation,
                        retryable=False,
                    ),
                )
            return _CollectionResult(
                document=EvidenceDocument(
                    candidate=candidate,
                    collected=collected,
                    parsed=parsed,
                ),
                failure=None,
            )

    async def _search(self, query: SearchQuery) -> _SearchBatch:
        try:
            result = await self._search_provider.search(query)
        except Exception:
            return _SearchBatch(
                candidates=(),
                failures=(
                    _failure(
                        code="SEARCH_PROVIDER_FAILED",
                        message="source search provider failed safely",
                        retryable=True,
                    ),
                ),
            )
        candidates: list[SourceCandidate] = []
        failures = [_search_failure(failure) for failure in result.failures]
        for candidate in result.candidates:
            if candidate.track_id != query.track_id:
                failures.append(
                    _failure(
                        code="SEARCH_RESULT_INVALID",
                        message="search candidate track did not match its query",
                        retryable=False,
                    )
                )
                continue
            candidates.append(candidate)
        return _SearchBatch(candidates=tuple(candidates), failures=tuple(failures))


@dataclass(frozen=True, slots=True)
class _SearchBatch:
    candidates: tuple[SourceCandidate, ...]
    failures: tuple[ResearchFailure, ...]


@dataclass(frozen=True, slots=True)
class _CollectionResult:
    document: EvidenceDocument | None
    failure: ResearchFailure | None


def _select_candidates(
    plan: ResearchPlan,
    candidates: tuple[SourceCandidate, ...],
) -> tuple[SourceCandidate, ...]:
    track_order = {track.id: index for index, track in enumerate(plan.tracks)}
    grouped: dict[str, list[SourceCandidate]] = defaultdict(list)
    seen_urls: set[tuple[str, str]] = set()
    for candidate in candidates:
        if candidate.track_id not in track_order:
            continue
        key = (candidate.track_id, _candidate_url_key(candidate.url))
        if key in seen_urls:
            continue
        seen_urls.add(key)
        grouped[candidate.track_id].append(candidate)
    for track_candidates in grouped.values():
        track_candidates.sort(
            key=lambda candidate: (
                _authority(candidate.source_tier),
                candidate.published_at is not None,
                candidate.published_at,
                candidate.id,
            ),
            reverse=True,
        )

    selected: list[SourceCandidate] = []
    while any(grouped.values()):
        for track in plan.tracks:
            track_candidates = grouped[track.id]
            if track_candidates:
                selected.append(track_candidates.pop(0))
    return tuple(selected)


def _deduplicate_documents(
    documents: list[EvidenceDocument],
) -> tuple[list[EvidenceDocument], int]:
    by_hash: dict[tuple[str, str], EvidenceDocument] = {}
    duplicates = 0
    for document in documents:
        key = (
            document.candidate.track_id,
            document.collected.sha256,
        )
        existing = by_hash.get(key)
        if existing is None:
            by_hash[key] = document
            continue
        duplicates += 1
        if _authority(document.candidate.source_tier) > _authority(existing.candidate.source_tier):
            by_hash[key] = document
    return list(by_hash.values()), duplicates


def _limit_candidates_by_source(
    candidates: tuple[SourceCandidate, ...],
    max_sources: int,
) -> tuple[tuple[SourceCandidate, ...], int]:
    selected: list[SourceCandidate] = []
    selected_urls: set[str] = set()
    omitted_urls: set[str] = set()
    for candidate in candidates:
        key = _candidate_url_key(candidate.url)
        if key in selected_urls:
            selected.append(candidate)
            continue
        if len(selected_urls) < max_sources:
            selected_urls.add(key)
            selected.append(candidate)
            continue
        omitted_urls.add(key)
    return tuple(selected), len(omitted_urls)


def _group_candidates_by_url(
    candidates: tuple[SourceCandidate, ...],
) -> tuple[tuple[SourceCandidate, ...], ...]:
    groups: dict[str, list[SourceCandidate]] = {}
    for candidate in candidates:
        groups.setdefault(_candidate_url_key(candidate.url), []).append(candidate)
    return tuple(tuple(group) for group in groups.values())


def _candidate_url_key(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        port = parsed.port
    except ValueError:
        return url
    netloc = host if port in {None, 443} else f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.casefold(), netloc, path, parsed.query, ""))


def _gaps(plan: ResearchPlan, evidence_pack: EvidencePack) -> tuple[str, ...]:
    represented_tracks = {citation.track_id for citation in evidence_pack.citations}
    gaps = list(evidence_pack.gaps)
    for track in plan.tracks:
        if track.id not in represented_tracks:
            gaps.append(f"{track.title}: 인용 가능한 공식 원문 근거를 확보하지 못했습니다.")
    if plan.stop_conditions.require_official_primary and not any(
        citation.source_tier is SourceTier.OFFICIAL_PRIMARY for citation in evidence_pack.citations
    ):
        gaps.append("공식 1차자료 원문을 확보하지 못했습니다.")
    return tuple(gaps)


def _citation(citation: EvidenceCitation) -> Citation:
    return Citation(
        id=citation.id,
        track_id=citation.track_id,
        title=citation.title,
        publisher=citation.publisher,
        url=HttpUrl(citation.url),
        retrieved_at=citation.retrieved_at,
        locator=citation.locator,
        excerpt=citation.excerpt,
        source_tier=citation.source_tier.value,
        document_sha256=citation.document_sha256,
        score=_score(citation.score),
    )


def _finding(finding: EvidenceFinding) -> Finding:
    return Finding(
        claim=finding.claim,
        kind=finding.kind,
        citation_ids=list(finding.citation_ids),
        confidence=finding.confidence,
    )


def _score(score: EvidenceScore) -> EvidenceScoreOutput:
    return EvidenceScoreOutput(
        overall=score.overall,
        authority=_component(score.authority),
        primary_source=_component(score.primary_source),
        direct_relevance=_component(score.direct_relevance),
        original_snapshot=_component(score.original_snapshot),
        specificity=_component(score.specificity),
        freshness=_component(score.freshness),
        independence=_component(score.independence),
    )


def _component(component: ScoreComponent) -> ScoreComponentOutput:
    return ScoreComponentOutput(
        value=component.value,
        explanation=component.explanation,
    )


def _confidence(score: float) -> Literal["HIGH", "MEDIUM", "LOW"]:
    if score >= 0.8:
        return "HIGH"
    if score >= 0.6:
        return "MEDIUM"
    return "LOW"


def _source_bundle(documents: list[EvidenceDocument]) -> bytes:
    return b"\n\n--PSR-DOCUMENT--\n\n".join(document.collected.body for document in documents)


def _extracted_bundle(documents: list[EvidenceDocument]) -> bytes:
    sections: list[str] = []
    for document in documents:
        sections.append(f"# {document.candidate.title}")
        sections.extend(
            f"[{passage.locator}] {passage.text}" for passage in document.parsed.passages
        )
    return "\n".join(sections).encode()


def _search_failure(failure: SearchFailure) -> ResearchFailure:
    return _failure(
        code=f"SEARCH_{failure.code}",
        message=failure.message,
        retryable=failure.retryable,
    )


def _failure(
    *,
    code: str,
    message: str,
    retryable: bool,
) -> ResearchFailure:
    return ResearchFailure(
        code=code,
        message=message,
        retryable=retryable,
    )


def _authority(tier: SourceTier) -> float:
    return _AUTHORITY[tier]


_AUTHORITY = {
    SourceTier.TEST_FIXTURE: 0.0,
    SourceTier.UNVERIFIED_WEB: 0.1,
    SourceTier.OFFICIAL_PRIMARY: 1.0,
    SourceTier.ACADEMIC_PRIMARY: 0.9,
    SourceTier.OFFICIAL_SECONDARY: 0.8,
    SourceTier.COMPANY_OFFICIAL: 0.75,
    SourceTier.REPUTABLE_MEDIA: 0.5,
    SourceTier.COMMUNITY: 0.2,
}
