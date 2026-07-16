from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import ssl
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from starlette.types import Receive, Scope, Send

from psr_mcp.bootstrap import build_container
from psr_mcp.config import Settings
from psr_mcp.conformance import ConformanceOptions, run_conformance
from psr_mcp.mcp.http_policy import compose_http_policy
from psr_mcp.mcp.server import create_http_app

HOP_BY_HOP_HEADERS = {
    b"connection",
    b"content-length",
    b"host",
    b"keep-alive",
    b"proxy-authenticate",
    b"proxy-authorization",
    b"te",
    b"trailer",
    b"transfer-encoding",
    b"upgrade",
}
EDGE_STRIPPED_REQUEST_HEADERS = HOP_BY_HOP_HEADERS | {
    b"authorization",
    b"cookie",
    b"forwarded",
    b"x-forwarded-for",
    b"x-forwarded-host",
    b"x-forwarded-proto",
    b"x-psr-client-ip",
    b"x-real-ip",
}


@pytest.mark.remote
@pytest.mark.anyio
async def test_official_conformance_through_tls_terminating_reverse_proxy(
    tmp_path: Path,
) -> None:
    """Exercise HTTPS trust, proxy termination, reconnect, Tool, Resource, and Prompt."""
    ca_file, cert_file, key_file = _write_test_pki(tmp_path)
    backend_listener = _listener()
    public_listener = _listener()
    backend_port = backend_listener.getsockname()[1]
    public_port = public_listener.getsockname()[1]
    public_origin = f"https://localhost:{public_port}"
    settings = Settings.from_env(
        {
            "PSR_PORT": str(backend_port),
            "PSR_PUBLIC_URL": public_origin,
            "PSR_RESOURCE_SERVER_URL": f"{public_origin}/mcp",
        }
    )
    backend_app = create_http_app(build_container(settings))
    backend = uvicorn.Server(
        uvicorn.Config(
            backend_app,
            host="127.0.0.1",
            port=backend_port,
            log_level="error",
            proxy_headers=False,
        )
    )
    proxy = uvicorn.Server(
        uvicorn.Config(
            _reverse_proxy(
                backend_origin=f"http://127.0.0.1:{backend_port}",
                public_host=f"localhost:{public_port}",
            ),
            host="127.0.0.1",
            port=public_port,
            log_level="error",
            proxy_headers=False,
            lifespan="off",
            ssl_certfile=str(cert_file),
            ssl_keyfile=str(key_file),
        )
    )
    backend_task = asyncio.create_task(backend.serve(sockets=[backend_listener]))
    proxy_task = asyncio.create_task(proxy.serve(sockets=[public_listener]))
    try:
        await _wait_started(backend, proxy)
        result = await run_conformance(
            ConformanceOptions(
                endpoint=f"{public_origin}/mcp",
                ca_bundle=str(ca_file),
                project_id="project-public-ai",
                approved_plan_id="plan-approved-public-ai",
                idempotency_key="tls-proxy-conformance-0001",
            )
        )
    finally:
        proxy.should_exit = True
        backend.should_exit = True
        await asyncio.wait_for(asyncio.gather(proxy_task, backend_task), timeout=10)
        public_listener.close()
        backend_listener.close()

    assert result["status"] == "PASS"
    assert result["endpoint"] == f"{public_origin}/mcp"
    assert result["reconnect_verified"] is True
    assert result["bearer_token_used"] is False


