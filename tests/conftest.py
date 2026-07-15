from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import count

import pytest

from psr_mcp.application.cursors import HmacCursorCodec
from psr_mcp.application.projects import ProjectService
from psr_mcp.application.research_runs import ResearchRunService
from psr_mcp.application.workers import WorkerService
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.auth.policy import AuthorizationPolicy
from psr_mcp.domain.identity import ActorType, Role
from psr_mcp.domain.projects import Project, ProjectStatus
from psr_mcp.domain.research import PlanStatus, ResearchPlan
from psr_mcp.storage.memory import InMemoryStore


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


class SequenceIds:
    def __init__(self) -> None:
        self._values = count(1)

    def new(self) -> str:
        return f"id-{next(self._values):08d}"


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 7, 16, 9, 0, tzinfo=UTC)


@pytest.fixture
def clock(now: datetime) -> MutableClock:
    return MutableClock(now)


@pytest.fixture
def ids() -> SequenceIds:
    return SequenceIds()


@pytest.fixture
def project_a1(now: datetime) -> Project:
    return Project(
        id="project-a1",
        organization_id="org-a",
        name="AI 구매 원칙",
        profile="government",
        status=ProjectStatus.ACTIVE,
        version=1,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def project_a2(now: datetime) -> Project:
    return Project(
        id="project-a2",
        organization_id="org-a",
        name="개인정보 가이드",
        profile="government",
        status=ProjectStatus.ACTIVE,
        version=1,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def project_b1(now: datetime) -> Project:
    return Project(
        id="project-b1",
        organization_id="org-b",
        name="다른 기관 조사",
        profile="government",
        status=ProjectStatus.ACTIVE,
        version=1,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def approved_plan(now: datetime, project_a1: Project) -> ResearchPlan:
    return ResearchPlan(
        id="plan-approved-a1",
        organization_id=project_a1.organization_id,
        project_id=project_a1.id,
        version=1,
        question="공공기관 AI 구매 원칙을 수립한다.",
        status=PlanStatus.APPROVED,
        approved_by="manager-a",
        approved_at=now,
    )


@pytest.fixture
def draft_plan(project_a1: Project) -> ResearchPlan:
    return ResearchPlan(
        id="plan-draft-a1",
        organization_id=project_a1.organization_id,
        project_id=project_a1.id,
        version=1,
        question="검토되지 않은 질문",
        status=PlanStatus.DRAFT,
        approved_by=None,
        approved_at=None,
    )


@pytest.fixture
def auth_a_wide() -> AuthorizationContext:
    return AuthorizationContext(
        organization_id="org-a",
        subject_id="user-a",
        roles=frozenset({Role.RESEARCHER}),
        scopes=frozenset({"project:read", "research:run"}),
        project_ids=None,
        actor_type=ActorType.HUMAN,
    )


@pytest.fixture
def auth_a_limited() -> AuthorizationContext:
    return AuthorizationContext(
        organization_id="org-a",
        subject_id="user-a-limited",
        roles=frozenset({Role.RESEARCHER}),
        scopes=frozenset({"project:read", "research:run"}),
        project_ids=frozenset({"project-a1"}),
    )


@pytest.fixture
def auth_b() -> AuthorizationContext:
    return AuthorizationContext(
        organization_id="org-b",
        subject_id="user-b",
        roles=frozenset({Role.RESEARCHER}),
        scopes=frozenset({"project:read", "research:run"}),
        project_ids=None,
    )


@pytest.fixture
def store(
    project_a1: Project,
    project_a2: Project,
    project_b1: Project,
    approved_plan: ResearchPlan,
    draft_plan: ResearchPlan,
) -> InMemoryStore:
    return InMemoryStore.from_seed(
        projects=[project_a1, project_a2, project_b1],
        plans=[approved_plan, draft_plan],
    )


@pytest.fixture
def project_service(store: InMemoryStore, ids: SequenceIds) -> ProjectService:
    return ProjectService(
        store.unit_of_work,
        AuthorizationPolicy(),
        HmacCursorCodec(b"testing-cursor-signing-key-32-bytes-long"),
        ids,
    )


@pytest.fixture
def run_service(store: InMemoryStore, clock: MutableClock, ids: SequenceIds) -> ResearchRunService:
    return ResearchRunService(store.unit_of_work, AuthorizationPolicy(), clock, ids)


@pytest.fixture
def worker_service(store: InMemoryStore, clock: MutableClock, ids: SequenceIds) -> WorkerService:
    return WorkerService(store.unit_of_work, clock, ids)
