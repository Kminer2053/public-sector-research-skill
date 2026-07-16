from __future__ import annotations

import psycopg
import pytest

from psr_mcp.storage.postgres import PostgresMembershipResolver, PostgresStore

from .conftest import (
    ORG_A,
    ORG_B,
    PROJECT_A1,
    TEST_ISSUER,
    USER_A,
    PostgresUrls,
)


@pytest.mark.postgres
@pytest.mark.anyio
async def test_exact_external_identity_resolves_internal_membership(
    postgres_store: PostgresStore,
) -> None:
    resolver = PostgresMembershipResolver(postgres_store.pool)
    result = await resolver.resolve(
        issuer=TEST_ISSUER,
        external_subject="subject-a",
        requested_organization_id=ORG_A,
    )

    assert result is not None
    assert result.organization_id == ORG_A
    assert result.subject_id == USER_A
    assert {role.value for role in result.roles} == {"researcher"}
    assert result.project_ids is None


@pytest.mark.postgres
@pytest.mark.anyio
@pytest.mark.parametrize(
    "issuer, subject, organization_id",
    [
        (TEST_ISSUER, "subject-a", ORG_B),
        (TEST_ISSUER, "subject-b", ORG_A),
        ("https://other-idp.example.gov", "subject-a", ORG_A),
        (TEST_ISSUER, "subject-a", "not-a-uuid"),
    ],
)
async def test_cross_org_or_identity_claim_manipulation_is_denied(
    postgres_store: PostgresStore,
    issuer: str,
    subject: str,
    organization_id: str,
) -> None:
    resolver = PostgresMembershipResolver(postgres_store.pool)
    assert (
        await resolver.resolve(
            issuer=issuer,
            external_subject=subject,
            requested_organization_id=organization_id,
        )
        is None
    )


@pytest.mark.postgres
@pytest.mark.anyio
async def test_revoked_membership_is_not_resolved(
    postgres_store: PostgresStore,
    seeded_postgres: PostgresUrls,
) -> None:
    with psycopg.connect(seeded_postgres.owner) as connection:
        connection.execute("SELECT set_config('app.organization_id', %s, true)", (ORG_A,))
        connection.execute(
            "UPDATE memberships SET status = 'REVOKED' WHERE organization_id = %s",
            (ORG_A,),
        )
    resolver = PostgresMembershipResolver(postgres_store.pool)
    assert (
        await resolver.resolve(
            issuer=TEST_ISSUER,
            external_subject="subject-a",
            requested_organization_id=ORG_A,
        )
        is None
    )


@pytest.mark.postgres
@pytest.mark.anyio
async def test_restricted_membership_returns_only_explicit_projects(
    postgres_store: PostgresStore,
    seeded_postgres: PostgresUrls,
) -> None:
    with psycopg.connect(seeded_postgres.owner) as connection:
        connection.execute("SELECT set_config('app.organization_id', %s, true)", (ORG_A,))
        connection.execute(
            """
            UPDATE memberships
               SET project_scope = 'RESTRICTED'
             WHERE organization_id = %s AND user_id = %s
            """,
            (ORG_A, USER_A),
        )
        connection.execute(
            """
            INSERT INTO membership_projects (organization_id, user_id, project_id)
            VALUES (%s, %s, %s)
            """,
            (ORG_A, USER_A, PROJECT_A1),
        )
    resolver = PostgresMembershipResolver(postgres_store.pool)
    result = await resolver.resolve(
        issuer=TEST_ISSUER,
        external_subject="subject-a",
        requested_organization_id=ORG_A,
    )
    assert result is not None
    assert result.project_ids == frozenset({PROJECT_A1})


@pytest.mark.postgres
@pytest.mark.anyio
async def test_membership_resolution_does_not_leak_tenant_context(
    postgres_store: PostgresStore,
) -> None:
    resolver = PostgresMembershipResolver(postgres_store.pool)
    assert (
        await resolver.resolve(
            issuer=TEST_ISSUER,
            external_subject="subject-a",
            requested_organization_id=ORG_A,
        )
        is not None
    )
    async with postgres_store.pool.connection() as connection:
        context = await connection.execute(
            "SELECT current_setting('app.organization_id', true) AS organization_id"
        )
        row = await context.fetchone()
        identities = await connection.execute("SELECT count(*) AS count FROM external_identities")
        identity_count = await identities.fetchone()
    assert row is not None and row["organization_id"] in {None, ""}
    assert identity_count is not None and identity_count["count"] == 0


@pytest.mark.postgres
def test_runtime_role_cannot_read_global_users(seeded_postgres: PostgresUrls) -> None:
    with (
        psycopg.connect(seeded_postgres.runtime) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("SELECT * FROM users").fetchall()
