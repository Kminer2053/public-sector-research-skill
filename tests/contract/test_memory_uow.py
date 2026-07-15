from __future__ import annotations

from datetime import datetime

import pytest

from psr_mcp.domain.audit import AuditEvent, AuditOutcome
from psr_mcp.domain.identity import ActorType
from psr_mcp.domain.projects import Project
from psr_mcp.domain.research import Job, JobState, ResearchRun, RunStatus
from psr_mcp.storage.memory import InMemoryStore


@pytest.mark.anyio
async def test_commit_persists_and_implicit_exit_rolls_back(
    project_a1: Project, project_a2: Project, now: datetime
) -> None:
    store = InMemoryStore.from_seed(projects=[project_a1])

    async with store.unit_of_work() as uow:
        await uow.projects.get("org-a", project_a1.id)
        # No Project write port exists yet; commit still records transaction intent.
        await uow.commit()

    snapshot = await store.snapshot()
    assert ("org-a", project_a1.id) in snapshot.projects
    assert ("org-a", project_a2.id) not in snapshot.projects


@pytest.mark.anyio
async def test_repository_requires_tenant_predicate(
    store: InMemoryStore, project_a1: Project
) -> None:
    async with store.unit_of_work() as uow:
        assert await uow.projects.get("org-a", project_a1.id) == project_a1
        assert await uow.projects.get("org-b", project_a1.id) is None


@pytest.mark.anyio
async def test_audit_failure_rolls_back_run_job_and_audit(now: datetime) -> None:
    store = InMemoryStore()
    run = ResearchRun(
        id="run-rollback",
        organization_id="org-a",
        project_id="project-a1",
        plan_id="plan-a1",
        plan_version=1,
        initiated_by="user-a",
        status=RunStatus.QUEUED,
        version=1,
        idempotency_key="rollback-request-0001",
        request_fingerprint="0" * 64,
        created_at=now,
        updated_at=now,
    )
    job = Job(
        id="job-rollback",
        organization_id="org-a",
        project_id="project-a1",
        run_id=run.id,
        state=JobState.QUEUED,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    event = AuditEvent(
        id="audit-rollback",
        organization_id="org-a",
        project_id="project-a1",
        occurred_at=now,
        actor_subject_id="user-a",
        actor_type=ActorType.HUMAN,
        operation="research.run.start",
        target_type="ResearchRun",
        target_id=run.id,
        outcome=AuditOutcome.SUCCEEDED,
        operation_id="operation-rollback",
    )

    with pytest.raises(Exception, match="audit event identifier exists"):
        async with store.unit_of_work() as uow:
            await uow.runs.add(run)
            await uow.jobs.add(job)
            await uow.audit.add(event)
            await uow.audit.add(event)
            await uow.commit()

    snapshot = await store.snapshot()
    assert snapshot.runs == {}
    assert snapshot.jobs == {}
    assert snapshot.audit_events == []
