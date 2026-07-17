"""Stable JSON-oriented CLI used by Agent Skills and humans."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from psr_core import __version__
from psr_core.planner import build_plan
from psr_core.profiles import list_profiles, load_profile
from psr_core.storage import (
    ProjectNotInitializedError,
    ProjectStore,
    RecordNotFoundError,
)
from psr_core.workflow import execute_run, load_sources, rebuild_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psr")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--project",
        default=".",
        help="project directory containing .psr (default: current directory)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    project = commands.add_parser("project", help="manage a local research project")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    init = project_commands.add_parser("init", help="initialize local SQLite and evidence files")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--name", required=True)

    research = commands.add_parser("research", help="plan and execute research")
    research_commands = research.add_subparsers(dest="research_command", required=True)
    plan = research_commands.add_parser("plan", help="create a reviewable research plan")
    plan.add_argument("question")
    plan.add_argument("--as-of", default=date.today().isoformat())
    plan.add_argument("--jurisdiction", default="KR")
    plan.add_argument("--profile", default="government")
    plan.add_argument("--max-sources", type=int, default=15)
    plan.add_argument("--max-bytes", type=int, default=50 * 1024 * 1024)
    plan.add_argument("--timeout", type=float, default=120.0)
    plan.add_argument(
        "--include-track",
        action="append",
        default=[],
        help="repeatable track ID to activate even when its keywords do not match",
    )
    plan.add_argument(
        "--exclude-track",
        action="append",
        default=[],
        help="repeatable track ID to remove from this plan",
    )
    run = research_commands.add_parser("run", help="collect supplied sources and build evidence")
    run.add_argument("run_id")
    run.add_argument(
        "--source",
        action="append",
        default=[],
        help="repeatable TRACK_ID=URL_OR_PATH source",
    )
    run.add_argument("--sources-file", help="JSON array or JSONL source manifest")
    run.add_argument("--refresh", action="store_true")
    run.add_argument("--reuse-max-age-days", type=int, default=7)
    run.add_argument("--max-workers", type=int, default=4)

    evidence = commands.add_parser("evidence", help="inspect stored evidence")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_list = evidence_commands.add_parser("list")
    evidence_list.add_argument("--run-id")
    evidence_show = evidence_commands.add_parser("show")
    evidence_show.add_argument("evidence_id")

    report = commands.add_parser("report", help="rebuild a stored report")
    report_commands = report.add_subparsers(dest="report_command", required=True)
    report_build = report_commands.add_parser("build")
    report_build.add_argument("run_id")
    report_build.add_argument(
        "--format",
        choices=("md", "html", "all"),
        default="all",
        help="report format to write (default: all)",
    )
    report_build.add_argument(
        "--brief-file",
        help="validated brief.json with citation-linked facts, inferences, and recommendations",
    )

    memory = commands.add_parser("memory", help="search local stored passages")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    memory_search = memory_commands.add_parser("search")
    memory_search.add_argument("query")
    memory_search.add_argument("--limit", type=int, default=20)

    profile = commands.add_parser("profile", help="inspect project research profiles")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_commands.add_parser("list")

    commands.add_parser("doctor", help="validate the local runtime and project")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "project" and args.project_command == "init":
            store = ProjectStore.initialize(Path(args.path), name=args.name)
            return _emit(
                {
                    "status": "ok",
                    "project_root": str(store.project_root),
                    "storage_root": str(store.root),
                    "database": str(store.db_path),
                }
            )
        store = ProjectStore(Path(args.project))
        store.require_initialized()
        if args.command == "research" and args.research_command == "plan":
            profile = load_profile(store.profile_dir, args.profile)
            plan = build_plan(
                question=args.question,
                as_of_date=date.fromisoformat(args.as_of),
                jurisdiction=args.jurisdiction,
                profile=profile,
                max_sources=args.max_sources,
                max_bytes=args.max_bytes,
                timeout_seconds=args.timeout,
                include_tracks=args.include_track,
                exclude_tracks=args.exclude_track,
            )
            path = store.save_plan(plan)
            return _emit(
                {
                    "status": "PLANNED",
                    "run_id": plan.id,
                    "plan_path": str(path),
                    "plan": plan.to_dict(),
                }
            )
        if args.command == "research" and args.research_command == "run":
            plan = store.get_plan(args.run_id)
            sources = load_sources(
                inline_sources=args.source,
                sources_file=args.sources_file,
            )
            result = execute_run(
                store=store,
                plan=plan,
                sources=sources,
                refresh=args.refresh,
                reuse_max_age_days=args.reuse_max_age_days,
                max_workers=args.max_workers,
            )
            return _emit(result.to_dict())
        if args.command == "evidence" and args.evidence_command == "list":
            return _emit(
                {
                    "status": "ok",
                    "items": store.list_citations(run_id=args.run_id),
                }
            )
        if args.command == "evidence" and args.evidence_command == "show":
            return _emit(
                {
                    "status": "ok",
                    "item": store.get_citation(args.evidence_id),
                }
            )
        if args.command == "report" and args.report_command == "build":
            return _emit(
                {
                    "status": "ok",
                    **rebuild_report(
                        store,
                        args.run_id,
                        output_format=args.format,
                        brief_file=args.brief_file,
                    ),
                }
            )
        if args.command == "memory" and args.memory_command == "search":
            if args.limit < 1 or args.limit > 100:
                raise ValueError("--limit must be 1..100")
            return _emit(
                {
                    "status": "ok",
                    "items": store.search_memory(args.query, limit=args.limit),
                }
            )
        if args.command == "profile" and args.profile_command == "list":
            return _emit(
                {
                    "status": "ok",
                    "items": list_profiles(store.profile_dir),
                }
            )
        if args.command == "doctor":
            return _emit(
                {
                    "status": "ok",
                    "version": __version__,
                    "python": sys.version.split()[0],
                    "project_root": str(store.project_root),
                    "database": str(store.db_path),
                    "profiles": list_profiles(store.profile_dir),
                    "network_policy": {
                        "http_https_only": True,
                        "private_addresses_blocked": True,
                        "robots_respected": True,
                        "nonstandard_ports_blocked": True,
                    },
                    "storage_policy": {
                        "local_only": True,
                        "server_upload": False,
                    },
                }
            )
    except (
        ValueError,
        ProjectNotInitializedError,
        RecordNotFoundError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        _emit_error("INPUT_ERROR", str(error))
        return 2
    except KeyboardInterrupt:
        _emit_error("INTERRUPTED", "operation interrupted")
        return 130
    except Exception as error:
        _emit_error("INTERNAL_ERROR", f"operation failed safely: {error}")
        return 3
    _emit_error("COMMAND_ERROR", "unhandled command")
    return 10


def _emit(payload: Dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _emit_error(code: str, message: str) -> None:
    print(
        json.dumps(
            {"status": "error", "code": code, "message": message},
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
