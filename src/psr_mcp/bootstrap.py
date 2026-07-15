"""Composition roots. Production adapters intentionally fail closed until implemented."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from psr_mcp.application.cursors import HmacCursorCodec
from psr_mcp.application.projects import ProjectService
from psr_mcp.application.research_runs import ResearchRunService
from psr_mcp.application.workers import WorkerService
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.auth.policy import AuthorizationPolicy
from psr_mcp.auth.providers import AuthContextProvider, StaticAuthContextProvider
from psr_mcp.common.runtime import SystemClock, Uuid4Generator
from psr_mcp.config import AuthMode, Environment, Settings, StorageMode
from psr_mcp.domain.identity import ActorType, Role
from psr_mcp.domain.projects import Project, ProjectStatus
from psr_mcp.domain.research import PlanStatus, ResearchPlan
from psr_mcp.storage.memory import InMemoryStore


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    auth_provider: AuthContextProvider
    project_service: ProjectService
    run_service: ResearchRunService
    worker_service: WorkerService
    ids: Uuid4Generator
    store: InMemoryStore


def build_container(settings: Settings) -> Container:
    settings.validate()
    if (
        settings.environment is not Environment.DEVELOPMENT
        or settings.auth_mode is not AuthMode.STATIC
        or settings.storage_mode is not StorageMode.MEMORY
    ):
        raise RuntimeError(
            "production OAuth and PostgreSQL adapters are not implemented; "
            "refusing insecure startup"
        )

    now = datetime(2026, 7, 16, tzinfo=UTC)
    project = Project(
        id="project-public-ai",
        organization_id="org-development-a",
        name="공공기관 AI 구매 원칙",
        profile="government",
        status=ProjectStatus.ACTIVE,
        version=1,
        created_at=now,
        updated_at=now,
    )
    plan = ResearchPlan(
        id="plan-approved-public-ai",
        organization_id=project.organization_id,
        project_id=project.id,
        version=1,
        question="공공기관 AI 구매 원칙을 수립한다.",
        status=PlanStatus.APPROVED,
        approved_by="development-manager",
        approved_at=now,
    )
    store = InMemoryStore.from_seed(projects=[project], plans=[plan])
    auth = AuthorizationContext(
        organization_id=project.organization_id,
        subject_id="development-researcher",
        roles=frozenset({Role.RESEARCHER}),
        scopes=frozenset({"project:read", "research:run"}),
        project_ids=frozenset({project.id}),
        actor_type=ActorType.HUMAN,
        client_id="development-client",
    )
    ids = Uuid4Generator()
    clock = SystemClock()
    policy = AuthorizationPolicy()
    cursor = HmacCursorCodec(settings.cursor_signing_key.encode())
    return Container(
        settings=settings,
        auth_provider=StaticAuthContextProvider(auth),
        project_service=ProjectService(store.unit_of_work, policy, cursor, ids),
        run_service=ResearchRunService(store.unit_of_work, policy, clock, ids),
        worker_service=WorkerService(store.unit_of_work, clock, ids),
        ids=ids,
        store=store,
    )
