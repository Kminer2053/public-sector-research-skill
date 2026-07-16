from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest

from psr_mcp.application.ports import Clock, IdGenerator
from psr_mcp.ephemeral.filesystem import (
    FilesystemEphemeralWorkspaceStore,
    WorkspaceAccessBlocked,
)
from psr_mcp.ephemeral.ports import (
    ArtifactKind,
    EphemeralWorkspaceStore,
    PurgeResult,
    WorkspaceRef,
)
from psr_mcp.planner import GovernmentPlanner
from psr_mcp.planner.models import ResearchPlan
from psr_mcp.public.service import (
    FixtureResearchBackend,
    PublicErrorCode,
    PublicQuickResearchService,
    PublicResearchError,
    ResearchBackend,
    ResearchDraft,
    _markdown_text,
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 16, tzinfo=UTC)


class FixedIds:
    def new(self) -> str:
        return "operation-test"


class ExplodingBackend:
    @property
    def available(self) -> bool:
        return True

    async def research(self, plan: ResearchPlan) -> ResearchDraft:
        del plan
        raise RuntimeError("source adapter exploded")


class SlowBackend:
    @property
    def available(self) -> bool:
        return True

    async def research(self, plan: ResearchPlan) -> ResearchDraft:
        del plan
        await asyncio.sleep(1)
        raise AssertionError("timeout should cancel the backend")


class StoreWrapper:
    def __init__(
        self,
        inner: FilesystemEphemeralWorkspaceStore,
        *,
        purge_failures: int = 0,
        inconclusive_purges: int = 0,
    ) -> None:
        self.inner = inner
        self.purge_failures = purge_failures
        self.inconclusive_purges = inconclusive_purges
        self.created: list[WorkspaceRef] = []
        self.purge_calls = 0

    async def create(
        self,
        *,
        expires_at: datetime,
        hard_expires_at: datetime,
    ) -> WorkspaceRef:
        ref = await self.inner.create(
            expires_at=expires_at,
            hard_expires_at=hard_expires_at,
        )
        self.created.append(ref)
        return ref

    async def write_bytes(
        self,
        ref: WorkspaceRef,
        kind: ArtifactKind,
        data: bytes,
    ) -> None:
        await self.inner.write_bytes(ref, kind, data)

    async def read_bytes(self, ref: WorkspaceRef, kind: ArtifactKind) -> bytes:
        return await self.inner.read_bytes(ref, kind)

    async def block_access(self, ref: WorkspaceRef) -> None:
        await self.inner.block_access(ref)

    async def purge(self, ref: WorkspaceRef) -> PurgeResult:
        self.purge_calls += 1
        if self.purge_calls <= self.purge_failures:
            raise OSError("simulated deletion failure")
        if self.purge_calls <= self.purge_failures + self.inconclusive_purges:
            return PurgeResult(workspace_id=ref.workspace_id, deleted=False)
        return await self.inner.purge(ref)

    async def purge_expired(self) -> list[PurgeResult]:
        return await self.inner.purge_expired()


def _service(
    store: EphemeralWorkspaceStore,
    backend: ResearchBackend,
    *,
    timeout_seconds: float = 20,
    kill_switch: bool = False,
) -> PublicQuickResearchService:
    return PublicQuickResearchService(
        store=store,
        planner=GovernmentPlanner(),
        backend=backend,
        clock=cast(Clock, FixedClock()),
        ids=cast(IdGenerator, FixedIds()),
        run_ttl_seconds=3_600,
        orphan_max_age_seconds=7_200,
        max_sources=12,
        max_bytes=31_457_280,
        timeout_seconds=timeout_seconds,
        kill_switch=kill_switch,
    )


async def _store(tmp_path: Path) -> FilesystemEphemeralWorkspaceStore:
    store = FilesystemEphemeralWorkspaceStore(
        tmp_path / "ephemeral",
        now=FixedClock().now,
        create_root=True,
    )
    await store.open()
    return store


