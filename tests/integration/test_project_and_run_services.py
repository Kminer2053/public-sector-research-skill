from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Protocol

import pytest

from psr_mcp.application.projects import ProjectService
from psr_mcp.application.research_runs import ResearchRunService
from psr_mcp.application.workers import WorkerService
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.identity import Role
from psr_mcp.domain.projects import Project, ProjectStatus
from psr_mcp.domain.research import JobState, ResearchPlan, RunStatus
from psr_mcp.storage.memory import InMemoryStore


class MutableClock(Protocol):
    value: datetime


@pytest.mark.anyio
async def test_project_list_is_tenant_and_restriction_scoped(
    project_service: ProjectService,
    auth_a_wide: AuthorizationContext,
    auth_a_limited: AuthorizationContext,
    auth_b: AuthorizationContext,
) -> None:
    wide = await project_service.list_projects(auth_a_wide)
    limited = await project_service.list_projects(auth_a_limited)
    tenant_b = await project_service.list_projects(auth_b)

    assert [project.id for project in wide.items] == ["project-a1", "project-a2"]
    assert [project.id for project in limited.items] == ["project-a1"]
    assert [project.id for project in tenant_b.items] == ["project-b1"]

    with pytest.raises(DomainError) as restricted:
        await project_service.get_project(auth_a_limited, "project-a2")
    assert restricted.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN


@pytest.mark.anyio
async def test_project_access_requires_scope_and_role(
    project_service: ProjectService,
    auth_a_wide: AuthorizationContext,
) -> None:
    no_scope = replace(auth_a_wide, scopes=frozenset())
    with pytest.raises(DomainError) as missing_scope:
        await project_service.get_project(no_scope, "project-a1")
    assert missing_scope.value.code is ErrorCode.AUTH_SCOPE_REQUIRED

    wrong_role = replace(auth_a_wide, roles=frozenset({Role.AUDIT_VIEWER}))
    with pytest.raises(DomainError) as forbidden_role:
        await project_service.get_project(wrong_role, "project-a1")
    assert forbidden_role.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN


@pytest.mark.anyio
async def test_cross_tenant_project_id_is_opaque(
    project_service: ProjectService,
    auth_a_wide: AuthorizationContext,
) -> None:
    with pytest.raises(DomainError) as caught:
        await project_service.get_project(auth_a_wide, "project-b1")
    assert caught.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN
    assert "project-b1" not in caught.value.message


@pytest.mark.anyio
async def test_cross_tenant_run_status_is_opaque(
    run_service: ResearchRunService,
    auth_a_wide: AuthorizationContext,
    auth_b: AuthorizationContext,
) -> None:
    started = await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-cross-tenant",
    )
    with pytest.raises(DomainError) as caught:
        await run_service.status(auth_b, started.run.id)
    assert caught.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN
    assert started.run.id not in caught.value.message


@pytest.mark.anyio
async def test_project_cursor_is_signed_and_paginates(
    project_service: ProjectService,
    auth_a_wide: AuthorizationContext,
) -> None:
    first = await project_service.list_projects(auth_a_wide, limit=1)
    assert len(first.items) == 1
    assert first.next_cursor is not None

    second = await project_service.list_projects(auth_a_wide, cursor=first.next_cursor, limit=1)
    assert len(second.items) == 1
    assert first.items[0].id != second.items[0].id

    with pytest.raises(DomainError) as caught:
        await project_service.list_projects(auth_a_wide, cursor=f"{first.next_cursor}x", limit=1)
    assert caught.value.code is ErrorCode.INPUT_INVALID

    for limit in (0, 101):
        with pytest.raises(DomainError) as invalid_limit:
            await project_service.list_projects(auth_a_wide, limit=limit)
        assert invalid_limit.value.code is ErrorCode.INPUT_INVALID


