from __future__ import annotations

import asyncio
from datetime import timedelta

import psycopg
import pytest
from psycopg import errors

from psr_mcp.application.projects import ProjectService
from psr_mcp.application.research_runs import ResearchRunService
from psr_mcp.application.workers import WorkerService
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.auth.policy import AuthorizationPolicy
from psr_mcp.domain.audit import AuditEvent, AuditOutcome
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.identity import ActorType
from psr_mcp.domain.research import Job, JobState, ResearchRun, RunStatus
from psr_mcp.storage.postgres import PostgresStore
from psr_mcp.storage.postgres.store import current_tenant_values

from .conftest import (
    ORG_A,
    ORG_B,
    PLAN_A1,
    PROJECT_A1,
    PROJECT_A2,
    PROJECT_B1,
    USER_A,
    FixedClock,
    PostgresUrls,
    UuidSequence,
)

pytestmark = pytest.mark.postgres


@pytest.mark.anyio
async def test_rls_default_deny_and_pool_reuse(
    postgres_store: PostgresStore,
    pg_project_service: ProjectService,
    pg_auth_a: AuthorizationContext,
    pg_auth_b: AuthorizationContext,
) -> None:
    async with postgres_store.pool.connection() as connection:
        cursor = await connection.execute("SELECT count(*) AS count FROM projects")
        row = await cursor.fetchone()
        assert row is not None and row["count"] == 0

    tenant_a = await pg_project_service.list_projects(pg_auth_a)
    assert [project.id for project in tenant_a.items] == [PROJECT_A1, PROJECT_A2]
    assert await current_tenant_values(postgres_store, samples=3) == [None, None, None]

    tenant_b = await pg_project_service.list_projects(pg_auth_b)
    assert [project.id for project in tenant_b.items] == [PROJECT_B1]
    assert await current_tenant_values(postgres_store, samples=3) == [None, None, None]


@pytest.mark.anyio
async def test_unit_of_work_rejects_tenant_switch(postgres_store: PostgresStore) -> None:
    async with postgres_store.unit_of_work() as unit_of_work:
        assert await unit_of_work.projects.get(ORG_A, PROJECT_A1) is not None
        with pytest.raises(DomainError) as caught:
            await unit_of_work.projects.get(ORG_B, PROJECT_B1)
    assert caught.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN


def test_runtime_role_and_rls_flags(seeded_postgres: PostgresUrls) -> None:
    with psycopg.connect(seeded_postgres.runtime) as connection:
        role = connection.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert role == (False, False)
        flags = connection.execute(
            """
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relname IN (
                'organizations', 'memberships', 'external_identities',
                'projects', 'membership_projects',
                'research_plans', 'research_runs', 'jobs', 'audit_events'
            )
            ORDER BY relname
            """
        ).fetchall()
    assert len(flags) == 9
    assert all(row[1:] == (True, True) for row in flags)


def test_cross_tenant_composite_foreign_key_is_rejected(
    seeded_postgres: PostgresUrls,
) -> None:
    with psycopg.connect(seeded_postgres.owner) as connection:
        connection.execute("SELECT set_config('app.organization_id', %s, true)", (ORG_A,))
        with pytest.raises(errors.ForeignKeyViolation):
            connection.execute(
                """
                INSERT INTO membership_projects (organization_id, user_id, project_id)
                VALUES (%s, %s, %s)
                """,
                (ORG_A, USER_A, PROJECT_B1),
            )