@pytest.mark.anyio
async def test_invalid_scope_and_kill_switch_do_not_create_workspace(tmp_path: Path) -> None:
    store = StoreWrapper(await _store(tmp_path))

    with pytest.raises(PublicResearchError) as invalid:
        await _service(store, ExplodingBackend()).quick(
            question="공공기관 정책을 공식자료 중심으로 조사해줘",
            as_of_date=date(2026, 7, 16),
            jurisdiction="US",
            profile="government-v0",
        )
    assert invalid.value.code is PublicErrorCode.INPUT_INVALID

    with pytest.raises(PublicResearchError) as invalid_profile:
        await _service(store, ExplodingBackend()).quick(
            question="공공기관 정책을 공식자료 중심으로 조사해줘",
            as_of_date=None,
            jurisdiction="KR",
            profile="unsupported",
        )
    assert invalid_profile.value.code is PublicErrorCode.INPUT_INVALID

    with pytest.raises(PublicResearchError) as paused:
        await _service(store, ExplodingBackend(), kill_switch=True).quick(
            question="공공기관 정책을 공식자료 중심으로 조사해줘",
            as_of_date=None,
            jurisdiction="KR",
            profile="government-v0",
        )
    assert paused.value.code is PublicErrorCode.PUBLIC_SERVICE_PAUSED
    assert store.created == []


@pytest.mark.anyio
async def test_timeout_and_unexpected_backend_failure_purge_workspace(tmp_path: Path) -> None:
    for backend, expected in (
        (cast(ResearchBackend, SlowBackend()), PublicErrorCode.BUDGET_EXHAUSTED),
        (cast(ResearchBackend, ExplodingBackend()), PublicErrorCode.INTERNAL_ERROR),
    ):
        store = StoreWrapper(await _store(tmp_path))
        with pytest.raises(PublicResearchError) as error:
            await _service(store, backend, timeout_seconds=0.001).quick(
                question="공공기관 정책을 공식자료 중심으로 조사해줘",
                as_of_date=None,
                jurisdiction="KR",
                profile="government-v0",
            )
        assert error.value.code is expected
        assert list(store.inner.root.iterdir()) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "purge_failures, inconclusive_purges",
    [(1, 0), (0, 1)],
)
async def test_purge_problem_returns_typed_error_then_finally_retries(
    tmp_path: Path,
    purge_failures: int,
    inconclusive_purges: int,
) -> None:
    store = StoreWrapper(
        await _store(tmp_path),
        purge_failures=purge_failures,
        inconclusive_purges=inconclusive_purges,
    )
    with pytest.raises(PublicResearchError) as error:
        await _service(
            store,
            FixtureResearchBackend(cast(Clock, FixedClock())),
        ).quick(
            question="공공기관 정책을 공식자료 중심으로 조사해줘",
            as_of_date=None,
            jurisdiction="KR",
            profile="government-v0",
        )

    assert error.value.code is PublicErrorCode.PURGE_PENDING
    assert error.value.retryable is True
    assert store.purge_calls == 2
    assert list(store.inner.root.iterdir()) == []


@pytest.mark.anyio
async def test_repeated_purge_failure_leaves_content_inaccessible_for_sweeper(
    tmp_path: Path,
) -> None:
    store = StoreWrapper(await _store(tmp_path), purge_failures=2)
    with pytest.raises(PublicResearchError) as error:
        await _service(
            store,
            FixtureResearchBackend(cast(Clock, FixedClock())),
        ).quick(
            question="공공기관 정책을 공식자료 중심으로 조사해줘",
            as_of_date=None,
            jurisdiction="KR",
            profile="government-v0",
        )

    assert error.value.code is PublicErrorCode.PURGE_PENDING
    ref = store.created[0]
    with pytest.raises(WorkspaceAccessBlocked):
        await store.read_bytes(ref, ArtifactKind.RESULT)


@pytest.mark.anyio
async def test_markdown_matches_structured_citations_and_escapes_untrusted_text(
    tmp_path: Path,
) -> None:
    store = await _store(tmp_path)
    output = await _service(
        store,
        FixtureResearchBackend(cast(Clock, FixedClock())),
    ).quick(
        question="공공기관 정책을 공식자료 중심으로 조사해줘",
        as_of_date=None,
        jurisdiction="KR",
        profile="government-v0",
    )

    citation = output.citations[0]
    assert output.markdown.startswith("# 공공분야 공식자료 조사 결과")
    assert "## 조사 요약" in output.markdown
    assert "## 조달 원칙 검토안" in output.markdown
    assert "## 확인한 사실" in output.markdown
    assert "인용 가능한 원문 사실이 없습니다." in output.markdown
    assert "## 추론·해석" in output.markdown
    assert f"[{citation.id}]" in output.markdown
    assert citation.document_sha256 in output.markdown
    assert "근거 점수: 0.0000" in output.markdown
    assert "출처 권위성: 0.0000" in output.markdown
    assert "## 상충 정보\n- 없음" in output.markdown
    assert _markdown_text("<script>*[source]`") == ("&lt;script&gt;\\*\\[source\\]\\`")
    assert list(store.root.iterdir()) == []
