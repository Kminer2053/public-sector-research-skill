from __future__ import annotations

import asyncio
import ipaddress
import socket
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
            if name.lower() not in HOP_BY_HOP_HEADERS
        ]
        forwarded_headers.append(("host", public_host))
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
