"""Quick public research lifecycle with mandatory ephemeral purge."""

from __future__ import annotations

import asyncio
import html
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import HttpUrl

from psr_mcp.application.ports import Clock, IdGenerator
from psr_mcp.ephemeral.ports import ArtifactKind, EphemeralWorkspaceStore, WorkspaceRef
from psr_mcp.planner.government import GovernmentPlanner
from psr_mcp.planner.models import ResearchPlan
from psr_mcp.public.schemas import (
    AppliedScope,
    Citation,
    EvidenceScoreOutput,
    Finding,
    QuickResearchOutput,
    ResearchFailure,
    RetentionStatus,
    ScoreComponentOutput,
    SourceDiscoveryMode,
)


class PublicErrorCode(StrEnum):
    INPUT_INVALID = "INPUT_INVALID"
    PUBLIC_SERVICE_PAUSED = "PUBLIC_SERVICE_PAUSED"
    RESEARCH_NOT_AVAILABLE = "RESEARCH_NOT_AVAILABLE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    PURGE_PENDING = "PURGE_PENDING"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class PublicResearchError(Exception):
    def __init__(
        self,
        code: PublicErrorCode,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ResearchDraft:
    status: Literal["PARTIAL", "SUCCEEDED"]
    source_discovery: SourceDiscoveryMode
    summary: str
    findings: tuple[Finding, ...]
    citations: tuple[Citation, ...]
    gaps: tuple[str, ...]
    conflicts: tuple[str, ...]
    failures: tuple[ResearchFailure, ...]
    source_bytes: bytes
    extracted_bytes: bytes


class ResearchBackend(Protocol):
    @property
    def available(self) -> bool: ...

    async def research(self, plan: ResearchPlan) -> ResearchDraft: ...


class UnavailableResearchBackend:
    @property
    def available(self) -> bool:
        return False

    async def research(self, plan: ResearchPlan) -> ResearchDraft:
        del plan
        raise PublicResearchError(
            PublicErrorCode.RESEARCH_NOT_AVAILABLE,
            "public research collection is not available yet",
            retryable=False,
        )


class FixtureResearchBackend:
    """Development-only evidence fixture; never enabled in production."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    @property
    def available(self) -> bool:
        return True

    async def research(self, plan: ResearchPlan) -> ResearchDraft:
        track_titles = ", ".join(track.title for track in plan.tracks)
        citation = Citation(
            id="cit-fixture-1",
            track_id=plan.tracks[0].id,
            title="Public quick lifecycle development fixture",
            publisher="PSR MCP test fixture",
            url=HttpUrl("https://fixture.invalid/public-quick-lifecycle"),
            retrieved_at=self._clock.now(),
            locator="fixture section 1",
            excerpt="이 문서는 외부 사실 근거가 아닌 무보관 실행경로 검증용 fixture입니다.",
            source_tier="TEST_FIXTURE",
            document_sha256="0" * 64,
            score=EvidenceScoreOutput(
                overall=0.0,
                authority=ScoreComponentOutput(
                    value=0.0,
                    explanation="개발 fixture이며 실제 출처 권위성을 갖지 않음",
                ),
                primary_source=ScoreComponentOutput(
                    value=0.0,
                    explanation="실제 1차자료가 아님",
                ),
                direct_relevance=ScoreComponentOutput(
                    value=0.0,
                    explanation="lifecycle 검증 전용",
                ),
                original_snapshot=ScoreComponentOutput(
                    value=0.0,
                    explanation="외부 원문 snapshot이 아님",
                ),
                specificity=ScoreComponentOutput(
                    value=0.0,
                    explanation="fixture locator",
                ),
                freshness=ScoreComponentOutput(
                    value=0.0,
                    explanation="발행일 개념 없음",
                ),
                independence=ScoreComponentOutput(
                    value=0.0,
                    explanation="독립 근거가 아님",
                ),
            ),
        )
        findings = (
            Finding(
                claim=f"개발 fixture가 조사 track을 생성했습니다: {track_titles}",
                kind="INFERENCE",
                citation_ids=["cit-fixture-1"],
                confidence="LOW",
            ),
            Finding(
                claim="실제 업무 판단에는 공식 원문 수집과 별도 검토가 필요합니다.",
                kind="RECOMMENDATION",
                citation_ids=[],
                confidence="HIGH",
            ),
        )
        return ResearchDraft(
            status="PARTIAL",
            source_discovery="development_fixture",
            summary=(
                "무보관 quick lifecycle 검증 결과입니다. 실제 웹 조사는 아직 수행하지 않았습니다."
            ),
            findings=findings,
            citations=(citation,),
            gaps=("공식 원문 Search·Collector가 아직 연결되지 않았습니다.",),
            conflicts=(),
            failures=(
                ResearchFailure(
                    code="FIXTURE_ONLY",
                    message="development fixture was used instead of public web collection",
                    retryable=False,
                ),
            ),
            source_bytes=b"PSR-SOURCE-CONTENT-CANARY fixture source",
            extracted_bytes=b"PSR-EXTRACTED-CONTENT-CANARY fixture passage",
        )


class PublicQuickResearchService:
    def __init__(
        self,
        *,
        store: EphemeralWorkspaceStore,
        planner: GovernmentPlanner,
        backend: ResearchBackend,
        clock: Clock,
        ids: IdGenerator,
        run_ttl_seconds: int,
        orphan_max_age_seconds: int,
        max_sources: int,
        max_bytes: int,
        timeout_seconds: float,
        kill_switch: bool,
    ) -> None:
        self._store = store
        self._planner = planner
        self._backend = backend
        self._clock = clock
        self._ids = ids
        self._run_ttl_seconds = run_ttl_seconds
        self._orphan_max_age_seconds = orphan_max_age_seconds
        self._max_sources = max_sources
        self._max_bytes = max_bytes
        self._timeout_seconds = timeout_seconds
        self._kill_switch = kill_switch

    @property
    def available(self) -> bool:
        return self._backend.available and not self._kill_switch

    async def quick(
        self,
        *,
        question: str,
        as_of_date: date | None,
        jurisdiction: str,
        profile: str,
    ) -> QuickResearchOutput:
        if self._kill_switch:
            raise PublicResearchError(
                PublicErrorCode.PUBLIC_SERVICE_PAUSED,
                "new public research is temporarily paused",
                retryable=True,
            )
        if profile != self._planner.profile:
            raise PublicResearchError(
                PublicErrorCode.INPUT_INVALID,
                "unsupported public research profile",
                retryable=False,
            )
        now = self._clock.now()
        try:
            plan = self._planner.plan(
                question=question,
                as_of_date=as_of_date or now.date(),
                jurisdiction=jurisdiction,
                max_sources=self._max_sources,
                max_bytes=self._max_bytes,
                timeout_seconds=self._timeout_seconds,
            )
        except ValueError as error:
            raise PublicResearchError(
                PublicErrorCode.INPUT_INVALID,
                str(error),
                retryable=False,
            ) from None

        ref: WorkspaceRef | None = None
        purged = False
        try:
            ref = await self._store.create(
                expires_at=now + timedelta(seconds=self._run_ttl_seconds),
                hard_expires_at=now + timedelta(seconds=self._orphan_max_age_seconds),
            )
            await self._store.write_bytes(
                ref,
                ArtifactKind.QUESTION,
                plan.question.encode("utf-8"),
            )
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    draft = await self._backend.research(plan)
            except TimeoutError:
                raise PublicResearchError(
                    PublicErrorCode.BUDGET_EXHAUSTED,
                    "public quick research exceeded its time budget",
                    retryable=True,
                ) from None
            await self._store.write_bytes(ref, ArtifactKind.SOURCE, draft.source_bytes)
            await self._store.write_bytes(ref, ArtifactKind.EXTRACTED, draft.extracted_bytes)
            markdown = _render_markdown(draft, plan)
            result_body = (draft.summary + "\n" + markdown + "\nPSR-RESULT-CONTENT-CANARY").encode(
                "utf-8"
            )
            await self._store.write_bytes(ref, ArtifactKind.RESULT, result_body)
            try:
                await self._store.block_access(ref)
                purge_result = await self._store.purge(ref)
            except Exception:
                raise PublicResearchError(
                    PublicErrorCode.PURGE_PENDING,
                    "research content access is blocked but deletion needs retry",
                    retryable=True,
                ) from None
            purged = purge_result.deleted or purge_result.already_absent
            if not purged:
                raise PublicResearchError(
                    PublicErrorCode.PURGE_PENDING,
                    "research content could not be purged safely",
                    retryable=True,
                )
            purged_at = self._clock.now()
            return QuickResearchOutput(
                operation_id=self._ids.new(),
                status=draft.status,
                summary=draft.summary,
                scope=_scope(plan, draft.source_discovery),
                findings=list(draft.findings),
                citations=list(draft.citations),
                gaps=list(draft.gaps),
                conflicts=list(draft.conflicts),
                failures=list(draft.failures),
                markdown=markdown,
                retention=RetentionStatus(
                    purge_state="PURGED",
                    purged_at=purged_at,
                ),
            )
        except PublicResearchError:
            raise
        except Exception:
            raise PublicResearchError(
                PublicErrorCode.INTERNAL_ERROR,
                "public quick research failed safely",
                retryable=False,
            ) from None
        finally:
            if ref is not None and not purged:
                await _best_effort_purge(self._store, ref)


async def _best_effort_purge(
    store: EphemeralWorkspaceStore,
    ref: WorkspaceRef,
) -> None:
    try:
        await store.block_access(ref)
        await store.purge(ref)
    except Exception:
        return


def _scope(
    plan: ResearchPlan,
    source_discovery: SourceDiscoveryMode,
) -> AppliedScope:
    stop = plan.stop_conditions
    return AppliedScope(
        as_of_date=plan.as_of_date,
        jurisdiction=plan.jurisdiction,
        profile=plan.profile,
        source_discovery=source_discovery,
        source_tracks=[track.id for track in plan.tracks],
        completion_criteria=list(plan.completion_criteria),
        stop_conditions={
            "max_sources": stop.max_sources,
            "max_bytes": stop.max_bytes,
            "timeout_seconds": stop.timeout_seconds,
            "require_official_primary": stop.require_official_primary,
        },
    )


def _render_markdown(draft: ResearchDraft, plan: ResearchPlan) -> str:
    lines = [
        "# Public Research Result",
        "",
        f"- 기준일: {plan.as_of_date.isoformat()}",
        f"- 관할: {plan.jurisdiction}",
        f"- Profile: {plan.profile}",
        f"- Source discovery: {draft.source_discovery}",
        "",
        _markdown_text(draft.summary),
        "",
        "## Findings",
    ]
    for finding in draft.findings:
        citations = ", ".join(_markdown_text(value) for value in finding.citation_ids) or "none"
        lines.append(
            f"- [{finding.kind}] {_markdown_text(finding.claim)} "
            f"(citations: {citations}; confidence: {finding.confidence})"
        )
    lines.extend(("", "## Citations"))
    if not draft.citations:
        lines.append("- none")
    for citation in draft.citations:
        lines.extend(
            (
                (
                    f"- [{_markdown_text(citation.id)}] "
                    f"{_markdown_text(citation.title)} — "
                    f"{_markdown_text(citation.publisher)}"
                ),
                f"  - URL: {citation.url}",
                f"  - Track: {_markdown_text(citation.track_id)}",
                f"  - Tier: {_markdown_text(citation.source_tier)}",
                f"  - Retrieved: {citation.retrieved_at.isoformat()}",
                f"  - Locator: {_markdown_text(citation.locator)}",
                f"  - Snapshot SHA-256: {citation.document_sha256}",
                f"  - Excerpt: {_markdown_text(citation.excerpt)}",
                f"  - Evidence score: {citation.score.overall:.4f}",
            )
        )
        for name, component in _score_components(citation.score):
            lines.append(
                f"    - {name}: {component.value:.4f} — {_markdown_text(component.explanation)}"
            )
    lines.extend(("", "## Gaps"))
    lines.extend(
        (f"- {_markdown_text(gap)}" for gap in draft.gaps),
    )
    if not draft.gaps:
        lines.append("- none")
    lines.extend(("", "## Conflicts"))
    lines.extend(
        (f"- {_markdown_text(conflict)}" for conflict in draft.conflicts),
    )
    if not draft.conflicts:
        lines.append("- none")
    lines.extend(("", "## Failures"))
    for failure in draft.failures:
        lines.append(
            f"- [{_markdown_text(failure.code)}] "
            f"{_markdown_text(failure.message)} "
            f"(retryable: {str(failure.retryable).lower()})"
        )
    if not draft.failures:
        lines.append("- none")
    return "\n".join(lines)


def _score_components(
    score: EvidenceScoreOutput,
) -> tuple[tuple[str, ScoreComponentOutput], ...]:
    return (
        ("authority", score.authority),
        ("primary_source", score.primary_source),
        ("direct_relevance", score.direct_relevance),
        ("original_snapshot", score.original_snapshot),
        ("specificity", score.specificity),
        ("freshness", score.freshness),
        ("independence", score.independence),
    )


def _markdown_text(value: str) -> str:
    normalized = " ".join(value.split())
    escaped = html.escape(normalized, quote=False)
    for character in ("\\", "`", "*", "_", "[", "]"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped
