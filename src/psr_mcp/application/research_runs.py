"""ResearchRun commands and queries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from psr_mcp.application.ports import Clock, IdGenerator, UnitOfWorkFactory
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.auth.policy import (
    PROJECT_READ_ROLES,
    RESEARCH_RUN_ROLES,
    AuthorizationPolicy,
)
from psr_mcp.domain.audit import AuditEvent, AuditOutcome
from psr_mcp.domain.errors import DomainError, ErrorCode, invalid
from psr_mcp.domain.projects import ProjectStatus
from psr_mcp.domain.research import (
    IDEMPOTENCY_KEY_PATTERN,
    Job,
    JobState,
    PlanStatus,
    ResearchRun,
    RunStatus,
)


@dataclass(frozen=True, slots=True)
class StartRunResult:
    run: ResearchRun
    operation_id: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class RunResult:
    run: ResearchRun
    operation_id: str


@dataclass(frozen=True, slots=True)
class CancelRunResult:
    run: ResearchRun
    operation_id: str
    cancellation_requested: bool


class ResearchRunService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        policy: AuthorizationPolicy,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy
        self._clock = clock
        self._ids = ids

    async def start(
        self,
        auth: AuthorizationContext,
        *,
        approved_plan_id: str,
        idempotency_key: str,
    ) -> StartRunResult:
        operation_id = self._ids.new()
        if not IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
            raise invalid(
                "idempotency_key must be 8..128 safe ASCII characters",
                field="idempotency_key",
            )
        now = self._clock.now()
        async with self._uow_factory() as uow:
            plan = await uow.plans.get(auth.organization_id, approved_plan_id)
            if plan is None:
                raise DomainError(
                    ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                    "the requested target was not found or is not accessible",
                )
            project_candidate = await uow.projects.get(auth.organization_id, plan.project_id)
            project = self._policy.require_project(
                auth,
                project_candidate,
                scope="research:run",
                allowed_roles=RESEARCH_RUN_ROLES,
            )
            if project.status is not ProjectStatus.ACTIVE:
                raise DomainError(ErrorCode.INVALID_STATE, "archived project cannot start a run")
            if plan.status is not PlanStatus.APPROVED:
                raise DomainError(ErrorCode.PLAN_NOT_APPROVED, "research plan is not approved")
            fingerprint = _fingerprint(plan.id, plan.version)
            existing = await uow.runs.find_idempotent(
                auth.organization_id,
                project.id,
                auth.subject_id,
                idempotency_key,
            )
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise DomainError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "idempotency key was used with a different request",
                    )
                await uow.audit.add(
                    self._audit_event(
                        auth,
                        operation_id,
                        "research.run.start",
                        "ResearchRun",
                        AuditOutcome.IDEMPOTENT_REPLAY,
                        project_id=project.id,
                        target_id=existing.id,
                        metadata={"plan_version": plan.version, "replayed": True},
                    )
                )
                await uow.commit()
                return StartRunResult(existing, operation_id, True)

            run = ResearchRun(
                id=self._ids.new(),
                organization_id=auth.organization_id,
                project_id=project.id,
                plan_id=plan.id,
                plan_version=plan.version,
                initiated_by=auth.subject_id,
                status=RunStatus.QUEUED,
                version=1,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                created_at=now,
                updated_at=now,
            )
            job = Job(
                id=self._ids.new(),
                organization_id=auth.organization_id,
                project_id=project.id,
                run_id=run.id,
                state=JobState.QUEUED,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
            await uow.runs.add(run)
            await uow.jobs.add(job)
            await uow.audit.add(
                self._audit_event(
                    auth,
                    operation_id,
                    "research.run.start",
                    "ResearchRun",
                    AuditOutcome.SUCCEEDED,
                    project_id=project.id,
                    target_id=run.id,
                    metadata={"plan_version": plan.version, "replayed": False},
                )
            )
            await uow.commit()
        return StartRunResult(run, operation_id, False)

    async def status(self, auth: AuthorizationContext, run_id: str) -> RunResult:
        async with self._uow_factory() as uow:
            run = await uow.runs.get(auth.organization_id, run_id)
            if run is None:
                raise DomainError(
                    ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                    "the requested target was not found or is not accessible",
                )
            project_candidate = await uow.projects.get(auth.organization_id, run.project_id)
            self._policy.require_project(
                auth,
                project_candidate,
                scope="project:read",
                allowed_roles=PROJECT_READ_ROLES,
            )
        return RunResult(run, self._ids.new())

    async def cancel(
        self,
        auth: AuthorizationContext,
        *,
        run_id: str,
        reason: str,
        expected_version: int,
    ) -> CancelRunResult:
        operation_id = self._ids.new()
        now = self._clock.now()
        async with self._uow_factory() as uow:
            run = await uow.runs.get(auth.organization_id, run_id)
            if run is None:
                raise DomainError(
                    ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                    "the requested target was not found or is not accessible",
                )
            project_candidate = await uow.projects.get(auth.organization_id, run.project_id)
            project = self._policy.require_project(
                auth,
                project_candidate,
                scope="research:run",
                allowed_roles=RESEARCH_RUN_ROLES,
            )
            if run.version != expected_version:
                raise DomainError(
                    ErrorCode.VERSION_CONFLICT,
                    "run version changed; reload before retrying",
                    retryable=True,
                )
            job = await uow.jobs.get_by_run(auth.organization_id, run.id)
            if job is None:
                raise DomainError(ErrorCode.INTERNAL_ERROR, "run job is missing")
            updated = run.request_cancellation(now, reason)
            if run.status is RunStatus.QUEUED:
                updated_job = replace(
                    job,
                    state=JobState.CANCELLED,
                    updated_at=now,
                    cancel_requested_at=now,
                    lease_owner=None,
                    lease_expires_at=None,
                )
                requested = False
            else:
                updated_job = replace(job, updated_at=now, cancel_requested_at=now)
                requested = True
            await uow.runs.update(updated, expected_version=expected_version)
            await uow.jobs.update(updated_job)
            await uow.audit.add(
                self._audit_event(
                    auth,
                    operation_id,
                    "research.run.cancel",
                    "ResearchRun",
                    AuditOutcome.SUCCEEDED,
                    project_id=project.id,
                    target_id=run.id,
                    metadata={"run_status": updated.status},
                )
            )
            await uow.commit()
        return CancelRunResult(updated, operation_id, requested)

    def _audit_event(
        self,
        auth: AuthorizationContext,
        operation_id: str,
        operation: str,
        target_type: str,
        outcome: AuditOutcome,
        *,
        project_id: str,
        target_id: str,
        metadata: dict[str, object],
    ) -> AuditEvent:
        return AuditEvent(
            id=self._ids.new(),
            organization_id=auth.organization_id,
            project_id=project_id,
            occurred_at=self._clock.now(),
            actor_subject_id=auth.subject_id,
            actor_type=auth.actor_type,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            operation_id=operation_id,
            metadata=metadata,
        )


def _fingerprint(plan_id: str, plan_version: int) -> str:
    canonical = json.dumps(
        {"plan_id": plan_id, "plan_version": plan_version},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
