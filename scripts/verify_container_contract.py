"""Static fail-closed checks for the Public Preview OCI artifact and CI smoke."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

PINNED_PYTHON_IMAGE = (
    "python:3.12.13-slim-bookworm@"
    "sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b"
)


def validate_contract(root: Path) -> tuple[str, ...]:
    dockerfile = (root / "Dockerfile").read_text()
    dockerignore = (root / ".dockerignore").read_text()
    workflow = (root / ".github/workflows/ci.yml").read_text()
    return validate_contents(
        dockerfile=dockerfile,
        dockerignore=dockerignore,
        workflow=workflow,
    )


def validate_contents(
    *,
    dockerfile: str,
    dockerignore: str,
    workflow: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    required_dockerfile = {
        f"ARG PYTHON_IMAGE={PINNED_PYTHON_IMAGE}": "pinned official Python image",
        "FROM runtime-base AS runtime": "final runtime stage",
        "PSR_ENV=production": "production fail-closed default",
        "PSR_SERVICE_MODE=public_ephemeral": "public-only service mode",
        "PSR_AUTH_MODE=static": "anonymous authentication mode",
        "PSR_STORAGE_MODE=memory": "no persistent content repository",
        "PSR_EPHEMERAL_ROOT=/var/lib/psr/ephemeral": "fixed ephemeral root",
        "PSR_PUBLIC_PAUSE_FILE=/run/psr/public.pause": "runtime pause boundary",
        "--require-hashes": "locked dependency hash verification",
        "USER 10001:10001": "non-root runtime user",
        'ENTRYPOINT ["psr-mcp"]': "exec-form server entrypoint",
        "FROM runtime-base AS test": "isolated container smoke target",
    }
    for fragment, purpose in required_dockerfile.items():
        if fragment not in dockerfile:
            errors.append(f"Dockerfile missing {purpose}")

    forbidden_patterns = {
        r"(?mi)^\s*VOLUME\b": "Dockerfile must not create persistent anonymous volumes",
        r"(?mi)^\s*HEALTHCHECK\b": "Dockerfile must not spend research budget as a healthcheck",
        r"(?mi)^\s*ADD\b": "Dockerfile must use explicit COPY only",
        r"(?mi)^\s*COPY\s+\.\s": "Dockerfile must not copy the entire repository",
        r"(?mi)^\s*USER\s+(?:root|0)(?::0)?\s*$": "runtime must not switch back to root",
        r"PSR_DATABASE_URL": "public image must not embed a database URL",
        r"PSR_AUTH_MODE=oauth": "public image must not enable OAuth",
        r"PSR_STORAGE_MODE=postgres": "public image must not enable persistent storage",
    }
    for pattern, message in forbidden_patterns.items():
        if re.search(pattern, dockerfile):
            errors.append(message)

    required_ignores = {
        ".git",
        ".venv",
        ".env",
        ".env.*",
        "docs",
        "tests",
        "dist",
        "*.pem",
        "*.key",
    }
    ignored = {
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for entry in sorted(required_ignores - ignored):
        errors.append(f".dockerignore missing {entry}")

    required_workflow = {
        "docker build --target test": "OCI test-stage build",
        "docker build --target runtime": "final runtime-stage build",
        "--read-only": "read-only root filesystem",
        "--cap-drop=ALL": "Linux capability drop",
        "no-new-privileges": "privilege escalation block",
        "/var/lib/psr/ephemeral": "ephemeral workspace tmpfs",
        "/run/psr": "operator pause tmpfs",
        "/opt/psr/container_smoke.py": "official SDK container smoke",
        "docker image inspect": "final image metadata inspection",
    }
    for fragment, purpose in required_workflow.items():
        if fragment not in workflow:
            errors.append(f"CI missing {purpose}")
    return tuple(errors)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    errors = validate_contract(root)
    print(
        json.dumps(
            {
                "status": "PASS" if not errors else "FAIL",
                "error_count": len(errors),
                "errors": list(errors),
            },
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
