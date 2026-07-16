#!/usr/bin/env python3
"""Install the portable skill into common user-level discovery locations."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Dict, Sequence

TARGETS: Dict[str, Path] = {
    "codex": Path.home() / ".codex" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "agents": Path.home() / ".agents" / "skills",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        choices=["codex", "claude", "agents", "all"],
        default="all",
    )
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = Path(__file__).resolve().parents[1]
    source = repository / "skills" / "public-sector-research"
    if args.destination:
        destinations = [args.destination.expanduser().resolve()]
    else:
        names = TARGETS if args.target == "all" else {args.target: TARGETS[args.target]}
        destinations = [path / source.name for path in names.values()]
    for destination in destinations:
        if destination.exists():
            if not args.force:
                raise SystemExit(
                    f"destination exists: {destination}; rerun with --force to replace it"
                )
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