@pytest.mark.anyio
async def test_run_job_audit_idempotency_and_persistence(
    postgres_store: PostgresStore,
    pg_run_service: ResearchRunService,
    pg_auth_a: AuthorizationContext,
    seeded_postgres: PostgresUrls,
) -> None:
    first = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-request-0001",
    )
    replay = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-request-0001",
    )
    assert replay.run.id == first.run.id
    assert replay.replayed is True

    async with postgres_store.unit_of_work() as unit_of_work:
        stored = await unit_of_work.runs.get(ORG_A, first.run.id)
        job = await unit_of_work.jobs.get_by_run(ORG_A, first.run.id)
    assert stored is not None and stored.status is RunStatus.QUEUED
    assert job is not None and job.state is JobState.QUEUED

    async with postgres_store.pool.connection() as connection:
        await connection.execute("SELECT set_config('app.organization_id', %s, true)", (ORG_A,))
        cursor = await connection.execute(
            "SELECT outcome FROM audit_events ORDER BY occurred_at, id"
        )
        outcomes = [row["outcome"] async for row in cursor]
    assert outcomes == ["SUCCEEDED", "IDEMPOTENT_REPLAY"]
    async with await psycopg.AsyncConnection.connect(seeded_postgres.owner) as owner:
        await owner.execute("SELECT set_config('app.organization_id', %s, true)", (ORG_A,))
        with pytest.raises(errors.RaiseException, match="append-only"):
            await owner.execute("UPDATE audit_events SET outcome = 'FAILED'")


@pytest.mark.anyio
async def test_concurrent_idempotency_creates_one_run(
    postgres_store: PostgresStore,
    pg_run_service: ResearchRunService,
    pg_auth_a: AuthorizationContext,
) -> None:
    async def start() -> str:
        result = await pg_run_service.start(
            pg_auth_a,
            approved_plan_id=PLAN_A1,
            idempotency_key="postgres-race-0001",
        )
        return result.run.id

    results = await asyncio.gather(start(), start(), return_exceptions=True)
    assert all(isinstance(result, str) for result in results)
    assert len(set(results)) == 1

    async with postgres_store.pool.connection() as connection:
        await connection.execute("SELECT set_config('app.organization_id', %s, true)", (ORG_A,))
        cursor = await connection.execute(
            "SELECT count(*) AS count FROM research_runs WHERE idempotency_key = %s",
            ("postgres-race-0001",),
        )
        row = await cursor.fetchone()
    assert row is not None and row["count"] == 1


@pytest.mark.anyio
async def test_skip_locked_allows_only_one_worker_claim(
    pg_run_service: ResearchRunService,
    pg_worker_service: WorkerService,
    pg_auth_a: AuthorizationContext,
) -> None:
    started = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-worker-0001",
    )
    claims = await asyncio.gather(
        pg_worker_service.claim_next(ORG_A, worker_id="worker-1"),
        pg_worker_service.claim_next(ORG_A, worker_id="worker-2"),
    )
    claimed = [claim for claim in claims if claim is not None]
    assert len(claimed) == 1
    assert claimed[0].run.id == started.run.id
    assert claimed[0].run.status is RunStatus.RUNNING


@pytest.mark.anyio
async def test_optimistic_cancel_race_has_one_winner(
    pg_run_service: ResearchRunService,
    pg_auth_a: AuthorizationContext,
) -> None:
    started = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-cancel-0001",
    )

    async def cancel(reason: str) -> RunStatus:
        result = await pg_run_service.cancel(
            pg_auth_a,
            run_id=started.run.id,
            reason=reason,
            expected_version=started.run.version,
        )
        return result.run.status

    results = await asyncio.gather(
        cancel("첫 번째 담당자가 실행 취소를 요청합니다."),
        cancel("두 번째 담당자가 실행 취소를 요청합니다."),
        return_exceptions=True,
    )
    assert results.count(RunStatus.CANCELLED) == 1
    assert (
        sum(
            isinstance(result, DomainError) and result.code is ErrorCode.VERSION_CONFLICT
            for result in results
        )
        == 1
    )


