"""Operator and development CLI for Foundation and Public Preview modes."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections.abc import Sequence

import psycopg
import uvicorn
from sqlalchemy.exc import SQLAlchemyError

from psr_mcp import __version__
from psr_mcp.bootstrap import build_container
from psr_mcp.config import SearchProviderMode, ServiceMode, Settings
from psr_mcp.conformance import ConformanceError, ConformanceOptions, run_conformance
from psr_mcp.mcp.server import create_http_app
from psr_mcp.storage.migrations.runner import current as migration_current
from psr_mcp.storage.migrations.runner import downgrade as migration_downgrade
from psr_mcp.storage.migrations.runner import upgrade as migration_upgrade


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psrctl")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="validate and print redacted configuration")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    serve_parser = commands.add_parser("serve", help="run the configured MCP server")
    serve_parser.add_argument("service", choices=["mcp"])
    database = commands.add_parser("db", help="run operator-only PostgreSQL migrations")
    database.add_argument("action", choices=["current", "upgrade", "downgrade"])
    database.add_argument("--revision")
    database.add_argument("--confirm-downgrade", action="store_true")
    conformance = commands.add_parser(
        "conformance", help="probe a remote MCP endpoint with the official SDK client"
    )
    conformance.add_argument("--endpoint", required=True)
    conformance.add_argument("--token-env", default="PSR_CONFORMANCE_BEARER_TOKEN")
    conformance.add_argument("--project-id")
    conformance.add_argument("--approved-plan-id")
    conformance.add_argument("--idempotency-key", default="conformance-request-0001")
    conformance.add_argument("--timeout", type=float, default=30.0)
    conformance.add_argument(
        "--ca-bundle",
        help="PEM CA bundle for an institution-managed HTTPS endpoint",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "db":
            return _database_command(
                action=args.action,
                revision=args.revision,
                confirm_downgrade=args.confirm_downgrade,
            )
        if args.command == "conformance":
            return _conformance_command(
                endpoint=args.endpoint,
                token_env=args.token_env,
                project_id=args.project_id,
                approved_plan_id=args.approved_plan_id,
                idempotency_key=args.idempotency_key,
                timeout_seconds=args.timeout,
                ca_bundle=args.ca_bundle,
            )
        settings = Settings.from_env()
        if args.command == "doctor":
            payload = {
                "status": "ok",
                "version": __version__,
                "settings": settings.diagnostics(),
                "limitations": _limitations(settings),
            }
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                print(f"PSR MCP {settings.service_mode.value} configuration: OK")
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "serve":
            _serve(settings)
            return 0
    except KeyboardInterrupt:
        return 130
    except ConformanceError:
        print("conformance failed; inspect restricted diagnostic logs")
        return 4
    except (RuntimeError, ValueError) as error:
        print(f"configuration error: {error}")
        return 2
    except (psycopg.Error, SQLAlchemyError):
        print("database operation failed; inspect restricted operator logs")
        return 3
    return 10


def serve() -> int:
    """`psr-mcp` console entry point."""
    try:
        settings = Settings.from_env()
        _serve(settings)
    except KeyboardInterrupt:
        return 130
    return 0


def _serve(settings: Settings) -> None:
    container = build_container(settings)
    app = create_http_app(container)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=False,
    )


def _database_command(*, action: str, revision: str | None, confirm_downgrade: bool) -> int:
    database_url = os.getenv("PSR_MIGRATION_DATABASE_URL")
    if not database_url:
        raise ValueError("PSR_MIGRATION_DATABASE_URL is required")
    if action == "current":
        migration_current(database_url)
        return 0
    if action == "upgrade":
        migration_upgrade(database_url, revision or "head")
        print(json.dumps({"action": "upgrade", "revision": revision or "head", "status": "ok"}))
        return 0
    if not confirm_downgrade:
        raise ValueError("downgrade requires --confirm-downgrade")
    migration_downgrade(database_url, revision or "-1")
    print(json.dumps({"action": "downgrade", "revision": revision or "-1", "status": "ok"}))
    return 0


def _limitations(settings: Settings) -> list[str]:
    limitations: list[str] = []
    if settings.service_mode is ServiceMode.PUBLIC_EPHEMERAL:
        if settings.public_fixture_research_enabled:
            limitations.append("development fixture is not external research evidence")
        elif settings.search_provider is SearchProviderMode.DISABLED:
            limitations.append("public research backend is disabled")
        else:
            limitations.append("live official-source usefulness is not yet validated")
            limitations.append(
                "external search provider retention is separate from PSR server retention"
            )
        limitations.append("Public Preview PG0 through PG3 are not yet fully validated")
        return limitations
    limitations.append("public collector and reporting are not exposed in Foundation mode")
    if settings.auth_mode.value == "static":
        limitations.append("development static authentication")
    if settings.storage_mode.value == "memory":
        limitations.append("in-memory storage")
    return limitations


def _conformance_command(
    *,
    endpoint: str,
    token_env: str,
    project_id: str | None,
    approved_plan_id: str | None,
    idempotency_key: str,
    timeout_seconds: float,
    ca_bundle: str | None,
) -> int:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token_env) is None:
        raise ValueError("--token-env must be an environment variable name")
    result = asyncio.run(
        run_conformance(
            ConformanceOptions(
                endpoint=endpoint,
                bearer_token=os.getenv(token_env),
                project_id=project_id,
                approved_plan_id=approved_plan_id,
                idempotency_key=idempotency_key,
                timeout_seconds=timeout_seconds,
                ca_bundle=ca_bundle,
            )
        )
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
