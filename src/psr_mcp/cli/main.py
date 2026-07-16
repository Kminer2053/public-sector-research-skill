"""Minimal operator/development CLI for Foundation."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

import psycopg
from sqlalchemy.exc import SQLAlchemyError

from psr_mcp import __version__
from psr_mcp.bootstrap import build_container
from psr_mcp.config import Settings
from psr_mcp.mcp.server import create_server
from psr_mcp.storage.migrations.runner import current as migration_current
from psr_mcp.storage.migrations.runner import downgrade as migration_downgrade
from psr_mcp.storage.migrations.runner import upgrade as migration_upgrade


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psrctl")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="validate and print redacted configuration")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    serve_parser = commands.add_parser("serve", help="run the Foundation development MCP server")
    serve_parser.add_argument("service", choices=["mcp"])
    database = commands.add_parser("db", help="run operator-only PostgreSQL migrations")
    database.add_argument("action", choices=["current", "upgrade", "downgrade"])
    database.add_argument("--revision")
    database.add_argument("--confirm-downgrade", action="store_true")
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
        settings = Settings.from_env()
        if args.command == "doctor":
            payload = {
                "status": "ok",
                "version": __version__,
                "settings": settings.diagnostics(),
                "limitations": [
                    "development static authentication",
                    "in-memory storage",
                    "PostgreSQL adapter is not composed into the MCP server",
                    "OAuth/remote conformance not validated",
                ],
            }
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                print("PSR MCP Foundation development configuration: OK")
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "serve":
            _serve(settings)
            return 0
    except KeyboardInterrupt:
        return 130
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
    server = create_server(container)
    server.run(transport="streamable-http")


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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
