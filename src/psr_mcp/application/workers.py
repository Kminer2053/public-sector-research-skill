"""Worker lease and completion application service."""

from __future__ import annotations

from dataclasses import dataclass, replace

from psr_mcp.application.ports import Clock, IdGenerator, UnitOfWorkFactory
from psr_mcp.domain.audit import AuditEvent, AuditOutcome
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.identity import ActorType
from psr_mcp.domain.research import Job, JobState, ResearchRun, RunStatus

JOB_TO_RUN_STATUS = {
    JobState.SUCCEEDED: RunStatus.SUCCEEDED,
    JobState.PARTIAL: RunStatus.PARTIAL,
    JobState.FAILED: RunStatus.FAILED,
    JobState.CANCELLED: RunStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class ClaimedRun:
    run: ResearchRun
    job: Job
    operation_id: str


class WorkerService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._ids = ids

    async def claim_next(
        self,
        organization_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 60,
    ) -> ClaimedRun | None:
        operation_id = self._ids.new()
        now = self._clock.now()
        async with self._uow_factory() as uow:
            candidates = await uow.jobs.list_claimable(organization_id, now=now, limit=1)
            if not candidates:
                return None
            job = candidates[0]
            run = await uow.runs.get(organization_id, job.run_id)
            if run is None:
                raise DomainError(ErrorCode.INTERNAL_ERROR, "job run is missing")
            if job.attempts >= job.max_attempts:
                failed_job = replace(
                    job,
                    state=JobState.FAILED,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
                failed_run = run.transition(RunStatus.FAILED, now, failure_code="RETRY_EXHAUSTED")
                await uow.jobs.update(failed_job)
                await uow.runs.update(failed_run, expected_version=run.version)
                await uow.commit()
                return None
            claimed_job = job.claim(worker_id, now, lease_seconds)
            if run.status is RunStatus.QUEUED:
                claimed_run = run.transition(RunStatus.RUNNING, now)
                await uow.runs.update(claimed_run, expected_version=run.version)
            elif run.status is RunStatus.RUNNING:
                claimed_run = run
            else:
                raise DomainError(ErrorCode.INVALID_STATE, "claimable job has terminal run")
            await uow.jobs.update(claimed_job)
            await uow.audit.add(
                self._worker_audit(
                    claimed_run,
                    operation_id,
                    worker_id,
                    "research.job.claim",
                    AuditOutcome.SUCCEEDED,
                )
            )
            await uow.commit()
        return ClaimedRun(claimed_run, claimed_job, operation_id)

    async def heartbeat(
        self,
        organization_id: str,
        *,
        run_id: str,
        worker_id: str,
        extend_seconds: int = 60,
    ) -> Job:
        now = self._clock.now()
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_by_run(organization_id, run_id)
            if job is None:
                raise DomainError(
                    ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                    "the requested target was not found or is not accessible",
                )
            updated = job.heartbeat(worker_id, now, extend_seconds)
            await uow.jobs.update(updated)
            await uow.commit()
        return updated

    async def complete(
        self,
        organization_id: str,
        *,
        run_id: str,
        worker_id: str,
        outcome: JobState,
        failure_code: str | None = None,
    ) -> ResearchRun:
        if outcome not in JOB_TO_RUN_STATUS:
            raise DomainError(ErrorCode.INPUT_INVALID, "worker outcome must be terminal")
        operation_id = self._ids.new()
        now = self._clock.now()
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_by_run(organization_id, run_id)
            run = await uow.runs.get(organization_id, run_id)
            if job is None or run is None:
                raise DomainError(
                    ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                    "the requested target was not found or is not accessible",
                )
            final_outcome = JobState.CANCELLED if job.cancel_requested_at else outcome
            updated_job = job.finish(worker_id, now, final_outcome)
            target = JOB_TO_RUN_STATUS[final_outcome]
            updated_run = run.transition(target, now, failure_code=failure_code)
            await uow.jobs.update(updated_job)
            await uow.runs.update(updated_run, expected_version=run.version)
            await uow.audit.add(
                self._worker_audit(
                    updated_run,
                    operation_id,
                    worker_id,
                    "research.job.complete",
                    AuditOutcome.SUCCEEDED,
                )
            )
            await uow.commit()
        return updated_run

    def _worker_audit(
        self,
        run: ResearchRun,
        operation_id: str,
        worker_id: str,
        operation: str,
        outcome: AuditOutcome,
    ) -> AuditEvent:
        return AuditEvent(
            id=self._ids.new(),
            organization_id=run.organization_id,
            project_id=run.project_id,
            occurred_at=self._clock.now(),
            actor_subject_id=worker_id,
            actor_type=ActorType.SERVICE,
            operation=operation,
            target_type="ResearchRun",
            target_id=run.id,
            outcome=outcome,
            operation_id=operation_id,
            metadata={"run_status": run.status},
        )
