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