@pytest.mark.anyio
async def test_run_start_is_approved_idempotent_and_audited(
    run_service: ResearchRunService,
    store: InMemoryStore,
    auth_a_wide: AuthorizationContext,
) -> None:
    first = await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-0001",
    )
    replay = await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-0001",
    )
    snapshot = await store.snapshot()

    assert first.run.status is RunStatus.QUEUED
    assert replay.run.id == first.run.id
    assert replay.replayed is True
    assert len(snapshot.runs) == 1
    assert len(snapshot.jobs) == 1
    assert [event.outcome for event in snapshot.audit_events] == ["SUCCEEDED", "IDEMPOTENT_REPLAY"]


@pytest.mark.anyio
async def test_draft_plan_cannot_start(
    run_service: ResearchRunService,
    auth_a_wide: AuthorizationContext,
) -> None:
    with pytest.raises(DomainError) as caught:
        await run_service.start(
            auth_a_wide,
            approved_plan_id="plan-draft-a1",
            idempotency_key="request-0002",
        )
    assert caught.value.code is ErrorCode.PLAN_NOT_APPROVED


@pytest.mark.anyio
async def test_archived_project_cannot_start(
    run_service: ResearchRunService,
    store: InMemoryStore,
    auth_a_wide: AuthorizationContext,
    project_a1: Project,
) -> None:
    await store.seed(projects=[replace(project_a1, status=ProjectStatus.ARCHIVED)])
    with pytest.raises(DomainError) as caught:
        await run_service.start(
            auth_a_wide,
            approved_plan_id="plan-approved-a1",
            idempotency_key="request-archived-project",
        )
    assert caught.value.code is ErrorCode.INVALID_STATE


@pytest.mark.anyio
async def test_same_key_with_different_plan_is_conflict(
    run_service: ResearchRunService,
    store: InMemoryStore,
    auth_a_wide: AuthorizationContext,
    approved_plan: ResearchPlan,
) -> None:
    await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-0003",
    )
    different = type(approved_plan)(
        id="plan-approved-a1-v2",
        organization_id=approved_plan.organization_id,
        project_id=approved_plan.project_id,
        version=2,
        question=approved_plan.question,
        status=approved_plan.status,
        approved_by=approved_plan.approved_by,
        approved_at=approved_plan.approved_at,
    )
    await store.seed(plans=[different])

    with pytest.raises(DomainError) as caught:
        await run_service.start(
            auth_a_wide,
            approved_plan_id=different.id,
            idempotency_key="request-0003",
        )
    assert caught.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


@pytest.mark.anyio
async def test_cancel_requires_current_version(
    run_service: ResearchRunService,
    auth_a_wide: AuthorizationContext,
) -> None:
    started = await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-0004",
    )
    with pytest.raises(DomainError) as caught:
        await run_service.cancel(
            auth_a_wide,
            run_id=started.run.id,
            reason="사용자 요청에 따라 조사 실행을 취소합니다.",
            expected_version=99,
        )
    assert caught.value.code is ErrorCode.VERSION_CONFLICT

    cancelled = await run_service.cancel(
        auth_a_wide,
        run_id=started.run.id,
        reason="사용자 요청에 따라 조사 실행을 취소합니다.",
        expected_version=1,
    )
    assert cancelled.run.status is RunStatus.CANCELLED
    assert cancelled.cancellation_requested is False

    with pytest.raises(DomainError) as terminal:
        await run_service.cancel(
            auth_a_wide,
            run_id=started.run.id,
            reason="이미 종료된 실행을 다시 취소할 수 없습니다.",
            expected_version=cancelled.run.version,
        )
    assert terminal.value.code is ErrorCode.INVALID_STATE


