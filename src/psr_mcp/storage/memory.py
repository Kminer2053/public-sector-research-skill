"""Serialized in-memory UnitOfWork for tests and loopback development only."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType

from psr_mcp.application.ports import (
    AuditRepository,
    JobRepository,
    PlanRepository,
    ProjectRepository,
    RunRepository,
)
from psr_mcp.domain.audit import AuditEvent
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.projects import Project
from psr_mcp.domain.research import Job, ResearchPlan, ResearchRun


@dataclass(slots=True)
class MemoryState:
    projects: dict[tuple[str, str], Project] = field(default_factory=dict)
    plans: dict[tuple[str, str], ResearchPlan] = field(default_factory=dict)
    runs: dict[tuple[str, str], ResearchRun] = field(default_factory=dict)
    jobs: dict[tuple[str, str], Job] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)


class InMemoryStore:
    """Owns committed state; it must never be selected in production."""

    def __init__(self) -> None:
        self._state = MemoryState()
        self._lock = asyncio.Lock()

    @classmethod
    def from_seed(
        cls,
        *,
        projects: list[Project] | None = None,
        plans: list[ResearchPlan] | None = None,
    ) -> InMemoryStore:
        store = cls()
        for project in projects or []:
            store._state.projects[(project.organization_id, project.id)] = project
        for plan in plans or []:
            store._state.plans[(plan.organization_id, plan.id)] = plan
        return store

    def unit_of_work(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self)

    async def seed(
        self,
        *,
        projects: list[Project] | None = None,
        plans: list[ResearchPlan] | None = None,
    ) -> None:
        async with self._lock:
            for project in projects or []:
                self._state.projects[(project.organization_id, project.id)] = project
            for plan in plans or []:
                self._state.plans[(plan.organization_id, plan.id)] = plan

    async def snapshot(self) -> MemoryState:
        async with self._lock:
            return copy.deepcopy(self._state)


class InMemoryProjectRepository(ProjectRepository):
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    async def list_page(
        self,
        organization_id: str,
        *,
        project_ids: frozenset[str] | None,
        after: tuple[datetime, str] | None,
        limit: int,
    ) -> list[Project]:
        projects = [
            project
            for (tenant_id, _), project in self._state.projects.items()
            if tenant_id == organization_id
            and (project_ids is None or project.id in project_ids)
            and (after is None or (project.created_at, project.id) > after)
        ]
        projects.sort(key=lambda project: (project.created_at, project.id))
        return projects[:limit]

    async def get(self, organization_id: str, project_id: str) -> Project | None:
        return self._state.projects.get((organization_id, project_id))


class InMemoryPlanRepository(PlanRepository):
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    async def get(self, organization_id: str, plan_id: str) -> ResearchPlan | None:
        return self._state.plans.get((organization_id, plan_id))


class InMemoryRunRepository(RunRepository):
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    async def get(self, organization_id: str, run_id: str) -> ResearchRun | None:
        return self._state.runs.get((organization_id, run_id))

    async def find_idempotent(
        self,
        organization_id: str,
        project_id: str,
        initiated_by: str,
        idempotency_key: str,
    ) -> ResearchRun | None:
        return next(
            (
                run
                for (tenant_id, _), run in self._state.runs.items()
                if tenant_id == organization_id
                and run.project_id == project_id
                and run.initiated_by == initiated_by
                and run.idempotency_key == idempotency_key
            ),
            None,
        )

    async def add(self, run: ResearchRun) -> None:
        key = (run.organization_id, run.id)
        if key in self._state.runs:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT, "run identifier already exists")
        duplicate = await self.find_idempotent(
            run.organization_id,
            run.project_id,
            run.initiated_by,
            run.idempotency_key,
        )
        if duplicate is not None:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT, "idempotency key already exists")
        self._state.runs[key] = run

    async def update(self, run: ResearchRun, *, expected_version: int) -> None:
        key = (run.organization_id, run.id)
        current = self._state.runs.get(key)
        if current is None:
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the requested target was not found or is not accessible",
            )
        if current.version != expected_version:
            raise DomainError(
                ErrorCode.VERSION_CONFLICT,
                "run version changed; reload before retrying",
                retryable=True,
            )
        self._state.runs[key] = run


class InMemoryJobRepository(JobRepository):
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    async def get_by_run(self, organization_id: str, run_id: str) -> Job | None:
        return next(
            (
                job
                for (tenant_id, _), job in self._state.jobs.items()
                if tenant_id == organization_id and job.run_id == run_id
            ),
            None,
        )

    async def list_claimable(self, organization_id: str, *, now: datetime, limit: int) -> list[Job]:
        jobs = [
            job
            for (tenant_id, _), job in self._state.jobs.items()
            if tenant_id == organization_id and job.is_claimable(now)
        ]
        jobs.sort(key=lambda job: (job.available_at, job.created_at, job.id))
        return jobs[:limit]

    async def add(self, job: Job) -> None:
        key = (job.organization_id, job.id)
        if key in self._state.jobs or await self.get_by_run(job.organization_id, job.run_id):
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT, "job already exists for run")
        self._state.jobs[key] = job

    async def update(self, job: Job) -> None:
        key = (job.organization_id, job.id)
        if key not in self._state.jobs:
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the requested target was not found or is not accessible",
            )
        self._state.jobs[key] = job


class InMemoryAuditRepository(AuditRepository):
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    async def add(self, event: AuditEvent) -> None:
        if any(existing.id == event.id for existing in self._state.audit_events):
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT, "audit event identifier exists")
        self._state.audit_events.append(event)


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._working: MemoryState | None = None
        self._committed = False

    @property
    def projects(self) -> ProjectRepository:
        return InMemoryProjectRepository(self._state)

    @property
    def plans(self) -> PlanRepository:
        return InMemoryPlanRepository(self._state)

    @property
    def runs(self) -> RunRepository:
        return InMemoryRunRepository(self._state)

    @property
    def jobs(self) -> JobRepository:
        return InMemoryJobRepository(self._state)

    @property
    def audit(self) -> AuditRepository:
        return InMemoryAuditRepository(self._state)

    @property
    def _state(self) -> MemoryState:
        if self._working is None:
            raise RuntimeError("unit of work is not active")
        return self._working

    async def __aenter__(self) -> InMemoryUnitOfWork:
        await self._store._lock.acquire()
        self._working = copy.deepcopy(self._store._state)
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None or not self._committed:
                await self.rollback()
        finally:
            self._working = None
            self._store._lock.release()

    async def commit(self) -> None:
        self._store._state = copy.deepcopy(self._state)
        self._committed = True

    async def rollback(self) -> None:
        self._committed = False
