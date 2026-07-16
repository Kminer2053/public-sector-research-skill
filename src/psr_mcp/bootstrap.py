"""Composition roots for the development harness and OAuth/PostgreSQL service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

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
from psr_mcp.collectors import (
    CollectionLimits,
    PinnedHttpcoreTransport,
    RobotsSourceAccessPolicy,
    SafeCollector,
    SystemHostResolver,
    UrlPolicy,
)
from psr_mcp.common.runtime import SystemClock, Uuid4Generator
from psr_mcp.common.secrets import EnvironmentSecretResolver, SecretResolver
from psr_mcp.config import (
    AuthMode,
    Environment,
    SearchProviderMode,
    ServiceMode,
    Settings,
    StorageMode,
)
from psr_mcp.domain.identity import ActorType, Role
from psr_mcp.domain.projects import Project, ProjectStatus
from psr_mcp.domain.research import PlanStatus, ResearchPlan
from psr_mcp.ephemeral import FilesystemEphemeralWorkspaceStore, PurgeSweeper
from psr_mcp.evidence import EvidenceComposer
from psr_mcp.parsers import DocumentParser, ParserLimits
from psr_mcp.planner import GovernmentPlanner
from psr_mcp.public.development_fixture import build_development_fixture_backend
from psr_mcp.public.pipeline import PublicResearchPipeline
from psr_mcp.public.schemas import SourceDiscoveryMode
from psr_mcp.public.service import (
    PublicQuickResearchService,
    ResearchBackend,
    UnavailableResearchBackend,
)
from psr_mcp.search import (
    BraveSearchProvider,
    CuratedOfficialSourceProvider,
    GovernmentQueryBuilder,
    GovernmentSourceRegistry,
    SearchProvider,
)
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


@dataclass(frozen=True, slots=True)
class PublicContainer:
    settings: Settings
    ids: Uuid4Generator
    workspace_store: FilesystemEphemeralWorkspaceStore
    purge_sweeper: PurgeSweeper
    abuse_hmac_key: bytes
    quick_service: PublicQuickResearchService
    search_client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        await self.workspace_store.open()
        await self.purge_sweeper.start()

    async def close(self) -> None:
        try:
            await self.purge_sweeper.stop()
        finally:
            if self.search_client is not None:
                await self.search_client.aclose()


ApplicationContainer = Container | PublicContainer


def build_container(
    settings: Settings,
    *,
    secret_resolver: SecretResolver | None = None,
) -> ApplicationContainer:
    settings.validate()
    if settings.service_mode is ServiceMode.PUBLIC_EPHEMERAL:
        return _build_public_container(
            settings,
            secret_resolver or EnvironmentSecretResolver(),
        )
    if settings.service_mode is not ServiceMode.FOUNDATION:
        raise RuntimeError(
            f"service mode {settings.service_mode.value} is designed but not implemented"
        )
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


def _build_public_container(
    settings: Settings,
    secret_resolver: SecretResolver,
) -> PublicContainer:
    if settings.ephemeral_root is None:
        raise RuntimeError("public ephemeral composition requires an ephemeral root")
    if settings.abuse_hmac_key_ref:
        abuse_hmac_key = secret_resolver.resolve(settings.abuse_hmac_key_ref).encode()
    else:
        abuse_hmac_key = settings.cursor_signing_key.encode()
    if len(abuse_hmac_key) < 32:
        raise ValueError("public abuse HMAC key must contain at least 32 bytes")
    clock = SystemClock()
    store = FilesystemEphemeralWorkspaceStore(
        Path(settings.ephemeral_root),
        now=clock.now,
        create_root=settings.environment is Environment.DEVELOPMENT,
    )
    ids = Uuid4Generator()
    backend: ResearchBackend
    search_client: httpx.AsyncClient | None = None
    if settings.public_fixture_research_enabled:
        backend = build_development_fixture_backend(clock)
    elif settings.search_provider in {
        SearchProviderMode.BRAVE,
        SearchProviderMode.CURATED,
    }:
        search_provider: SearchProvider
        source_discovery: SourceDiscoveryMode
        if settings.search_provider is SearchProviderMode.BRAVE:
            if settings.search_api_key_ref is None:
                raise RuntimeError("Brave search composition requires an API key reference")
            search_api_key = secret_resolver.resolve(settings.search_api_key_ref)
            if len(search_api_key) < 16:
                raise ValueError("Brave Search API key is too short")
            search_client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.search_timeout_seconds),
                follow_redirects=False,
                trust_env=False,
                limits=httpx.Limits(
                    max_connections=settings.search_max_concurrency,
                    max_keepalive_connections=settings.search_max_concurrency,
                ),
            )
            search_provider = BraveSearchProvider(
                api_key=search_api_key,
                client=search_client,
                registry=GovernmentSourceRegistry(),
                timeout_seconds=settings.search_timeout_seconds,
                max_response_bytes=settings.search_max_response_bytes,
                max_concurrency=settings.search_max_concurrency,
            )
            source_discovery = "brave_live_search"
        else:
            search_provider = CuratedOfficialSourceProvider()
            source_discovery = "curated_seed"
        collector = SafeCollector(
            policy=UrlPolicy(SystemHostResolver()),
            transport=PinnedHttpcoreTransport(),
            clock=clock,
            limits=CollectionLimits(
                max_response_bytes=min(
                    settings.max_run_bytes,
                    10_485_760,
                ),
                total_timeout_seconds=min(
                    settings.quick_timeout_seconds,
                    20.0,
                ),
            ),
        )
        backend = PublicResearchPipeline(
            query_builder=GovernmentQueryBuilder(
                max_results_per_track=min(5, settings.max_run_sources),
            ),
            search_provider=search_provider,
            collector=collector,
            parser=DocumentParser(
                ParserLimits(
                    max_input_bytes=min(
                        settings.max_run_bytes,
                        10_485_760,
                    ),
                    pdf_timeout_seconds=min(
                        settings.quick_timeout_seconds / 2,
                        5.0,
                    ),
                )
            ),
            evidence=EvidenceComposer(
                max_citations=settings.max_run_sources,
                max_per_document=2,
            ),
            source_policy=RobotsSourceAccessPolicy(collector),
            max_collection_concurrency=settings.collection_max_concurrency,
            source_discovery=source_discovery,
        )
    else:
        backend = UnavailableResearchBackend()
    return PublicContainer(
        settings=settings,
        ids=ids,
        workspace_store=store,
        purge_sweeper=PurgeSweeper(
            store,
            interval_seconds=settings.purge_sweep_seconds,
        ),
        abuse_hmac_key=abuse_hmac_key,
        search_client=search_client,
        quick_service=PublicQuickResearchService(
            store=store,
            planner=GovernmentPlanner(),
            backend=backend,
            clock=clock,
            ids=ids,
            run_ttl_seconds=settings.run_ttl_seconds,
            orphan_max_age_seconds=settings.orphan_max_age_seconds,
            max_sources=settings.max_run_sources,
            max_bytes=settings.max_run_bytes,
            timeout_seconds=settings.quick_timeout_seconds,
            max_active_quick=settings.public_max_active_quick,
            daily_quick_budget=settings.public_daily_quick_budget,
            kill_switch=settings.public_kill_switch,
        ),
    )


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
