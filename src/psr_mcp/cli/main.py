"""Minimal operator/development CLI for Foundation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from psr_mcp import __version__
from psr_mcp.bootstrap import build_container
from psr_mcp.config import Settings
from psr_mcp.mcp.server import create_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psrctl")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="validate and print redacted configuration")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    serve_parser = commands.add_parser("serve", help="run the Foundation development MCP server")
    serve_parser.add_argument("service", choices=["mcp"])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "doctor":
            payload = {
                "status": "ok",
                "version": __version__,
                "settings": settings.diagnostics(),
                "limitations": [
                    "development static authentication",
                    "in-memory storage",
                    "PostgreSQL/OAuth/remote conformance not validated",
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
