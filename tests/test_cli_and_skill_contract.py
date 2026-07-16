from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from psr_core import cli

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "skills" / "public-sector-research" / "scripts" / "psr.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_end_to_end(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialized = _run("project", "init", str(project), "--name", "cli")
    assert initialized.returncode == 0
    assert json.loads(initialized.stdout)["status"] == "ok"

    planned = _run(
        "--project",
        str(project),
        "research",
        "plan",
        "공공기관 인공지능 정책 관련 공식자료를 조사한다",
        "--as-of",
        "2026-07-17",
    )
    assert planned.returncode == 0
    run_id = json.loads(planned.stdout)["run_id"]

    source = tmp_path / "policy.html"
    source.write_text(
        "<html><p>공공기관 정부 가이드는 책임성과 위험관리를 요구한다.</p></html>",
        encoding="utf-8",
    )
    executed = _run(
        "--project",
        str(project),
        "research",
        "run",
        run_id,
        "--source",
        f"government-policy={source}",
    )
    assert executed.returncode == 0
    output = json.loads(executed.stdout)
    assert output["status"] == "PARTIAL"
    assert Path(output["report_path"]).exists()

    listed = _run(
        "--project",
        str(project),
        "evidence",
        "list",
        "--run-id",
        run_id,
    )
    assert listed.returncode == 0
    assert json.loads(listed.stdout)["items"]

    doctor = _run("--project", str(project), "doctor")
    assert doctor.returncode == 0
    assert json.loads(doctor.stdout)["storage_policy"]["local_only"] is True


def test_cli_uninitialized_project_returns_json_error(tmp_path: Path) -> None:
    result = _run("--project", str(tmp_path), "doctor")

    assert result.returncode == 2
    payload = json.loads(result.stderr)
    assert payload["status"] == "error"
    assert payload["code"] == "INPUT_ERROR"


def test_cli_commands_in_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "project"
    assert cli.main(["project", "init", str(project), "--name", "direct"]) == 0
    capsys.readouterr()

    assert (
        cli.main(
            [
                "--project",
                str(project),
                "research",
                "plan",
                "공공기관 인공지능 정책 관련 공식자료를 조사한다",
                "--as-of",
                "2026-07-17",
            ]
        )
        == 0
    )
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    source = tmp_path / "policy.html"
    source.write_text(
        "<html><p>공공기관 정부 가이드는 책임성과 위험관리를 요구한다.</p></html>",
        encoding="utf-8",
    )
    assert (
        cli.main(
            [
                "--project",
                str(project),
                "research",
                "run",
                run_id,
                "--source",
                f"government-policy={source}",
            ]
        )
        == 0
    )
    run_output = json.loads(capsys.readouterr().out)
    evidence_id = run_output["citations"][0]["id"]

    commands = [
        ["--project", str(project), "evidence", "list", "--run-id", run_id],
        ["--project", str(project), "evidence", "show", evidence_id],
        ["--project", str(project), "memory", "search", "위험관리"],
        ["--project", str(project), "report", "build", run_id],
        ["--project", str(project), "profile", "list"],
        ["--project", str(project), "doctor"],
    ]
    for command in commands:
        assert cli.main(command) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "ok"

    assert (
        cli.main(
            [
                "--project",
                str(project),
                "memory",
                "search",
                "x",
                "--limit",
                "0",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["code"] == "INPUT_ERROR"
    assert cli.main(["--project", str(project), "evidence", "show", "missing"]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "INPUT_ERROR"


def test_cli_internal_error_is_content_safe(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    assert cli.main(["project", "init", str(project), "--name", "error"]) == 0
    capsys.readouterr()

    def fail_profiles(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "list_profiles", fail_profiles)

    assert cli.main(["--project", str(project), "profile", "list"]) == 3
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == "INTERNAL_ERROR"
    assert "boom" in payload["message"]


def test_skill_and_host_metadata_contract() -> None:
    skill = (
        REPOSITORY
        / "skills"
        / "public-sector-research"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert skill.startswith("---\nname: public-sector-research\n")
    assert "description:" in skill.split("---", 2)[1]
    assert "Codex 전용" not in skill

    openai = (
        REPOSITORY
        / "skills"
        / "public-sector-research"
        / "agents"
        / "openai.yaml"
    ).read_text(encoding="utf-8")
    assert "$public-sector-research" in openai

    marketplace = json.loads(
        (REPOSITORY / ".claude-plugin" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )
    plugin = marketplace["plugins"][0]
    assert plugin["skills"] == ["./skills/public-sector-research"]
    assert plugin["name"] == "public-sector-research"
