from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast


class ValidateContents(Protocol):
    def __call__(
        self,
        *,
        dockerfile: str,
        dockerignore: str,
        workflow: str,
    ) -> tuple[str, ...]: ...


_SCRIPT = runpy.run_path("scripts/verify_container_contract.py")
PINNED_PYTHON_IMAGE = cast(str, _SCRIPT["PINNED_PYTHON_IMAGE"])
validate_contract = cast(Callable[[Path], tuple[str, ...]], _SCRIPT["validate_contract"])
validate_contents = cast(ValidateContents, _SCRIPT["validate_contents"])


def test_repository_container_contract_is_fail_closed() -> None:
    assert validate_contract(Path(".")) == ()


def test_container_contract_rejects_unpinned_root_and_missing_hardening() -> None:
    errors = validate_contents(
        dockerfile=f"""
ARG PYTHON_IMAGE={PINNED_PYTHON_IMAGE}
FROM ${{PYTHON_IMAGE}} AS runtime-base
VOLUME /var/lib/psr/ephemeral
HEALTHCHECK CMD psrctl conformance-public --endpoint http://127.0.0.1:8000/mcp
USER root
ENTRYPOINT ["psr-mcp"]
""",
        dockerignore=".git\n",
        workflow="docker build .\n",
    )

    assert "Dockerfile must not create persistent anonymous volumes" in errors
    assert "Dockerfile must not spend research budget as a healthcheck" in errors
    assert "runtime must not switch back to root" in errors
    assert "CI missing read-only root filesystem" in errors
    assert ".dockerignore missing .env" in errors
