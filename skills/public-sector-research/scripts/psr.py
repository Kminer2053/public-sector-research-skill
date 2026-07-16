#!/usr/bin/env python3
"""Self-contained entry point bundled with the Agent Skill."""

# ruff: noqa: E402, I001

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from psr_core.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
