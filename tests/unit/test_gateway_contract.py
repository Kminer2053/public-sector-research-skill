from __future__ import annotations

import runpy
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

import pytest


class ValidateContents(Protocol):
    def __call__(
        self,
        *,
        nginx_conf: str,
        server_template: str,
        gateway_validator: str,
        workflow: str,
    ) -> tuple[str, ...]: ...


_SCRIPT = runpy.run_path("scripts/verify_gateway_contract.py")
validate_contract = cast(Callable[[Path], tuple[str, ...]], _SCRIPT["validate_contract"])
validate_contents = cast(ValidateContents, _SCRIPT["validate_contents"])


def test_repository_gateway_contract_passes() -> None:
    assert validate_contract(Path(".")) == ()


def test_gateway_contract_rejects_spoofable_identity_and_sensitive_log() -> None:
    root = Path(__file__).resolve().parents[2]
    nginx_conf = (
        (root / "deploy/nginx/nginx.conf")
        .read_text()
        .replace(
            '"request_seconds":$request_time,',
            '"client":"$remote_addr","request_seconds":$request_time,',
        )
    )
    server_template = (
        (root / "deploy/nginx/templates/psr-public.conf.template")
        .read_text()
        .replace(
            "proxy_set_header X-PSR-Client-IP $remote_addr;",
            "proxy_set_header X-PSR-Client-IP $http_x_psr_client_ip;",
        )
    )
    gateway_validator = (root / "deploy/nginx/entrypoint/15-psr-validate-env.sh").read_text()
    workflow = (root / ".github/workflows/ci.yml").read_text()

    errors = validate_contents(
        nginx_conf=nginx_conf,
        server_template=server_template,
        gateway_validator=gateway_validator,
        workflow=workflow,
    )

    assert "content-free access log includes client IP" in errors
    assert "gateway must not consume client X-PSR-Client-IP" in errors
    assert "canonical client IP must come only from the direct TCP peer" in errors


def test_gateway_contract_rejects_missing_syntax_gate() -> None:
    root = Path(__file__).resolve().parents[2]
    nginx_conf = (root / "deploy/nginx/nginx.conf").read_text()
    server_template = (root / "deploy/nginx/templates/psr-public.conf.template").read_text()
    gateway_validator = (root / "deploy/nginx/entrypoint/15-psr-validate-env.sh").read_text()
    workflow = (
        (root / ".github/workflows/ci.yml")
        .read_text()
        .replace(
            "nginx -t -c /etc/nginx/nginx.conf",
            "true",
        )
    )

    errors = validate_contents(
        nginx_conf=nginx_conf,
        server_template=server_template,
        gateway_validator=gateway_validator,
        workflow=workflow,
    )

    assert "CI missing NGINX syntax validation" in errors


@pytest.mark.parametrize(
    ("public_host", "upstream_host", "upstream_port"),
    [
        ("localhost", "psr-public", "8000"),
        ("203.0.113.1", "psr-public", "8000"),
        ("research.example.org\nload_module", "psr-public", "8000"),
        ("research.example.org", "psr-public;return", "8000"),
        ("research.example.org", "psr-public", "8000;return"),
    ],
)
def test_gateway_environment_validator_rejects_injection_without_echoing_values(
    public_host: str,
    upstream_host: str,
    upstream_port: str,
) -> None:
    script = "deploy/nginx/entrypoint/15-psr-validate-env.sh"
    result = subprocess.run(
        ["sh", script],
        env={
            "PATH": "/usr/bin:/bin",
            "PSR_PUBLIC_HOST": public_host,
            "PSR_UPSTREAM_HOST": upstream_host,
            "PSR_UPSTREAM_PORT": upstream_port,
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "PSR gateway configuration is invalid\n"
