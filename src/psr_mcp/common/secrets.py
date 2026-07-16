"""Minimal secret-reference port and environment-backed implementation."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Protocol


class SecretResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


class EnvironmentSecretResolver:
    """Resolve only explicit env://NAME references without exposing their values."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def resolve(self, reference: str) -> str:
        match = re.fullmatch(r"env://([A-Za-z_][A-Za-z0-9_]*)", reference)
        if match is None:
            raise ValueError("only env://VARIABLE secret references are supported")
        value = self._environ.get(match.group(1))
        if value is None or not value.strip():
            raise ValueError("referenced secret is unavailable")
        return value
