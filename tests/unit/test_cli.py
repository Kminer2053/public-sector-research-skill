from __future__ import annotations

import json

import pytest

from psr_mcp.cli import main as cli
from psr_mcp.config import Settings


def test_doctor_json_is_redacted(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PSR_PORT", raising=False)
    exit_code = cli.main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["settings"]["cursor_signing_key"] == "***"
    assert "in-memory storage" in payload["limitations"]
    assert "OAuth/remote conformance not validated" in payload["limitations"]


def test_doctor_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["doctor"]) == 0
    assert "Foundation development configuration: OK" in capsys.readouterr().out


def test_configuration_error_uses_exit_code_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PSR_PORT", "invalid")
    assert cli.main(["doctor"]) == 2
    assert "configuration error" in capsys.readouterr().out


def test_serve_command_uses_validated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[Settings] = []
    monkeypatch.setattr(cli, "_serve", called.append)

    assert cli.main(["serve", "mcp"]) == 0
    assert called[0].host == "127.0.0.1"


def test_console_serve_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[Settings] = []
    monkeypatch.setattr(cli, "_serve", called.append)

    assert cli.serve() == 0
    assert len(called) == 1


def test_interrupt_uses_conventional_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(_settings: Settings) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_serve", interrupted)
    assert cli.main(["serve", "mcp"]) == 130
    assert cli.serve() == 130


def test_database_upgrade_reads_url_from_environment_without_printing_it(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[tuple[str, str]] = []
    database_url = "postgresql://operator:secret@database.example/psr"
    monkeypatch.setenv("PSR_MIGRATION_DATABASE_URL", database_url)
    monkeypatch.setattr(
        cli,
        "migration_upgrade",
        lambda url, revision: called.append((url, revision)),
    )

    assert cli.main(["db", "upgrade"]) == 0
    assert called == [(database_url, "head")]
    assert database_url not in capsys.readouterr().out


def test_database_downgrade_requires_confirmation(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PSR_MIGRATION_DATABASE_URL", "postgresql://operator@database/psr")
    assert cli.main(["db", "downgrade"]) == 2
    assert "confirm-downgrade" in capsys.readouterr().out


def test_database_current_and_confirmed_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql://operator@database/psr"
    current_calls: list[str] = []
    downgrade_calls: list[tuple[str, str]] = []
    monkeypatch.setenv("PSR_MIGRATION_DATABASE_URL", database_url)
    monkeypatch.setattr(cli, "migration_current", current_calls.append)
    monkeypatch.setattr(
        cli,
        "migration_downgrade",
        lambda url, revision: downgrade_calls.append((url, revision)),
    )

    assert cli.main(["db", "current"]) == 0
    assert cli.main(["db", "downgrade", "--confirm-downgrade"]) == 0
    assert current_calls == [database_url]
    assert downgrade_calls == [(database_url, "-1")]