@pytest.mark.anyio
async def test_audit_insert_failure_rolls_back_run_and_job(
    postgres_store: PostgresStore,
    pg_clock: FixedClock,
) -> None:
    run_id = "00000000-0000-0000-0000-00000000d001"
    job_id = "00000000-0000-0000-0000-00000000d002"
    audit_id = "00000000-0000-0000-0000-00000000d003"
    run = ResearchRun(
        id=run_id,
        organization_id=ORG_A,
        project_id=PROJECT_A1,
        plan_id=PLAN_A1,
        plan_version=1,
        initiated_by=USER_A,
        status=RunStatus.QUEUED,
        version=1,
        idempotency_key="postgres-rollback-0001",
        request_fingerprint="a" * 64,
        created_at=pg_clock.now(),
        updated_at=pg_clock.now(),
    )
    job = Job(
        id=job_id,
        organization_id=ORG_A,
        project_id=PROJECT_A1,
        run_id=run_id,
        state=JobState.QUEUED,
        available_at=pg_clock.now(),
        created_at=pg_clock.now(),
        updated_at=pg_clock.now(),
    )
    event = AuditEvent(
        id=audit_id,
        organization_id=ORG_A,
        project_id=PROJECT_A1,
        occurred_at=pg_clock.now(),
        actor_subject_id=USER_A,
        actor_type=ActorType.HUMAN,
        operation="research.run.start",
        target_type="ResearchRun",
        target_id=run_id,
        outcome=AuditOutcome.SUCCEEDED,
        operation_id="postgres-rollback-operation",
    )

    with pytest.raises(DomainError) as caught:
        async with postgres_store.unit_of_work() as unit_of_work:
            await unit_of_work.runs.add(run)
            await unit_of_work.jobs.add(job)
            await unit_of_work.audit.add(event)
            await unit_of_work.audit.add(event)
            await unit_of_work.commit()
    assert caught.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    async with postgres_store.unit_of_work() as unit_of_work:
        assert await unit_of_work.runs.get(ORG_A, run_id) is None
        assert await unit_of_work.jobs.get_by_run(ORG_A, run_id) is None


@pytest.mark.anyio
async def test_worker_lease_survives_pool_restart_and_is_reclaimed(
    seeded_postgres: PostgresUrls,
    postgres_store: PostgresStore,
    pg_run_service: ResearchRunService,
    pg_worker_service: WorkerService,
    pg_auth_a: AuthorizationContext,
    pg_clock: FixedClock,
    pg_ids: UuidSequence,
) -> None:
    started = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-recovery-0001",
    )
    first = await pg_worker_service.claim_next(
        ORG_A, worker_id="worker-before-restart", lease_seconds=5
    )
    assert first is not None and first.job.attempts == 1
    pg_clock.value += timedelta(seconds=6)

    async with PostgresStore(seeded_postgres.runtime, min_size=1, max_size=2) as restarted:
        restarted_worker = WorkerService(restarted.unit_of_work, pg_clock, pg_ids)
        reclaimed = await restarted_worker.claim_next(
            ORG_A, worker_id="worker-after-restart", lease_seconds=30
        )
        assert reclaimed is not None
        assert reclaimed.run.id == started.run.id
        assert reclaimed.job.attempts == 2

    async with postgres_store.unit_of_work() as unit_of_work:
        persisted = await unit_of_work.jobs.get_by_run(ORG_A, started.run.id)
    assert persisted is not None and persisted.attempts == 2


@pytest.mark.anyio
async def test_response_loss_retry_returns_same_run_from_new_pool(
    seeded_postgres: PostgresUrls,
    pg_run_service: ResearchRunService,
    pg_auth_a: AuthorizationContext,
    pg_clock: FixedClock,
) -> None:
    first = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-response-loss-0001",
    )
    ids = UuidSequence(30_000)
    async with PostgresStore(seeded_postgres.runtime, min_size=1, max_size=2) as restarted:
        retried_service = ResearchRunService(
            restarted.unit_of_work,
            AuthorizationPolicy(),
            pg_clock,
            ids,
        )
        retried = await retried_service.start(
            pg_auth_a,
            approved_plan_id=PLAN_A1,
            idempotency_key="postgres-response-loss-0001",
        )
    assert retried.replayed is True
    assert retried.run.id == first.run.id


