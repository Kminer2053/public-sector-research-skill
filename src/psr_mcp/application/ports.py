"""Ports implemented by storage, time, and identifier adapters."""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from psr_mcp.domain.audit import AuditEvent
from psr_mcp.domain.projects import Project
from psr_mcp.domain.research import Job, ResearchPlan, ResearchRun


class ProjectRepository(Protocol):
    async def list_page(
        self,
        organization_id: str,
        *,
        project_ids: frozenset[str] | None,
        after: tuple[datetime, str] | None,
        limit: int,
    ) -> list[Project]: ...

    async def get(self, organization_id: str, project_id: str) -> Project | None: ...


class PlanRepository(Protocol):
    async def get(self, organization_id: str, plan_id: str) -> ResearchPlan | None: ...


class RunRepository(Protocol):
    async def get(self, organization_id: str, run_id: str) -> ResearchRun | None: ...

    async def find_idempotent(
        self,
        organization_id: str,
        project_id: str,
        initiated_by: str,
        idempotency_key: str,
    ) -> ResearchRun | None: ...

    async def add(self, run: ResearchRun) -> None: ...

    async def update(self, run: ResearchRun, *, expected_version: int) -> None: ...


class JobRepository(Protocol):
    async def get_by_run(self, organization_id: str, run_id: str) -> Job | None: ...

    async def list_claimable(
        self, organization_id: str, *, now: datetime, limit: int
    ) -> list[Job]: ...

    async def add(self, job: Job) -> None: ...

    async def update(self, job: Job) -> None: ...


class AuditRepository(Protocol):
    async def add(self, event: AuditEvent) -> None: ...


class UnitOfWork(Protocol):
    @property
    def projects(self) -> ProjectRepository: ...

    @property
    def plans(self) -> PlanRepository: ...

    @property
    def runs(self) -> RunRepository: ...

    @property
    def jobs(self) -> JobRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new(self) -> str: ...


class CursorCodec(Protocol):
    def encode(self, position: tuple[datetime, str]) -> str: ...

    def decode(self, cursor: str) -> tuple[datetime, str]: ...
