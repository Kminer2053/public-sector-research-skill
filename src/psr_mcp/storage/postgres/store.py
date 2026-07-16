"""Psycopg pool and UnitOfWork implementation."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import cast

from psycopg import AsyncConnection
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from psr_mcp.application.ports import (
    AuditRepository,
    JobRepository,
    PlanRepository,
    ProjectRepository,
    RunRepository,
)
from psr_mcp.storage.postgres.repositories import (
    PgConnection,
    PostgresAuditRepository,
    PostgresJobRepository,
    PostgresPlanRepository,
    PostgresProjectRepository,
    PostgresRunRepository,
    TransactionTenant,
)

PgPool = AsyncConnectionPool[PgConnection]


async def _configure_connection(connection: PgConnection) -> None:
    await connection.execute("SET TIME ZONE 'UTC'")
    await connection.execute("SET statement_timeout = '30s'")
    await connection.execute("SET lock_timeout = '5s'")
    await connection.commit()


async def _reset_connection(connection: PgConnection) -> None:
    if connection.info.transaction_status is not TransactionStatus.IDLE:
        await connection.rollback()


class PostgresStore:
    def __init__(
        self,
        conninfo: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 10.0,
    ) -> None:
        if not conninfo.strip():
            raise ValueError("PostgreSQL conninfo is required")
        self._pool = cast(
            PgPool,
            AsyncConnectionPool(
                conninfo,
                connection_class=AsyncConnection,
                kwargs={"row_factory": dict_row},
                min_size=min_size,
                max_size=max_size,
                timeout=timeout,
                open=False,
                configure=_configure_connection,
                reset=_reset_connection,
                name="psr-mcp",
            ),
        )

    @property
    def pool(self) -> PgPool:
        return self._pool

    async def open(self) -> None:
        await self._pool.open(wait=True)

    async def close(self) -> None:
        await self._pool.close()

    async def __aenter__(self) -> PostgresStore:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    def unit_of_work(self) -> PostgresUnitOfWork:
        return PostgresUnitOfWork(self._pool)


class PostgresUnitOfWork:
    def __init__(self, pool: PgPool) -> None:
        self._pool = pool
        self._connection_context: AbstractAsyncContextManager[PgConnection] | None = None
        self._connection: PgConnection | None = None
        self._tenant: TransactionTenant | None = None
        self._committed = False

    @property
    def projects(self) -> ProjectRepository:
        return PostgresProjectRepository(self._active_connection, self._active_tenant)

    @property
    def plans(self) -> PlanRepository:
        return PostgresPlanRepository(self._active_connection, self._active_tenant)

    @property
    def runs(self) -> RunRepository:
        return PostgresRunRepository(self._active_connection, self._active_tenant)

    @property
    def jobs(self) -> JobRepository:
        return PostgresJobRepository(self._active_connection, self._active_tenant)

    @property
    def audit(self) -> AuditRepository:
        return PostgresAuditRepository(self._active_connection, self._active_tenant)

    @property
    def _active_connection(self) -> PgConnection:
        if self._connection is None:
            raise RuntimeError("unit of work is not active")
        return self._connection

    @property
    def _active_tenant(self) -> TransactionTenant:
        if self._tenant is None:
            raise RuntimeError("unit of work is not active")
        return self._tenant

    async def __aenter__(self) -> PostgresUnitOfWork:
        if self._connection is not None:
            raise RuntimeError("unit of work is already active")
        context = self._pool.connection()
        self._connection_context = cast(AbstractAsyncContextManager[PgConnection], context)
        self._connection = await self._connection_context.__aenter__()
        self._tenant = TransactionTenant(self._connection)
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = self._connection_context
        try:
            if self._connection is not None and exc_type is None and not self._committed:
                await self._connection.rollback()
        finally:
            try:
                if context is not None:
                    await context.__aexit__(exc_type, exc_value, traceback)
            finally:
                self._tenant = None
                self._connection = None
                self._connection_context = None

    async def commit(self) -> None:
        await self._active_connection.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self._active_connection.rollback()
        self._committed = False

    async def backend_pid(self) -> int:
        """Return the checked-out backend PID for recovery diagnostics and fault tests."""
        cursor = await self._active_connection.execute("SELECT pg_backend_pid() AS pid")
        row = await cursor.fetchone()
        if row is None or not isinstance(row["pid"], int):
            raise RuntimeError("PostgreSQL backend PID is unavailable")
        return row["pid"]


async def current_tenant_values(store: PostgresStore, *, samples: int) -> list[str | None]:
    """Test/diagnostic helper proving pool connections don't retain tenant context."""
    values: list[str | None] = []
    for _ in range(samples):
        async with store.pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT NULLIF(current_setting('app.organization_id', true), '') AS tenant"
            )
            row = await cursor.fetchone()
            values.append(row["tenant"] if row is not None else None)
    return values
