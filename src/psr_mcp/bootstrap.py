"""Composition roots for the development harness and OAuth/PostgreSQL service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from psr_mcp.application.cursors import HmacCursorCodec
from psr_mcp.application.projects import ProjectService
from psr_mcp.application.research_runs import ResearchRunService
from psr_mcp.application.workers import WorkerService
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.auth.policy import AuthorizationPolicy
from psr_mcp.auth.providers import (
    AuthContextProvider,
    McpAccessTokenAuthContextProvider,
    StaticAuthContextProvider,
)
from psr_mcp.auth.tokens import OidcJwtTokenVerifier, OidcVerifierSettings
from psr_mcp.common.runtime import SystemClock, Uuid4Generator
from psr_mcp.common.secrets import EnvironmentSecretResolver, SecretResolver
from psr_mcp.config import AuthMode, Environment, Settings, StorageMode
from psr_mcp.domain.identity import ActorType, Role
from psr_mcp.domain.projects import Project, ProjectStatus
from psr_mcp.domain.research import PlanStatus, ResearchPlan
from psr_mcp.storage.memory import InMemoryStore
from psr_mcp.storage.postgres import PostgresMembershipResolver, PostgresStore

ApplicationStore = InMemoryStore | PostgresStore


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    auth_provider: AuthContextProvider
    project_service: ProjectService
    run_service: ResearchRunService
    worker_service: WorkerService
    ids: Uuid4Generator
    store: ApplicationStore
    token_verifier: OidcJwtTokenVerifier | None = None

    async def open(self) -> None:
        if isinstance(self.store, PostgresStore):
            await self.store.open()

    async def close(self) -> None:
        try:
            if self.token_verifier is not None:
                await self.token_verifier.aclose()
        finally:
            if isinstance(self.store, PostgresStore):
                await self.store.close()


def build_container(
    settings: Settings,
    *,
    secret_resolver: SecretResolver | None = None,
) -> Container:
    settings.validate()
    if (
        settings.environment is Environment.DEVELOPMENT
        and settings.auth_mode is AuthMode.STATIC
        and settings.storage_mode is StorageMode.MEMORY
    ):
        return _build_development_container(settings)
    if settings.auth_mode is AuthMode.OAUTH and settings.storage_mode is StorageMode.POSTGRES:
        return _build_oauth_postgres_container(
            settings,
            secret_resolver or EnvironmentSecretResolver(),
        )
    raise RuntimeError("unsupported authentication and storage composition; refusing startup")


def _build_development_container(settings: Settings) -> Container:
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
    return _assemble_container(settings, store, StaticAuthContextProvider(auth), None)


def _build_oauth_postgres_container(
    settings: Settings,
    secret_resolver: SecretResolver,
) -> Container:
    if settings.issuer_url is None or settings.database_url_ref is None:
        raise RuntimeError("OAuth/PostgreSQL composition requires issuer and database references")
    database_url = secret_resolver.resolve(settings.database_url_ref)
    if urlparse(database_url).scheme not in {"postgresql", "postgres"}:
        raise ValueError("database secret must be a PostgreSQL URL")
    store = PostgresStore(database_url)
    verifier = OidcJwtTokenVerifier(
        OidcVerifierSettings(
            issuer=settings.issuer_url,
            audience=settings.resource_server_url,
            allowed_algorithms=frozenset(settings.oauth_allowed_algorithms),
            organization_claim=settings.oauth_organization_claim,
            allowed_jwks_origins=frozenset(settings.oauth_jwks_origins),
            allow_insecure_http=settings.environment is Environment.DEVELOPMENT,
        )
    )
    auth = McpAccessTokenAuthContextProvider(PostgresMembershipResolver(store.pool))
    return _assemble_container(settings, store, auth, verifier)


def _assemble_container(
    settings: Settings,
    store: ApplicationStore,
    auth_provider: AuthContextProvider,
    token_verifier: OidcJwtTokenVerifier | None,
) -> Container:
    ids = Uuid4Generator()
    clock = SystemClock()
    policy = AuthorizationPolicy()
    cursor = HmacCursorCodec(settings.cursor_signing_key.encode())
    return Container(
        settings=settings,
        auth_provider=auth_provider,
        project_service=ProjectService(store.unit_of_work, policy, cursor, ids),
        run_service=ResearchRunService(store.unit_of_work, policy, clock, ids),
        worker_service=WorkerService(store.unit_of_work, clock, ids),
        ids=ids,
        store=store,
        token_verifier=token_verifier,
    )