@pytest.mark.remote
@pytest.mark.anyio
async def test_tls_gateway_overwrites_spoofed_identity_and_strips_credentials(
    tmp_path: Path,
) -> None:
    ca_file, cert_file, key_file = _write_test_pki(tmp_path)
    backend_listener = _listener()
    public_listener = _listener()
    backend_port = backend_listener.getsockname()[1]
    public_port = public_listener.getsockname()[1]
    public_origin = f"https://localhost:{public_port}"
    backend_app = compose_http_policy(
        _gateway_scope_app,
        request_id_factory=lambda: "generated-request-id",
        max_request_bytes=1_048_576,
        request_timeout_seconds=30,
        rate_limit_requests=120,
        rate_limit_window_seconds=60,
        rate_limit_hmac_key=b"testing-rate-limit-hmac-key-32-bytes",
        trusted_proxy_cidrs=("127.0.0.1/32",),
    )
    backend = uvicorn.Server(
        uvicorn.Config(
            backend_app,
            host="127.0.0.1",
            port=backend_port,
            log_level="error",
            proxy_headers=False,
            lifespan="off",
        )
    )
    proxy = uvicorn.Server(
        uvicorn.Config(
            _reverse_proxy(
                backend_origin=f"http://127.0.0.1:{backend_port}",
                public_host=f"localhost:{public_port}",
                canonical_client_ip="203.0.113.10",
            ),
            host="127.0.0.1",
            port=public_port,
            log_level="error",
            proxy_headers=False,
            lifespan="off",
            ssl_certfile=str(cert_file),
            ssl_keyfile=str(key_file),
        )
    )
    backend_task = asyncio.create_task(backend.serve(sockets=[backend_listener]))
    proxy_task = asyncio.create_task(proxy.serve(sockets=[public_listener]))
    try:
        await _wait_started(backend, proxy)
        async with httpx.AsyncClient(
            verify=ssl.create_default_context(cafile=str(ca_file))
        ) as client:
            response = await client.post(
                f"{public_origin}/mcp",
                content=b"gateway-boundary",
                headers={
                    "authorization": "Bearer must-be-removed",
                    "cookie": "session=must-be-removed",
                    "forwarded": "for=198.51.100.1",
                    "x-forwarded-for": "198.51.100.2",
                    "x-real-ip": "198.51.100.3",
                    "x-psr-client-ip": "198.51.100.4",
                },
            )
    finally:
        proxy.should_exit = True
        backend.should_exit = True
        await asyncio.wait_for(asyncio.gather(proxy_task, backend_task), timeout=10)
        public_listener.close()
        backend_listener.close()

    assert response.status_code == 200
    assert response.json() == {
        "client": "203.0.113.10",
        "sensitive_headers_present": [],
    }


def _listener() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    return listener


async def _wait_started(*servers: uvicorn.Server) -> None:
    for _ in range(500):
        if all(server.started for server in servers):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("TLS reverse-proxy test servers did not start")


def _reverse_proxy(
    *,
    backend_origin: str,
    public_host: str,
    canonical_client_ip: str | None = None,
) -> Callable[[Scope, Receive, Send], Awaitable[None]]:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            raise RuntimeError("reverse-proxy fixture accepts HTTP requests only")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        path = scope.get("raw_path", scope["path"].encode()).decode("ascii")
        query = scope.get("query_string", b"")
        target = f"{backend_origin}{path}"
        if query:
            target = f"{target}?{query.decode('ascii')}"
        forwarded_headers = [
            (name.decode("latin-1"), value.decode("latin-1"))
            for name, value in scope.get("headers", [])
            if name.lower() not in EDGE_STRIPPED_REQUEST_HEADERS
        ]
        forwarded_headers.append(("host", public_host))
        if canonical_client_ip is not None:
            forwarded_headers.append(("x-psr-client-ip", canonical_client_ip))
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.request(
                scope["method"],
                target,
                headers=forwarded_headers,
                content=bytes(body),
            )
        response_headers = [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in response.headers.multi_items()
            if name.lower().encode() not in HOP_BY_HOP_HEADERS | {b"content-encoding"}
        ]
        response_headers.append((b"content-length", str(len(response.content)).encode()))
        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": response_headers,
            }
        )
        await send({"type": "http.response.body", "body": response.content})

    return app


async def _gateway_scope_app(scope: Scope, receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        if message["type"] == "http.request" and not message.get("more_body", False):
            break
    sensitive_names = {
        b"authorization",
        b"cookie",
        b"forwarded",
        b"x-forwarded-for",
        b"x-forwarded-host",
        b"x-forwarded-proto",
        b"x-psr-client-ip",
        b"x-real-ip",
    }
    present = sorted(
        name.decode("ascii")
        for name, _ in scope.get("headers", [])
        if name.lower() in sensitive_names
    )
    payload = json.dumps(
        {
            "client": scope.get("client", ("unknown", 0))[0],
            "sensitive_headers_present": present,
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": payload})


def _write_test_pki(tmp_path: Path) -> tuple[Path, Path, Path]:
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PSR test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_file = tmp_path / "ca.pem"
    cert_file = tmp_path / "server.pem"
    key_file = tmp_path / "server-key.pem"
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return ca_file, cert_file, key_file
