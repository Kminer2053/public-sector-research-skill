"""Programmatic Alembic runner without a repository-local secret-bearing ini file."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config(database_url: str) -> Config:
    if not database_url.strip():
        raise ValueError("database_url is required")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
    config.set_main_option("sqlalchemy.url", _sqlalchemy_url(database_url).replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def upgrade(database_url: str, revision: str = "head") -> None:
    command.upgrade(migration_config(database_url), revision)


def downgrade(database_url: str, revision: str = "base") -> None:
    command.downgrade(migration_config(database_url), revision)


def current(database_url: str) -> None:
    command.current(migration_config(database_url), verbose=False)


def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    raise ValueError("database_url must use a PostgreSQL scheme")
