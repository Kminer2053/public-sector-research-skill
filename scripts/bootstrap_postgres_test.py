"""Create isolated PostgreSQL roles/database for CI integration tests."""

from __future__ import annotations

import json
import os
import re

import psycopg
from psycopg import sql


def main() -> int:
    admin_url = _required_env("PSR_TEST_ADMIN_DATABASE_URL")
    owner_role = _safe_identifier(os.getenv("PSR_TEST_OWNER_ROLE", "psr_test_owner"))
    runtime_role = _safe_identifier(os.getenv("PSR_TEST_RUNTIME_ROLE", "psr_test_runtime"))
    database = _safe_identifier(os.getenv("PSR_TEST_DATABASE", "psr_test"))
    password = _required_env("PSR_TEST_ROLE_PASSWORD")

    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )
        _ensure_role(connection, owner_role, password)
        _ensure_role(connection, runtime_role, password)
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database),
                sql.Identifier(owner_role),
            )
        )

    print(
        json.dumps(
            {
                "database": database,
                "owner_role": owner_role,
                "runtime_role": runtime_role,
                "status": "ready",
            },
            sort_keys=True,
        )
    )
    return 0


def _ensure_role(
    connection: psycopg.Connection[tuple[object, ...]], role: str, password: str
) -> None:
    exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    if exists is None:
        connection.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                "NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(sql.Identifier(role), sql.Literal(password))
        )
    else:
        connection.execute(
            sql.SQL(
                "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                "NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(sql.Identifier(role), sql.Literal(password))
        )


def _safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("test database identifiers must be simple SQL identifiers")
    return value


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
