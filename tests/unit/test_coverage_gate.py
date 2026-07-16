from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "coverage_gate.py"


def _payload(*, lines: int = 95, branches: int = 86, critical_lines: int = 95) -> dict[str, object]:
    return {
        "totals": {
            "covered_lines": lines,
            "num_statements": 100,
            "covered_branches": branches,
            "num_branches": 100,
        },
        "files": {
            "src/psr_mcp/application/service.py": {
                "summary": {
                    "covered_lines": critical_lines,
                    "num_statements": 100,
                }
            },
            "src/psr_mcp/conformance.py": {"summary": {"covered_lines": 1, "num_statements": 100}},
        },
    }


def _run(tmp_path: Path, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    artifact = tmp_path / "coverage.json"
    artifact.write_text(json.dumps(payload))
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--coverage-json", str(artifact)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_coverage_gate_passes_each_independent_threshold(tmp_path: Path) -> None:
    result = _run(tmp_path, _payload())

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "status": "pass",
        "statement_percent": 95.0,
        "branch_percent": 86.0,
        "critical_statement_percent_minimum": 95.0,
    }


@pytest.mark.parametrize(
    "payload, fragment",
    [
        (_payload(lines=89), "overall statements"),
        (_payload(branches=84), "overall branches"),
        (_payload(critical_lines=94), "critical module"),
    ],
)
def test_coverage_gate_rejects_each_threshold_independently(
    tmp_path: Path, payload: dict[str, object], fragment: str
) -> None:
    result = _run(tmp_path, payload)

    assert result.returncode == 1
    assert fragment in result.stdout


def test_coverage_gate_rejects_malformed_counts(tmp_path: Path) -> None:
    payload = _payload()
    totals = payload["totals"]
    assert isinstance(totals, dict)
    totals["covered_lines"] = 101

    result = _run(tmp_path, payload)

    assert result.returncode == 2
    assert "invalid coverage artifact" in result.stdout
