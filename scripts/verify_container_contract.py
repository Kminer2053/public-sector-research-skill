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
    pyproject = (root / "pyproject.toml").read_text()
    build_requirements = (root / "requirements/container-build.txt").read_text()
    workflow = (root / ".github/workflows/ci.yml").read_text()
    return validate_contents(
        dockerfile=dockerfile,
        dockerignore=dockerignore,
        pyproject=pyproject,
        build_requirements=build_requirements,
        workflow=workflow,
    )


def validate_contents(
    *,
    dockerfile: str,
    dockerignore: str,
    pyproject: str,
    build_requirements: str,
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
        "requirements/container-build.txt": "hashed OCI build tool requirements",
        "--require-hashes": "locked dependency and build-tool hash verification",
        "--only-binary=:all:": "wheel-only dependency resolution",
        "--no-build-isolation": "preinstalled pinned PEP 517 build tools",
        "--python /usr/local/bin/python": "explicit OCI builder interpreter",
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
        r"(?mi)^\s*RUN\s+.*pip\s+install\s+.*uv==": (
            "build tools must come from the hashed requirements file"
        ),
    }
    for pattern, message in forbidden_patterns.items():
        if re.search(pattern, dockerfile):
            errors.append(message)

    if 'requires = ["hatchling==1.31.0"]' not in pyproject:
        errors.append("pyproject must pin the OCI PEP 517 backend exactly")
    requirement_blocks = _requirement_blocks(build_requirements)
    for package, version in {
        "hatchling": "1.31.0",
        "uv": "0.11.15",
    }.items():
        block = requirement_blocks.get(package)
        if block is None or block[0].rstrip(" \\") != f"{package}=={version}":
            errors.append(f"container build requirements must pin {package}=={version}")
        elif not any("--hash=sha256:" in line for line in block[1:]):
            errors.append(f"container build requirements must hash {package}")
    for package, block in requirement_blocks.items():
        if "==" not in block[0]:
            errors.append(f"container build requirement {package} is not exact")
        if not any("--hash=sha256:" in line for line in block[1:]):
            errors.append(f"container build requirement {package} has no SHA-256 hash")

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


def _requirement_blocks(requirements: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for raw_line in requirements.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line[0].isspace():
            if current is not None:
                current.append(line.strip())
            continue
        package = re.split(r"[=<>!~\s]", line, maxsplit=1)[0].lower()
        current = [line]
        blocks[package] = current
    return blocks


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
