"""PostgreSQL membership resolution behind tenant RLS."""

from __future__ import annotations

from uuid import UUID

import psycopg

from psr_mcp.auth.membership import ResolvedMembership
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.identity import ActorType, MembershipStatus, Role
from psr_mcp.storage.postgres.store import PgPool


class PostgresMembershipResolver:
    """Bind the untrusted organization hint to RLS, then verify exact membership."""

    def __init__(self, pool: PgPool) -> None:
        self._pool = pool

    async def resolve(
        self,
        *,
        issuer: str,
        external_subject: str,
        requested_organization_id: str,
    ) -> ResolvedMembership | None:
        try:
            organization_id = str(UUID(requested_organization_id))
        except ValueError:
            return None
        try:
            async with (
                self._pool.connection() as connection,
                connection.transaction(),
            ):
                await connection.execute(
                    "SELECT set_config('app.organization_id', %s, true)",
                    (organization_id,),
                )
                cursor = await connection.execute(
                    """
                        SELECT
                            identities.user_id::text AS subject_id,
                            memberships.roles,
                            memberships.status,
                            memberships.project_scope,
                            identities.actor_type,
                            COALESCE(
                                array_agg(membership_projects.project_id::text)
                                    FILTER (WHERE membership_projects.project_id IS NOT NULL),
                                ARRAY[]::text[]
                            ) AS project_ids
                        FROM external_identities AS identities
                        JOIN memberships
                          ON memberships.organization_id = identities.organization_id
                         AND memberships.user_id = identities.user_id
                        JOIN organizations
                          ON organizations.id = identities.organization_id
                        LEFT JOIN membership_projects
                          ON membership_projects.organization_id = memberships.organization_id
                         AND membership_projects.user_id = memberships.user_id
                        WHERE identities.organization_id = %s::uuid
                          AND identities.issuer = %s
                          AND identities.external_subject = %s
                          AND organizations.status = 'ACTIVE'
                          AND memberships.status = 'ACTIVE'
                        GROUP BY
                            identities.user_id,
                            memberships.roles,
                            memberships.status,
                            memberships.project_scope,
                            identities.actor_type
                        """,
                    (organization_id, issuer, external_subject),
                )
                row = await cursor.fetchone()
            if row is None:
                return None
            roles = frozenset(Role(value) for value in row["roles"])
            project_ids = (
                None
                if row["project_scope"] == "ALL"
                else frozenset(str(value) for value in row["project_ids"])
            )
            return ResolvedMembership(
                organization_id=organization_id,
                subject_id=str(row["subject_id"]),
                roles=roles,
                project_ids=project_ids,
                actor_type=ActorType(row["actor_type"]),
                status=MembershipStatus(row["status"]),
            )
        except (psycopg.Error, TypeError, ValueError) as error:
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "membership resolution is temporarily unavailable",
                retryable=True,
            ) from error