@pytest.mark.anyio
async def test_worker_claim_heartbeat_complete_and_recovery(
    run_service: ResearchRunService,
    worker_service: WorkerService,
    clock: MutableClock,
    auth_a_wide: AuthorizationContext,
) -> None:
    started = await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-0005",
    )
    first_claim = await worker_service.claim_next("org-a", worker_id="worker-1", lease_seconds=30)
    assert first_claim is not None
    assert first_claim.run.status is RunStatus.RUNNING

    heartbeat = await worker_service.heartbeat(
        "org-a", run_id=started.run.id, worker_id="worker-1", extend_seconds=30
    )
    assert heartbeat.lease_owner == "worker-1"
    with pytest.raises(DomainError) as wrong_worker:
        await worker_service.heartbeat(
            "org-a", run_id=started.run.id, worker_id="worker-2", extend_seconds=30
        )
    assert wrong_worker.value.code is ErrorCode.LEASE_CONFLICT

    clock.value += timedelta(seconds=31)
    recovered = await worker_service.claim_next("org-a", worker_id="worker-2", lease_seconds=30)
    assert recovered is not None
    assert recovered.run.id == started.run.id
    assert recovered.job.attempts == 2

    completed = await worker_service.complete(
        "org-a",
        run_id=started.run.id,
        worker_id="worker-2",
        outcome=JobState.SUCCEEDED,
    )
    assert completed.status is RunStatus.SUCCEEDED

    assert await worker_service.claim_next("org-a", worker_id="worker-3") is None


@pytest.mark.anyio
async def test_two_workers_cannot_claim_the_same_job(
    run_service: ResearchRunService,
    worker_service: WorkerService,
    auth_a_wide: AuthorizationContext,
) -> None:
    await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-worker-race",
    )
    claims = await asyncio.gather(
        worker_service.claim_next("org-a", worker_id="worker-1"),
        worker_service.claim_next("org-a", worker_id="worker-2"),
    )
    assert sum(claim is not None for claim in claims) == 1


@pytest.mark.anyio
async def test_running_cancel_is_observed_by_worker(
    run_service: ResearchRunService,
    worker_service: WorkerService,
    auth_a_wide: AuthorizationContext,
) -> None:
    started = await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-0006",
    )
    claimed = await worker_service.claim_next("org-a", worker_id="worker-1")
    assert claimed is not None
    cancellation = await run_service.cancel(
        auth_a_wide,
        run_id=started.run.id,
        reason="실행 중인 작업에 협력적 취소를 요청합니다.",
        expected_version=claimed.run.version,
    )
    assert cancellation.cancellation_requested is True

    completed = await worker_service.complete(
        "org-a",
        run_id=started.run.id,
        worker_id="worker-1",
        outcome=JobState.SUCCEEDED,
    )
    assert completed.status is RunStatus.CANCELLED


@pytest.mark.anyio
async def test_worker_exhausts_expired_leases(
    run_service: ResearchRunService,
    worker_service: WorkerService,
    clock: MutableClock,
    auth_a_wide: AuthorizationContext,
) -> None:
    started = await run_service.start(
        auth_a_wide,
        approved_plan_id="plan-approved-a1",
        idempotency_key="request-0007",
    )
    for worker_id in ("worker-1", "worker-2", "worker-3"):
        claimed = await worker_service.claim_next("org-a", worker_id=worker_id, lease_seconds=5)
        assert claimed is not None
        clock.value += timedelta(seconds=6)

    assert await worker_service.claim_next("org-a", worker_id="worker-4") is None
    snapshot = await run_service.status(auth_a_wide, started.run.id)
    assert snapshot.run.status is RunStatus.FAILED
    assert snapshot.run.failure_code == "RETRY_EXHAUSTED"


@pytest.mark.anyio
async def test_worker_rejects_nonterminal_completion(
    worker_service: WorkerService,
) -> None:
    with pytest.raises(DomainError) as caught:
        await worker_service.complete(
            "org-a",
            run_id="missing-run",
            worker_id="worker-1",
            outcome=JobState.RUNNING,
        )
    assert caught.value.code is ErrorCode.INPUT_INVALID


@pytest.mark.anyio
async def test_worker_missing_run_is_reported_opaquely(worker_service: WorkerService) -> None:
    with pytest.raises(DomainError) as heartbeat:
        await worker_service.heartbeat(
            "org-a",
            run_id="missing-run",
            worker_id="worker-1",
        )
    assert heartbeat.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN

    with pytest.raises(DomainError) as completion:
        await worker_service.complete(
            "org-a",
            run_id="missing-run",
            worker_id="worker-1",
            outcome=JobState.SUCCEEDED,
        )
    assert completion.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN
