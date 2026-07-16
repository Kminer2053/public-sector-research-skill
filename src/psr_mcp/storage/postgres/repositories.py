"""Parameterized PostgreSQL repositories sharing one transaction tenant binding."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg import AsyncConnection, errors
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from psr_mcp.application.ports import (
    AuditRepository,
    JobRepository,
    PlanRepository,
    ProjectRepository,
    RunRepository,
)
from psr_mcp.domain.audit import AuditEvent
from psr_mcp.domain.errors import DomainError, ErrorCode, invalid
from psr_mcp.domain.projects import Project
from psr_mcp.domain.research import Job, ResearchPlan, ResearchRun
from psr_mcp.storage.postgres.mappers import (
    job_from_row,
    plan_from_row,
    project_from_row,
    run_from_row,
)

PgConnection = AsyncConnection[DictRow]


class TransactionTenant:
    def __init__(self, connection: PgConnection) -> None:
        self._connection = connection
        self._organization_id: str | None = None

    async def bind(self, organization_id: str) -> str:
        try:
            normalized = str(UUID(organization_id))
        except ValueError as error:
            raise invalid("organization_id must be a UUID", field="organization_id") from error
        if self._organization_id is not None and self._organization_id != normalized:
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the requested target was not found or is not accessible",
            )
        if self._organization_id is None:
            await self._connection.execute(
                "SELECT set_config('app.organization_id', %s, true)",
                (normalized,),
            )
            self._organization_id = normalized
        return normalized


class PostgresProjectRepository(ProjectRepository):
    def __init__(self, connection: PgConnection, tenant: TransactionTenant) -> None:
        self._connection = connection
        self._tenant = tenant

    async def list_page(
        self,
        organization_id: str,
        *,
        project_ids: frozenset[str] | None,
        after: tuple[datetime, str] | None,
        limit: int,
    ) -> list[Project]:
        tenant = await self._tenant.bind(organization_id)
        query = """
            SELECT id, organization_id, name, profile, status, version, created_at, updated_at
            FROM projects
            WHERE organization_id = %s::uuid
        """
        params: list[object] = [tenant]
        if project_ids is not None:
            query += " AND id = ANY(%s::uuid[])"
            params.append(list(project_ids))
        if after is not None:
            query += " AND (created_at, id) > (%s, %s::uuid)"
            params.extend(after)
        query += " ORDER BY created_at, id LIMIT %s"
        params.append(limit)
        cursor = await self._connection.execute(query, params)
        return [project_from_row(row) async for row in cursor]

    async def get(self, organization_id: str, project_id: str) -> Project | None:
        tenant = await self._tenant.bind(organization_id)
        cursor = await self._connection.execute(
            """
            SELECT id, organization_id, name, profile, status, version, created_at, updated_at
            FROM projects
            WHERE organization_id = %s::uuid AND id = %s::uuid
            """,
            (tenant, project_id),
        )
        row = await cursor.fetchone()
        return project_from_row(row) if row is not None else None


class PostgresPlanRepository(PlanRepository):
    def __init__(self, connection: PgConnection, tenant: TransactionTenant) -> None:
        self._connection = connection
        self._tenant = tenant

    async def get(self, organization_id: str, plan_id: str) -> ResearchPlan | None:
        tenant = await self._tenant.bind(organization_id)
        cursor = await self._connection.execute(
            """
            SELECT id, organization_id, project_id, version, question, status,
                   approved_by, approved_at
            FROM research_plans
            WHERE organization_id = %s::uuid AND id = %s::uuid
            ORDER BY version DESC
            LIMIT 1
            """,
            (tenant, plan_id),
        )
        row = await cursor.fetchone()
        return plan_from_row(row) if row is not None else None


class PostgresRunRepository(RunRepository):
    def __init__(self, connection: PgConnection, tenant: TransactionTenant) -> None:
        self._connection = connection
        self._tenant = tenant

    async def get(self, organization_id: str, run_id: str) -> ResearchRun | None:
        tenant = await self._tenant.bind(organization_id)
        cursor = await self._connection.execute(
            "SELECT * FROM research_runs WHERE organization_id = %s::uuid AND id = %s::uuid",
            (tenant, run_id),
        )
        row = await cursor.fetchone()
        return run_from_row(row) if row is not None else None

    async def find_idempotent(
        self,
        organization_id: str,
        project_id: str,
        initiated_by: str,
        idempotency_key: str,
    ) -> ResearchRun | None:
        tenant = await self._tenant.bind(organization_id)
        lock_key = "\x1f".join((tenant, project_id, initiated_by, idempotency_key))
        await self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (lock_key,),
        )
        cursor = await self._connection.execute(
            """
            SELECT * FROM research_runs
            WHERE organization_id = %s::uuid
              AND project_id = %s::uuid
              AND initiated_by = %s::uuid
              AND idempotency_key = %s
            """,
            (tenant, project_id, initiated_by, idempotency_key),
        )
        row = await cursor.fetchone()
        return run_from_row(row) if row is not None else None

    async def add(self, run: ResearchRun) -> None:
        await self._tenant.bind(run.organization_id)
        try:
            await self._connection.execute(
                """
                INSERT INTO research_runs (
                    id, organization_id, project_id, plan_id, plan_version, initiated_by,
                    status, version, idempotency_key, request_fingerprint, failure_code,
                    cancel_reason, cancellation_requested_at, created_at, updated_at,
                    started_at, finished_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s::uuid,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    run.id,
                    run.organization_id,
                    run.project_id,
                    run.plan_id,
                    run.plan_version,
                    run.initiated_by,
                    run.status.value,
                    run.version,
                    run.idempotency_key,
                    run.request_fingerprint,
                    run.failure_code,
                    run.cancel_reason,
                    run.cancellation_requested_at,
                    run.created_at,
                    run.updated_at,
                    run.started_at,
                    run.finished_at,
                ),
            )
        except errors.UniqueViolation as error:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "run identifier or idempotency key already exists",
            ) from error

    async def update(self, run: ResearchRun, *, expected_version: int) -> None:
        tenant = await self._tenant.bind(run.organization_id)
        cursor = await self._connection.execute(
            """
            UPDATE research_runs
            SET status = %s, version = %s, failure_code = %s, cancel_reason = %s,
                cancellation_requested_at = %s, updated_at = %s, started_at = %s,
                finished_at = %s
            WHERE organization_id = %s::uuid AND id = %s::uuid AND version = %s
            """,
            (
                run.status.value,
                run.version,
                run.failure_code,
                run.cancel_reason,
                run.cancellation_requested_at,
                run.updated_at,
                run.started_at,
                run.finished_at,
                tenant,
                run.id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise DomainError(
                ErrorCode.VERSION_CONFLICT,
                "run version changed; reload before retrying",
                retryable=True,
            )


class PostgresJobRepository(JobRepository):
    def __init__(self, connection: PgConnection, tenant: TransactionTenant) -> None:
        self._connection = connection
        self._tenant = tenant

    async def get_by_run(self, organization_id: str, run_id: str) -> Job | None:
        tenant = await self._tenant.bind(organization_id)
        cursor = await self._connection.execute(
            """
            SELECT * FROM jobs
            WHERE organization_id = %s::uuid AND run_id = %s::uuid
            FOR UPDATE
            """,
            (tenant, run_id),
        )
        row = await cursor.fetchone()
        return job_from_row(row) if row is not None else None

    async def list_claimable(self, organization_id: str, *, now: datetime, limit: int) -> list[Job]:
        tenant = await self._tenant.bind(organization_id)
        cursor = await self._connection.execute(
            """
            SELECT * FROM jobs
            WHERE organization_id = %s::uuid
              AND available_at <= %s
              AND (
                  state = 'QUEUED'
                  OR (state = 'RUNNING' AND lease_expires_at <= %s)
              )
            ORDER BY available_at, created_at, id
            FOR UPDATE SKIP LOCKED
            LIMIT %s
            """,
            (tenant, now, now, limit),
        )
        return [job_from_row(row) async for row in cursor]

    async def add(self, job: Job) -> None:
        await self._tenant.bind(job.organization_id)
        try:
            await self._connection.execute(
                """
                INSERT INTO jobs (
                    id, organization_id, project_id, run_id, state, available_at,
                    attempts, max_attempts, lease_owner, lease_expires_at,
                    cancel_requested_at, created_at, updated_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    job.id,
                    job.organization_id,
                    job.project_id,
                    job.run_id,
                    job.state.value,
                    job.available_at,
                    job.attempts,
                    job.max_attempts,
                    job.lease_owner,
                    job.lease_expires_at,
                    job.cancel_requested_at,
                    job.created_at,
                    job.updated_at,
                ),
            )
        except errors.UniqueViolation as error:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT, "job already exists for run"
            ) from error

    async def update(self, job: Job) -> None:
        tenant = await self._tenant.bind(job.organization_id)
        cursor = await self._connection.execute(
            """
            UPDATE jobs
            SET state = %s, available_at = %s, attempts = %s, max_attempts = %s,
                lease_owner = %s, lease_expires_at = %s, cancel_requested_at = %s,
                updated_at = %s
            WHERE organization_id = %s::uuid AND id = %s::uuid
            """,
            (
                job.state.value,
                job.available_at,
                job.attempts,
                job.max_attempts,
                job.lease_owner,
                job.lease_expires_at,
                job.cancel_requested_at,
                job.updated_at,
                tenant,
                job.id,
            ),
        )
        if cursor.rowcount != 1:
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the requested target was not found or is not accessible",
            )


class PostgresAuditRepository(AuditRepository):
    def __init__(self, connection: PgConnection, tenant: TransactionTenant) -> None:
        self._connection = connection
        self._tenant = tenant

    async def add(self, event: AuditEvent) -> None:
        await self._tenant.bind(event.organization_id)
        try:
            await self._connection.execute(
                """
                INSERT INTO audit_events (
                    id, organization_id, project_id, occurred_at, actor_subject_id,
                    actor_type, operation, target_type, target_id, outcome,
                    operation_id, reason_code, metadata_json
                ) VALUES (
                    %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    event.id,
                    event.organization_id,
                    event.project_id,
                    event.occurred_at,
                    event.actor_subject_id,
                    event.actor_type.value,
                    event.operation,
                    event.target_type,
                    event.target_id,
                    event.outcome.value,
                    event.operation_id,
                    event.reason_code,
                    Jsonb(event.metadata),
                ),
            )
        except errors.UniqueViolation as error:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "audit event identifier already exists",
            ) from error
