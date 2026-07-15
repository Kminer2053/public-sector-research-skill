from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta

import pytest

from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.projects import Project, ProjectStatus
from psr_mcp.domain.research import (
    Job,
    JobState,
    PlanStatus,
    ResearchPlan,
    ResearchRun,
    RunStatus,
)


def make_run(now: datetime, *, status: RunStatus = RunStatus.QUEUED) -> ResearchRun:
    finished_at = (
        now
        if status in {RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.CANCELLED}
        else None
    )
    return ResearchRun(
        id="run-1",
        organization_id="org-a",
        project_id="project-a1",
        plan_id="plan-a1",
        plan_version=1,
        initiated_by="user-a",
        status=status,
        version=1,
        idempotency_key="request-0001",
        request_fingerprint="a" * 64,
        created_at=now,
        updated_at=now,
        finished_at=finished_at,
    )


def test_domain_rejects_naive_datetime() -> None:
    with pytest.raises(DomainError) as caught:
        make_run(datetime(2026, 7, 16))
    assert caught.value.code is ErrorCode.INPUT_INVALID


def test_run_state_machine_and_terminal_immutability(now: datetime) -> None:
    queued = make_run(now)
    running = queued.transition(RunStatus.RUNNING, now + timedelta(seconds=1))
    succeeded = running.transition(RunStatus.SUCCEEDED, now + timedelta(seconds=2))

    assert running.version == 2
    assert running.started_at == now + timedelta(seconds=1)
    assert succeeded.version == 3
    assert succeeded.finished_at == now + timedelta(seconds=2)
    with pytest.raises(DomainError) as caught:
        succeeded.transition(RunStatus.RUNNING, now + timedelta(seconds=3))
    assert caught.value.code is ErrorCode.INVALID_STATE


@pytest.mark.parametrize(
    "target",
    [RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.CANCELLED],
)
def test_running_run_allows_each_terminal_outcome(now: datetime, target: RunStatus) -> None:
    running = make_run(now).transition(RunStatus.RUNNING, now + timedelta(seconds=1))
    finished = running.transition(target, now + timedelta(seconds=2))

    assert finished.status is target
    assert finished.finished_at == now + timedelta(seconds=2)


def test_running_cancel_is_a_request_not_terminal(now: datetime) -> None:
    running = make_run(now).transition(RunStatus.RUNNING, now + timedelta(seconds=1))
    updated = running.request_cancellation(
        now + timedelta(seconds=2), "업무 담당자가 명시적으로 취소 요청"
    )

    assert updated.status is RunStatus.RUNNING
    assert updated.cancellation_requested_at is not None
    assert updated.version == running.version + 1


def test_job_lease_owner_and_expiry(now: datetime) -> None:
    job = Job(
        id="job-1",
        organization_id="org-a",
        project_id="project-a1",
        run_id="run-1",
        state=JobState.QUEUED,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    claimed = job.claim("worker-1", now, 30)
    heartbeat = claimed.heartbeat("worker-1", now + timedelta(seconds=5), 30)

    assert claimed.attempts == 1
    assert heartbeat.lease_expires_at == now + timedelta(seconds=35)
    with pytest.raises(DomainError) as caught:
        heartbeat.heartbeat("worker-2", now + timedelta(seconds=6), 30)
    assert caught.value.code is ErrorCode.LEASE_CONFLICT

    finished = heartbeat.finish("worker-1", now + timedelta(seconds=7), JobState.SUCCEEDED)
    assert finished.state is JobState.SUCCEEDED
    assert finished.lease_owner is None

    with pytest.raises(DomainError) as expired:
        claimed.finish("worker-1", now + timedelta(seconds=31), JobState.SUCCEEDED)
    assert expired.value.code is ErrorCode.LEASE_CONFLICT


def test_queued_cancel_is_terminal(now: datetime) -> None:
    cancelled = make_run(now).request_cancellation(
        now + timedelta(seconds=1), "대기 중인 실행을 담당자가 취소합니다."
    )
    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.finished_at is not None

    with pytest.raises(DomainError) as caught:
        cancelled.request_cancellation(
            now + timedelta(seconds=2), "완료된 취소를 다시 요청할 수 없습니다."
        )
    assert caught.value.code is ErrorCode.INVALID_STATE


def test_domain_values_are_frozen(now: datetime) -> None:
    run = make_run(now)
    with pytest.raises(FrozenInstanceError):
        run.status = RunStatus.RUNNING  # type: ignore[misc]


def test_non_utc_offset_is_rejected() -> None:
    from datetime import timezone

    offset = timezone(timedelta(hours=9))
    with pytest.raises(DomainError):
        make_run(datetime(2026, 7, 16, tzinfo=offset))


def test_project_plan_and_request_constraints(now: datetime) -> None:
    with pytest.raises(DomainError):
        Project(
            id=" ",
            organization_id="org-a",
            name="invalid",
            profile="government",
            status=ProjectStatus.ACTIVE,
            version=1,
            created_at=now,
            updated_at=now,
        )
    with pytest.raises(DomainError):
        Project(
            id="project-a1",
            organization_id="org-a",
            name="invalid",
            profile="government",
            status=ProjectStatus.ACTIVE,
            version=0,
            created_at=now,
            updated_at=now,
        )
    with pytest.raises(DomainError):
        ResearchPlan(
            id="plan-a1",
            organization_id="org-a",
            project_id="project-a1",
            version=1,
            question="승인 메타데이터가 없는 계획",
            status=PlanStatus.APPROVED,
            approved_by=None,
            approved_at=None,
        )
    with pytest.raises(DomainError):
        ResearchPlan(
            id="plan-a1",
            organization_id="org-a",
            project_id="project-a1",
            version=1,
            question="초안에 승인 메타데이터가 있는 계획",
            status=PlanStatus.DRAFT,
            approved_by="manager-a",
            approved_at=now,
        )
    with pytest.raises(DomainError):
        ResearchRun(
            id="run-invalid-key",
            organization_id="org-a",
            project_id="project-a1",
            plan_id="plan-a1",
            plan_version=1,
            initiated_by="user-a",
            status=RunStatus.QUEUED,
            version=1,
            idempotency_key="short",
            request_fingerprint="a" * 64,
            created_at=now,
            updated_at=now,
        )


def test_cancellation_reason_and_job_datetime_constraints(now: datetime) -> None:
    with pytest.raises(DomainError):
        make_run(now).request_cancellation(now + timedelta(seconds=1), "짧음")

    from datetime import timezone

    with pytest.raises(DomainError):
        Job(
            id="job-offset",
            organization_id="org-a",
            project_id="project-a1",
            run_id="run-a1",
            state=JobState.QUEUED,
            available_at=datetime(2026, 7, 16, tzinfo=timezone(timedelta(hours=9))),
            created_at=now,
            updated_at=now,
        )
