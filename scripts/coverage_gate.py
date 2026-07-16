"""Enforce the separate Foundation coverage thresholds from VALIDATION_CRITERIA."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MIN_STATEMENT_PERCENT = 90.0
MIN_BRANCH_PERCENT = 85.0
MIN_CRITICAL_STATEMENT_PERCENT = 95.0
CRITICAL_PATH_PREFIXES = (
    "src/psr_mcp/application/",
    "src/psr_mcp/collectors/",
    "src/psr_mcp/domain/",
    "src/psr_mcp/ephemeral/",
    "src/psr_mcp/evidence/",
    "src/psr_mcp/parsers/",
    "src/psr_mcp/planner/",
    "src/psr_mcp/public/",
    "src/psr_mcp/search/",
)
CRITICAL_EXACT_PATHS = {
    "src/psr_mcp/auth/policy.py",
    "src/psr_mcp/config.py",
    "src/psr_mcp/mcp/http_policy.py",
}


def evaluate(payload: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    totals = _mapping(payload.get("totals"), "coverage totals")
    statement_percent = _percentage(totals, "covered_lines", "num_statements")
    branch_percent = _percentage(totals, "covered_branches", "num_branches")
    if statement_percent < MIN_STATEMENT_PERCENT:
        failures.append(
            f"overall statements {statement_percent:.2f}% < {MIN_STATEMENT_PERCENT:.2f}%"
        )
    if branch_percent < MIN_BRANCH_PERCENT:
        failures.append(f"overall branches {branch_percent:.2f}% < {MIN_BRANCH_PERCENT:.2f}%")

    files = _mapping(payload.get("files"), "coverage files")
    for path, record in sorted(files.items()):
        if not isinstance(path, str) or not _is_critical(path):
            continue
        summary = _mapping(_mapping(record, f"coverage file {path}").get("summary"), path)
        if _integer(summary.get("num_statements"), f"{path} num_statements") == 0:
            continue
        critical_percent = _percentage(summary, "covered_lines", "num_statements")
        if critical_percent < MIN_CRITICAL_STATEMENT_PERCENT:
            failures.append(
                f"critical module {path} statements {critical_percent:.2f}% "
                f"< {MIN_CRITICAL_STATEMENT_PERCENT:.2f}%"
            )
    return failures


def summary(payload: Mapping[str, Any]) -> dict[str, object]:
    totals = _mapping(payload.get("totals"), "coverage totals")
    return {
        "status": "pass",
        "statement_percent": round(_percentage(totals, "covered_lines", "num_statements"), 2),
        "branch_percent": round(_percentage(totals, "covered_branches", "num_branches"), 2),
        "critical_statement_percent_minimum": MIN_CRITICAL_STATEMENT_PERCENT,
    }


def _is_critical(path: str) -> bool:
    return path in CRITICAL_EXACT_PATHS or path.startswith(CRITICAL_PATH_PREFIXES)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _percentage(values: Mapping[str, Any], covered_key: str, total_key: str) -> float:
    covered = _integer(values.get(covered_key), covered_key)
    total = _integer(values.get(total_key), total_key)
    if covered > total or total == 0:
        raise ValueError(f"invalid coverage ratio: {covered_key}/{total_key}")
    return covered * 100.0 / total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.coverage_json.read_text())
        if not isinstance(payload, dict):
            raise ValueError("coverage document must be an object")
        failures = evaluate(payload)
        if failures:
            print(json.dumps({"status": "fail", "failures": failures}, sort_keys=True))
            return 1
        print(json.dumps(summary(payload), sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, ValueError):
        print(json.dumps({"status": "error", "message": "invalid coverage artifact"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
