from __future__ import annotations

import pytest

from psr_mcp.storage.migrations import runner


def test_migration_config_normalizes_postgresql_scheme() -> None:
    config = runner.migration_config("postgresql://operator@example.test/psr")
    assert config.get_main_option("sqlalchemy.url") == (
        "postgresql+psycopg://operator@example.test/psr"
    )
    script_location = config.get_main_option("script_location")
    assert script_location is not None
    assert script_location.endswith("storage/migrations/alembic")


@pytest.mark.parametrize("database_url", ["", "sqlite:///test.db", "mysql://example/test"])
def test_migration_config_rejects_invalid_url(database_url: str) -> None:
    with pytest.raises(ValueError):
        runner.migration_config(database_url)


def test_migration_commands_use_programmatic_config(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "alembic.command.upgrade",
        lambda config, revision: calls.append((config.get_main_option("sqlalchemy.url"), revision)),
    )
    monkeypatch.setattr(
        "alembic.command.downgrade",
        lambda config, revision: calls.append((config.get_main_option("sqlalchemy.url"), revision)),
    )
    monkeypatch.setattr(
        "alembic.command.current",
        lambda config, verbose: calls.append(
            (config.get_main_option("sqlalchemy.url"), str(verbose))
        ),
    )

    url = "postgresql+psycopg://operator@example.test/psr"
    runner.upgrade(url, "head")
    runner.downgrade(url, "base")
    runner.current(url)
    assert calls == [(url, "head"), (url, "base"), (url, "False")]
