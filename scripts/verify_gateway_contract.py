"""Static fail-closed checks for the direct-ingress Public Preview gateway."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

PINNED_NGINX_IMAGE = (
    "nginx:1.30.4-alpine@sha256:59d10bca5c674965ef4ff884715000dd60ef5567c36663523f108eec8e4105d4"
)


def validate_contract(root: Path) -> tuple[str, ...]:
    nginx_conf = (root / "deploy/nginx/nginx.conf").read_text()
    server_template = (root / "deploy/nginx/templates/psr-public.conf.template").read_text()
    validator_path = root / "deploy/nginx/entrypoint/15-psr-validate-env.sh"
    gateway_validator = validator_path.read_text()
    workflow = (root / ".github/workflows/ci.yml").read_text()
    errors = list(
        validate_contents(
            nginx_conf=nginx_conf,
            server_template=server_template,
            gateway_validator=gateway_validator,
            workflow=workflow,
        )
    )
    if validator_path.stat().st_mode & 0o111 == 0:
        errors.append("gateway environment validator must be executable")
    return tuple(errors)


def validate_contents(
    *,
    nginx_conf: str,
    server_template: str,
    gateway_validator: str,
    workflow: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    required_nginx = {
        "error_log /dev/stderr crit;": "critical-only error log",
        "log_format psr_content_free": "content-free access log format",
        "access_log /dev/stdout psr_content_free;": "content-free access log",
        "client_body_temp_path /tmp/client_body": "ephemeral request-body temp path",
        "proxy_temp_path /tmp/proxy": "ephemeral proxy temp path",
        "limit_req_zone $binary_remote_addr zone=psr_per_ip:10m rate=60r/m;": (
            "per-IP request limit zone"
        ),
        "limit_req_zone $server_name zone=psr_global:10m rate=20r/s;": (
            "global request limit zone"
        ),
        "limit_conn_zone $binary_remote_addr zone=psr_per_ip_conn:10m;": (
            "per-IP connection limit zone"
        ),
        "limit_conn_zone $server_name zone=psr_global_conn:10m;": ("global connection limit zone"),
        "limit_req_status 429;": "request quota status",
        "limit_conn_status 429;": "connection quota status",
        "include /tmp/conf.d/*.conf;": "read-only compatible rendered config directory",
    }
    for fragment, purpose in required_nginx.items():
        if fragment not in nginx_conf:
            errors.append(f"nginx.conf missing {purpose}")

    log_match = re.search(
        r"log_format\s+psr_content_free\b(?P<body>.*?);",
        nginx_conf,
        flags=re.DOTALL,
    )
    if log_match is None:
        errors.append("nginx.conf must define psr_content_free log format")
    else:
        log_body = log_match.group("body").lower()
        forbidden_log_patterns = {
            r"\$remote_addr\b": "client IP",
            r"\$request\b": "request line",
            r"\$request_uri\b": "URI/query",
            r"\$uri\b": "URI",
            r"\$host\b": "Host",
            r"\$http_": "request header",
            r"\$request_body\b": "request body",
            r"\$sent_http_": "response header",
            r"\$upstream_http_": "upstream response header",
        }
        for pattern, content in forbidden_log_patterns.items():
            if re.search(pattern, log_body):
                errors.append(f"content-free access log includes {content}")

    required_template = {
        "server ${PSR_UPSTREAM_HOST}:${PSR_UPSTREAM_PORT}": "explicit upstream",
        "listen 8443 ssl default_server;": "default TLS rejection server",
        "ssl_reject_handshake on;": "unknown SNI rejection",
        "return 421;": "valid-SNI but invalid-Host rejection",
        "server_name ${PSR_PUBLIC_HOST};": "canonical public host",
        "ssl_protocols TLSv1.2 TLSv1.3;": "TLS protocol floor",
        "ssl_session_tickets off;": "TLS session ticket disablement",
        "location = /mcp {": "exact MCP route",
        "limit_req zone=psr_per_ip burst=20 nodelay;": "per-IP edge quota",
        "limit_req zone=psr_global burst=40 nodelay;": "global edge quota",
        "limit_conn psr_per_ip_conn 4;": "per-IP connection quota",
        "limit_conn psr_global_conn 100;": "global connection quota",
        "client_max_body_size 1m;": "request body cap matching the app default",
        "proxy_request_buffering off;": "request streaming without disk buffering",
        "proxy_buffering off;": "response streaming without disk buffering",
        "proxy_max_temp_file_size 0;": "proxy response temp-file disablement",
        "proxy_cache off;": "cache disablement",
        "proxy_next_upstream off;": "non-idempotent request retry disablement",
        "proxy_set_header Host ${PSR_PUBLIC_HOST};": "canonical upstream Host",
        'proxy_set_header Authorization "";': "credential stripping",
        'proxy_set_header Cookie "";': "cookie stripping",
        'proxy_set_header Forwarded "";': "standard forwarding header stripping",
        'proxy_set_header X-Forwarded-For "";': "forwarded IP stripping",
        'proxy_set_header X-Real-IP "";': "real IP stripping",
        "proxy_set_header X-PSR-Client-IP $remote_addr;": (
            "canonical direct-peer client IP overwrite"
        ),
        "proxy_hide_header Set-Cookie;": "upstream cookie suppression",
        'add_header Cache-Control "no-store" always;': "response storage prevention",
        "proxy_pass http://psr_backend;": "application proxy target",
        "location / {": "default route",
        "return 404;": "default route rejection",
    }
    for fragment, purpose in required_template.items():
        if fragment not in server_template:
            errors.append(f"gateway template missing {purpose}")

    forbidden_template_patterns = {
        r"\breal_ip_header\b": "direct-ingress reference must not trust a forwarding header",
        r"\bset_real_ip_from\b": "direct-ingress reference must not declare upstream proxies",
        r"\$http_x_forwarded_for\b": "gateway must not consume client X-Forwarded-For",
        r"\$http_x_real_ip\b": "gateway must not consume client X-Real-IP",
        r"\$http_x_psr_client_ip\b": "gateway must not consume client X-PSR-Client-IP",
        r"\bproxy_add_x_forwarded_for\b": "gateway must not append a spoofable IP chain",
        r"(?i)proxy_set_header\s+X-PSR-Client-IP\s+(?!\$remote_addr;)": (
            "canonical client IP must come only from the direct TCP peer"
        ),
        r"(?mi)^\s*proxy_store\b": "gateway must not store responses",
    }
    for pattern, message in forbidden_template_patterns.items():
        if re.search(pattern, server_template):
            errors.append(message)

    required_validator = {
        "set -eu": "fail-fast shell mode",
        'validate_dns_name "${PSR_PUBLIC_HOST:-}"': "public Host validation",
        'validate_dns_name "${PSR_UPSTREAM_HOST:-}"': "upstream Host validation",
        '[ "$port" -ge 1 ]': "upstream port lower bound",
        '[ "$port" -le 65535 ]': "upstream port upper bound",
        "[ -r /etc/nginx/tls/tls.crt ]": "TLS certificate readability check",
        "[ -r /etc/nginx/tls/tls.key ]": "TLS key readability check",
        '[ "${NGINX_ENVSUBST_FILTER:-}" = "^(PSR_)" ]': ("restricted envsubst filter enforcement"),
        '[ "${NGINX_ENVSUBST_OUTPUT_DIR:-}" = "/tmp/conf.d" ]': (
            "ephemeral envsubst output enforcement"
        ),
        "mkdir -p /tmp/conf.d": "render output directory creation",
        "[ -w /tmp/conf.d ]": "render output directory writability check",
    }
    for fragment, purpose in required_validator.items():
        if fragment not in gateway_validator:
            errors.append(f"gateway environment validator missing {purpose}")
    if re.search(r"(?m)^\s*echo\s+.*\$(?:\{)?PSR_", gateway_validator):
        errors.append("gateway environment validator must not echo configuration values")

    required_workflow = {
        f'NGINX_IMAGE: "{PINNED_NGINX_IMAGE}"': "pinned official NGINX image",
        "python3 scripts/verify_gateway_contract.py": "static gateway contract gate",
        "NGINX_ENVSUBST_FILTER='^(PSR_)'": "restricted NGINX template substitution",
        "NGINX_ENVSUBST_OUTPUT_DIR=/tmp/conf.d": "ephemeral rendered config directory",
        (
            "deploy/nginx/entrypoint/15-psr-validate-env.sh:"
            "/docker-entrypoint.d/15-psr-validate-env.sh:ro"
        ): "gateway environment validator mount",
        "nginx -t -c /etc/nginx/nginx.conf": "NGINX syntax validation",
        "--user 101:101": "non-root NGINX validation",
        "--read-only": "read-only NGINX validation",
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
