from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from psr_mcp.bootstrap import build_container
from psr_mcp.config import Settings
from psr_mcp.mcp.server import create_http_app


def _initialize_payload() -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "remote-policy-test", "version": "1.0"},
        },
    }


@pytest.mark.anyio
async def test_canonical_public_host_and_origin_are_allowed() -> None:
    settings = Settings.from_env(
        {
            "PSR_PUBLIC_URL": "https://research.example.gov",
            "PSR_RESOURCE_SERVER_URL": "https://research.example.gov/mcp",
        }
    )
    app = create_http_app(build_container(settings))
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
        "origin": "https://research.example.gov",
        "x-forwarded-host": "attacker.example",
        "x-forwarded-proto": "http",
    }
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://research.example.gov",
        ) as client,
    ):
        response = await client.post("/mcp", headers=headers, json=_initialize_payload())

    assert response.status_code == 200
    assert response.json()["result"]["protocolVersion"] == "2025-11-25"
    assert response.headers["x-request-id"]


@pytest.mark.anyio
async def test_unconfigured_host_is_rejected_by_transport_security() -> None:
    settings = Settings.from_env(
        {
            "PSR_PUBLIC_URL": "https://research.example.gov",
            "PSR_RESOURCE_SERVER_URL": "https://research.example.gov/mcp",
        }
    )
    app = create_http_app(build_container(settings))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://research.example.gov",
        ) as client,
    ):
        response = await client.post(
            "/mcp",
            headers={
                "host": "evil.example",
                "accept": "application/json, text/event-stream",
                "content-type": "application/json",
            },
            json=_initialize_payload(),
        )

    assert response.status_code in {400, 403, 421}
