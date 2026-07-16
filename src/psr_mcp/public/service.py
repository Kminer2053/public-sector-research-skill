"""Quick public research lifecycle with mandatory ephemeral purge."""

from __future__ import annotations

import asyncio
import html
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from threading import Lock
from typing import Literal, Protocol

from pydantic import HttpUrl

from psr_mcp.application.ports import Clock, IdGenerator
from psr_mcp.ephemeral.ports import ArtifactKind, EphemeralWorkspaceStore, WorkspaceRef
from psr_mcp.planner.government import GovernmentPlanner
from psr_mcp.planner.models import ResearchPlan
from psr_mcp.public.admission import PauseSignal
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
    PUBLIC_LIMIT_REACHED = "PUBLIC_LIMIT_REACHED"
    PUBLIC_DAILY_BUDGET_EXHAUSTED = "PUBLIC_DAILY_BUDGET_EXHAUSTED"
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
        max_active_quick: int,
        daily_quick_budget: int,
        pause_signal: PauseSignal,
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
        self._max_active_quick = max_active_quick
        self._active_quick = 0
        self._active_quick_lock = Lock()
        self._daily_quick_budget = daily_quick_budget
        self._daily_budget_day: date | None = None
        self._daily_quick_used = 0
        self._daily_budget_lock = Lock()
        self._pause_signal = pause_signal
        self._kill_switch = kill_switch

    @property
    def available(self) -> bool:
        return self._backend.available and not self.paused and not self._daily_budget_exhausted()

    @property
    def paused(self) -> bool:
        return self._kill_switch or self._pause_signal.paused

    async def quick(
        self,
        *,
        question: str,
        as_of_date: date | None,
        jurisdiction: str,
        profile: str,
    ) -> QuickResearchOutput:
        if self.paused:
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
        if not self._try_acquire_quick_slot():
            raise PublicResearchError(
                PublicErrorCode.PUBLIC_LIMIT_REACHED,
                "public quick research concurrency limit reached",
                retryable=True,
            )
        try:
            return await self._run_quick(
                question=question,
                as_of_date=as_of_date,
                jurisdiction=jurisdiction,
            )
        finally:
            self._release_quick_slot()

    async def _run_quick(
        self,
        *,
        question: str,
        as_of_date: date | None,
        jurisdiction: str,
    ) -> QuickResearchOutput:
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
        if not self._try_consume_daily_budget():
            raise PublicResearchError(
                PublicErrorCode.PUBLIC_DAILY_BUDGET_EXHAUSTED,
                "public daily quick budget is exhausted until the next UTC day",
                retryable=True,
            )

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

    def _try_acquire_quick_slot(self) -> bool:
        with self._active_quick_lock:
            if self._active_quick >= self._max_active_quick:
                return False
            self._active_quick += 1
            return True

    def _release_quick_slot(self) -> None:
        with self._active_quick_lock:
            if self._active_quick <= 0:
                raise RuntimeError("public quick concurrency counter underflow")
            self._active_quick -= 1

    def _try_consume_daily_budget(self) -> bool:
        if self._daily_quick_budget == 0:
            return True
        with self._daily_budget_lock:
            self._reset_daily_budget_if_needed()
            if self._daily_quick_used >= self._daily_quick_budget:
                return False
            self._daily_quick_used += 1
            return True

    def _daily_budget_exhausted(self) -> bool:
        if self._daily_quick_budget == 0:
            return False
        with self._daily_budget_lock:
            self._reset_daily_budget_if_needed()
            return self._daily_quick_used >= self._daily_quick_budget

    def _reset_daily_budget_if_needed(self) -> None:
        today = self._clock.now().date()
        if self._daily_budget_day != today:
            self._daily_budget_day = today
            self._daily_quick_used = 0


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
        "# 공공분야 공식자료 조사 결과",
        "",
        f"- 기준일: {plan.as_of_date.isoformat()}",
        f"- 관할: {plan.jurisdiction}",
        f"- 조사 프로필: {plan.profile}",
        f"- 출처 발견 방식: {draft.source_discovery}",
        "",
        "## 조사 요약",
        "",
        _markdown_text(draft.summary),
    ]
    _append_findings(
        lines,
        draft,
        kind="RECOMMENDATION",
        title="조달 원칙 검토안",
        empty_message="근거 anchor가 충족된 검토안이 없습니다.",
    )
    _append_findings(
        lines,
        draft,
        kind="FACT",
        title="확인한 사실",
        empty_message="인용 가능한 원문 사실이 없습니다.",
    )
    _append_findings(
        lines,
        draft,
        kind="INFERENCE",
        title="추론·해석",
        empty_message="별도로 표시할 추론·해석이 없습니다.",
    )
    lines.extend(("", "## 근거"))
    if not draft.citations:
        lines.append("- 없음")
    for citation in draft.citations:
        lines.extend(
            (
                (
                    f"- [{_markdown_text(citation.id)}] "
                    f"{_markdown_text(citation.title)} — "
                    f"{_markdown_text(citation.publisher)}"
                ),
                f"  - URL: {citation.url}",
                f"  - 조사 트랙: {_markdown_text(citation.track_id)}",
                f"  - 출처 등급: {_markdown_text(citation.source_tier)}",
                f"  - 수집 시각: {citation.retrieved_at.isoformat()}",
                f"  - 원문 위치: {_markdown_text(citation.locator)}",
                f"  - 스냅샷 SHA-256: {citation.document_sha256}",
                f"  - 원문 구간: {_markdown_text(citation.excerpt)}",
                f"  - 근거 점수: {citation.score.overall:.4f}",
            )
        )
        for name, component in _score_components(citation.score):
            lines.append(
                f"    - {_SCORE_LABELS[name]}: {component.value:.4f} — "
                f"{_markdown_text(component.explanation)}"
            )
    lines.extend(("", "## 확인 필요사항"))
    lines.extend(
        (f"- {_markdown_text(gap)}" for gap in draft.gaps),
    )
    if not draft.gaps:
        lines.append("- 없음")
    lines.extend(("", "## 상충 정보"))
    lines.extend(
        (f"- {_markdown_text(conflict)}" for conflict in draft.conflicts),
    )
    if not draft.conflicts:
        lines.append("- 없음")
    lines.extend(("", "## 수집·처리 실패"))
    for failure in draft.failures:
        lines.append(
            f"- [{_markdown_text(failure.code)}] "
            f"{_markdown_text(failure.message)} "
            f"(재시도 가능: {str(failure.retryable).lower()})"
        )
    if not draft.failures:
        lines.append("- 없음")
    return "\n".join(lines)


def _append_findings(
    lines: list[str],
    draft: ResearchDraft,
    *,
    kind: Literal["FACT", "INFERENCE", "RECOMMENDATION"],
    title: str,
    empty_message: str,
) -> None:
    lines.extend(("", f"## {title}"))
    selected = tuple(finding for finding in draft.findings if finding.kind == kind)
    if not selected:
        lines.append(f"- {empty_message}")
        return
    for finding in selected:
        citations = ", ".join(_markdown_text(value) for value in finding.citation_ids) or "없음"
        lines.extend(
            (
                f"- {_markdown_text(finding.claim)}",
                f"  - 근거 ID: {citations}",
                f"  - 신뢰도: {finding.confidence}",
            )
        )


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


_SCORE_LABELS = {
    "authority": "출처 권위성",
    "primary_source": "1차 자료성",
    "direct_relevance": "직접 관련성",
    "original_snapshot": "원문 확보",
    "specificity": "구체성",
    "freshness": "최신성",
    "independence": "독립성",
}


def _markdown_text(value: str) -> str:
    normalized = " ".join(value.split())
    escaped = html.escape(normalized, quote=False)
    for character in ("\\", "`", "*", "_", "[", "]"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped
