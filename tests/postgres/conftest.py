from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import count
from uuid import UUID

import psycopg
import pytest
from psycopg import sql

from psr_mcp.application.cursors import HmacCursorCodec
from psr_mcp.application.projects import ProjectService
from psr_mcp.application.research_runs import ResearchRunService
from psr_mcp.application.workers import WorkerService
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.auth.policy import AuthorizationPolicy
from psr_mcp.domain.identity import Role
from psr_mcp.storage.migrations.runner import downgrade, upgrade
from psr_mcp.storage.postgres import PostgresStore

ORG_A = "00000000-0000-0000-0000-00000000000a"
ORG_B = "00000000-0000-0000-0000-00000000000b"
USER_A = "00000000-0000-0000-0000-00000000001a"
USER_B = "00000000-0000-0000-0000-00000000001b"
PROJECT_A1 = "00000000-0000-0000-0000-0000000000a1"
PROJECT_A2 = "00000000-0000-0000-0000-0000000000a2"
PROJECT_B1 = "00000000-0000-0000-0000-0000000000b1"
PLAN_A1 = "00000000-0000-0000-0000-0000000001a1"
PLAN_B1 = "00000000-0000-0000-0000-0000000001b1"
TEST_ISSUER = "https://idp.example.gov/"


@dataclass(frozen=True, slots=True)
class PostgresUrls:
    admin: str
    owner: str
    runtime: str
    runtime_role: str


@dataclass(slots=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


class UuidSequence:
    def __init__(self, start: int = 10_000) -> None:
        self._values = count(start)

    def new(self) -> str:
        return str(UUID(int=next(self._values)))


@pytest.fixture(scope="session")
def postgres_urls() -> Generator[PostgresUrls]:
    admin = os.getenv("PSR_TEST_ADMIN_DATABASE_URL")
    owner = os.getenv("PSR_TEST_OWNER_DATABASE_URL")
    runtime = os.getenv("PSR_TEST_RUNTIME_DATABASE_URL")
    runtime_role = os.getenv("PSR_TEST_RUNTIME_ROLE", "psr_test_runtime")
    if not admin or not owner or not runtime:
        pytest.skip("PostgreSQL test URLs are not configured")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", runtime_role):
        raise ValueError("PSR_TEST_RUNTIME_ROLE is not a safe SQL identifier")

    downgrade(owner)
    upgrade(owner)
    with psycopg.connect(owner, autocommit=True) as connection:
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(runtime_role))
        )
        connection.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}").format(
                sql.Identifier(runtime_role)
            )
        )
        connection.execute(
            sql.SQL(
                "GRANT SELECT ON organizations, memberships, external_identities, "
                "membership_projects, projects, research_plans, research_runs, jobs, "
                "audit_events TO {}"
            ).format(sql.Identifier(runtime_role))
        )
        connection.execute(
            sql.SQL("GRANT INSERT, UPDATE ON research_runs, jobs TO {}").format(
                sql.Identifier(runtime_role)
            )
        )
        connection.execute(
            sql.SQL("GRANT INSERT ON audit_events TO {}").format(sql.Identifier(runtime_role))
        )
    yield PostgresUrls(
        admin=admin,
        owner=owner,
        runtime=runtime,
        runtime_role=runtime_role,
    )


@pytest.fixture
def seeded_postgres(postgres_urls: PostgresUrls) -> PostgresUrls:
    _seed(postgres_urls.owner)
    return postgres_urls


@pytest.fixture
async def postgres_store(
    seeded_postgres: PostgresUrls,
) -> AsyncGenerator[PostgresStore]:
    store = PostgresStore(seeded_postgres.runtime, min_size=1, max_size=6)
    await store.open()
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
def pg_clock() -> FixedClock:
    return FixedClock(datetime(2026, 7, 16, 2, 0, tzinfo=UTC))


@pytest.fixture
def pg_ids() -> UuidSequence:
    return UuidSequence()


@pytest.fixture
def pg_auth_a() -> AuthorizationContext:
    return AuthorizationContext(
        organization_id=ORG_A,
        subject_id=USER_A,
        roles=frozenset({Role.RESEARCHER}),
        scopes=frozenset({"project:read", "research:run"}),
        project_ids=None,
    )


@pytest.fixture
def pg_auth_b() -> AuthorizationContext:
    return AuthorizationContext(
        organization_id=ORG_B,
        subject_id=USER_B,
        roles=frozenset({Role.RESEARCHER}),
        scopes=frozenset({"project:read", "research:run"}),
        project_ids=None,
    )