@pytest.mark.anyio
async def test_backend_loss_before_commit_leaves_no_run_and_pool_recovers(
    seeded_postgres: PostgresUrls,
    postgres_store: PostgresStore,
    pg_clock: FixedClock,
) -> None:
    run_id = "00000000-0000-0000-0000-00000000e001"
    run = ResearchRun(
        id=run_id,
        organization_id=ORG_A,
        project_id=PROJECT_A1,
        plan_id=PLAN_A1,
        plan_version=1,
        initiated_by=USER_A,
        status=RunStatus.QUEUED,
        version=1,
        idempotency_key="postgres-db-loss-0001",
        request_fingerprint="b" * 64,
        created_at=pg_clock.now(),
        updated_at=pg_clock.now(),
    )

    with pytest.raises(psycopg.OperationalError):
        async with postgres_store.unit_of_work() as unit_of_work:
            await unit_of_work.runs.add(run)
            backend_pid = await unit_of_work.backend_pid()
            await asyncio.to_thread(_terminate_backend, seeded_postgres.admin, backend_pid)
            await unit_of_work.commit()

    async with postgres_store.unit_of_work() as unit_of_work:
        assert await unit_of_work.runs.get(ORG_A, run_id) is None


@pytest.mark.anyio
async def test_queue_claim_order_is_deterministic(
    pg_run_service: ResearchRunService,
    pg_worker_service: WorkerService,
    pg_auth_a: AuthorizationContext,
) -> None:
    first = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-fairness-0001",
    )
    await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-fairness-0002",
    )
    claimed = await pg_worker_service.claim_next(ORG_A, worker_id="fair-worker")
    assert claimed is not None
    assert claimed.run.id == first.run.id


@pytest.mark.anyio
async def test_retry_exhaustion_persists_failed_run(
    pg_run_service: ResearchRunService,
    pg_worker_service: WorkerService,
    pg_auth_a: AuthorizationContext,
    pg_clock: FixedClock,
) -> None:
    started = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-exhaustion-0001",
    )
    for worker_id in ("retry-worker-1", "retry-worker-2", "retry-worker-3"):
        claim = await pg_worker_service.claim_next(ORG_A, worker_id=worker_id, lease_seconds=5)
        assert claim is not None
        pg_clock.value += timedelta(seconds=6)

    assert await pg_worker_service.claim_next(ORG_A, worker_id="retry-worker-4") is None
    status = await pg_run_service.status(pg_auth_a, started.run.id)
    assert status.run.status is RunStatus.FAILED
    assert status.run.failure_code == "RETRY_EXHAUSTED"


@pytest.mark.anyio
async def test_cancel_complete_race_never_splits_run_and_job_state(
    postgres_store: PostgresStore,
    pg_run_service: ResearchRunService,
    pg_worker_service: WorkerService,
    pg_auth_a: AuthorizationContext,
) -> None:
    started = await pg_run_service.start(
        pg_auth_a,
        approved_plan_id=PLAN_A1,
        idempotency_key="postgres-completion-race-0001",
    )
    claimed = await pg_worker_service.claim_next(ORG_A, worker_id="completion-worker")
    assert claimed is not None

    results = await asyncio.gather(
        pg_run_service.cancel(
            pg_auth_a,
            run_id=started.run.id,
            reason="완료와 동시에 담당자가 실행 취소를 요청합니다.",
            expected_version=claimed.run.version,
        ),
        pg_worker_service.complete(
            ORG_A,
            run_id=started.run.id,
            worker_id="completion-worker",
            outcome=JobState.SUCCEEDED,
        ),
        return_exceptions=True,
    )
    assert not all(isinstance(result, BaseException) for result in results)

    async with postgres_store.unit_of_work() as unit_of_work:
        run = await unit_of_work.runs.get(ORG_A, started.run.id)
        job = await unit_of_work.jobs.get_by_run(ORG_A, started.run.id)
    assert run is not None and job is not None
    assert run.status in {RunStatus.SUCCEEDED, RunStatus.CANCELLED}
    assert job.state.value == run.status.value


def _terminate_backend(admin_url: str, backend_pid: int) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        row = connection.execute("SELECT pg_terminate_backend(%s)", (backend_pid,)).fetchone()
    assert row == (True,)
