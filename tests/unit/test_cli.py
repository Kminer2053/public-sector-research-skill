from __future__ import annotations

import json

import pytest

from psr_mcp.cli import main as cli
from psr_mcp.config import Settings
from psr_mcp.conformance import ConformanceError, ConformanceOptions


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
    assert all("remote Host conformance" not in value for value in payload["limitations"])


def test_doctor_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["doctor"]) == 0
    assert "foundation configuration: OK" in capsys.readouterr().out


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


def test_conformance_reads_bearer_from_environment_without_printing_it(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "conformance-secret-token"
    observed: list[ConformanceOptions] = []

    async def fake_conformance(options: ConformanceOptions) -> dict[str, object]:
        observed.append(options)
        return {"status": "PASS", "bearer_token_used": options.bearer_token is not None}

    monkeypatch.setenv("TEST_CONFORMANCE_TOKEN", token)
    monkeypatch.setattr(cli, "run_conformance", fake_conformance)
    assert (
        cli.main(
            [
                "conformance",
                "--endpoint",
                "https://research.example.gov/mcp",
                "--token-env",
                "TEST_CONFORMANCE_TOKEN",
                "--ca-bundle",
                "/tmp/institution-ca.pem",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert observed[0].bearer_token == token
    assert observed[0].ca_bundle == "/tmp/institution-ca.pem"
    assert token not in output
    assert json.loads(output)["status"] == "PASS"


def test_conformance_failure_is_redacted_and_has_exit_code_4(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failed_conformance(_options: ConformanceOptions) -> dict[str, object]:
        raise ConformanceError("sensitive remote detail")

    monkeypatch.setattr(cli, "run_conformance", failed_conformance)
    assert cli.main(["conformance", "--endpoint", "https://research.example.gov/mcp"]) == 4
    output = capsys.readouterr().out
    assert "conformance failed" in output
    assert "sensitive remote detail" not in output


def test_conformance_token_environment_name_is_validated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli.main(
            [
                "conformance",
                "--endpoint",
                "https://research.example.gov/mcp",
                "--token-env",
                "INVALID-NAME",
            ]
        )
        == 2
    )
    assert "configuration error" in capsys.readouterr().out


def test_conformance_token_environment_name_rejects_unicode_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli.main(
            [
                "conformance",
                "--endpoint",
                "https://research.example.gov/mcp",
                "--token-env",
                "비밀토큰",
            ]
        )
        == 2
    )
    assert "configuration error" in capsys.readouterr().out