@pytest.fixture
def pg_project_service(postgres_store: PostgresStore, pg_ids: UuidSequence) -> ProjectService:
    return ProjectService(
        postgres_store.unit_of_work,
        AuthorizationPolicy(),
        HmacCursorCodec(b"postgres-test-cursor-key-32-bytes"),
        pg_ids,
    )


@pytest.fixture
def pg_run_service(
    postgres_store: PostgresStore,
    pg_clock: FixedClock,
    pg_ids: UuidSequence,
) -> ResearchRunService:
    return ResearchRunService(
        postgres_store.unit_of_work,
        AuthorizationPolicy(),
        pg_clock,
        pg_ids,
    )


@pytest.fixture
def pg_worker_service(
    postgres_store: PostgresStore,
    pg_clock: FixedClock,
    pg_ids: UuidSequence,
) -> WorkerService:
    return WorkerService(postgres_store.unit_of_work, pg_clock, pg_ids)


def _seed(owner_url: str) -> None:
    now = datetime(2026, 7, 16, 2, 0, tzinfo=UTC)
    with psycopg.connect(owner_url) as connection:
        connection.execute(
            """
            TRUNCATE audit_events, jobs, research_runs, research_plans,
                     membership_projects, projects, external_identities,
                     memberships, users, organizations
            CASCADE
            """
        )
        connection.commit()
        connection.execute(
            """
            INSERT INTO users (id, external_subject, created_at)
            VALUES (%s, %s, %s), (%s, %s, %s)
            """,
            (USER_A, "subject-a", now, USER_B, "subject-b", now),
        )
        connection.commit()
        _seed_tenant(
            connection,
            organization_id=ORG_A,
            user_id=USER_A,
            organization_name="기관 A",
            projects=((PROJECT_A1, "AI 구매 원칙"), (PROJECT_A2, "개인정보 가이드")),
            plan_id=PLAN_A1,
            plan_project_id=PROJECT_A1,
            now=now,
        )
        _seed_tenant(
            connection,
            organization_id=ORG_B,
            user_id=USER_B,
            organization_name="기관 B",
            projects=((PROJECT_B1, "다른 기관 조사"),),
            plan_id=PLAN_B1,
            plan_project_id=PROJECT_B1,
            now=now,
        )


def _seed_tenant(
    connection: psycopg.Connection[tuple[object, ...]],
    *,
    organization_id: str,
    user_id: str,
    organization_name: str,
    projects: tuple[tuple[str, str], ...],
    plan_id: str,
    plan_project_id: str,
    now: datetime,
) -> None:
    connection.execute("SELECT set_config('app.organization_id', %s, true)", (organization_id,))
    connection.execute(
        "INSERT INTO organizations (id, name, status, created_at) VALUES (%s, %s, 'ACTIVE', %s)",
        (organization_id, organization_name, now),
    )
    connection.execute(
        """
        INSERT INTO memberships (
            organization_id, user_id, roles, status, created_at, updated_at
        ) VALUES (%s, %s, %s, 'ACTIVE', %s, %s)
        """,
        (organization_id, user_id, ["researcher"], now, now),
    )
    connection.execute(
        """
        INSERT INTO external_identities (
            organization_id, user_id, issuer, external_subject, actor_type, created_at
        ) VALUES (%s, %s, %s, %s, 'human', %s)
        """,
        (organization_id, user_id, TEST_ISSUER, f"subject-{organization_id[-1]}", now),
    )
    for project_id, name in projects:
        connection.execute(
            """
            INSERT INTO projects (
                id, organization_id, name, profile, status, version, created_at, updated_at
            ) VALUES (%s, %s, %s, 'government', 'ACTIVE', 1, %s, %s)
            """,
            (project_id, organization_id, name, now, now),
        )
    connection.execute(
        """
        INSERT INTO research_plans (
            id, organization_id, project_id, version, question, status,
            approved_by, approved_at, created_at, updated_at
        ) VALUES (%s, %s, %s, 1, %s, 'APPROVED', %s, %s, %s, %s)
        """,
        (
            plan_id,
            organization_id,
            plan_project_id,
            "공공기관 AI 구매 원칙을 수립한다.",
            user_id,
            now,
            now,
            now,
        ),
    )
    connection.commit()
