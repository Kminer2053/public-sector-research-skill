"""Content-free MCP smoke probe used only by the Docker test stage."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from psr_mcp.conformance import PublicConformanceOptions, run_public_conformance


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="container-smoke")
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8000/mcp",
        help="loopback MCP endpoint inside the test container",
    )
    parser.add_argument(
        "--ephemeral-root",
        default="/var/lib/psr/ephemeral",
        help="ephemeral root that must be empty after the quick result is returned",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = asyncio.run(
        run_public_conformance(
            PublicConformanceOptions(
                endpoint=args.endpoint,
                release_gate=False,
                verify_feedback_submission=True,
            )
        )
    )
    _require_test_result(result)
    _require_empty_ephemeral_root(Path(args.ephemeral_root))
    safe_summary = {
        "status": result["status"],
        "source_discovery": result["source_discovery"],
        "citation_count": result["citation_count"],
        "purge_verified": result["purge_verified"],
        "feedback_submission_verified": result["feedback_submission_verified"],
        "release_gate_checked": result["release_gate_checked"],
        "reconnect_verified": result["reconnect_verified"],
        "ephemeral_root_empty": True,
    }
    print(json.dumps(safe_summary, sort_keys=True))
    return 0


def _require_test_result(result: dict[str, object]) -> None:
    if result.get("status") != "PASS":
        raise RuntimeError("container MCP smoke did not pass")
    if result.get("source_discovery") != "development_fixture":
        raise RuntimeError("container smoke must use only the development fixture")
    if result.get("release_gate_checked") is not False:
        raise RuntimeError("container fixture smoke must not be reported as a release gate")
    for field in (
        "purge_verified",
        "feedback_submission_verified",
        "reconnect_verified",
    ):
        if result.get(field) is not True:
            raise RuntimeError(f"container MCP smoke failed required check: {field}")


def _require_empty_ephemeral_root(root: Path) -> None:
    if not root.is_dir():
        raise RuntimeError("container ephemeral root is unavailable")
    if next(root.iterdir(), None) is not None:
        raise RuntimeError("container ephemeral root retained workspace content")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
