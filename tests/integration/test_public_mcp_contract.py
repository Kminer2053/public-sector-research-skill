from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from psr_mcp.bootstrap import PublicContainer, build_container
from psr_mcp.config import Settings
from psr_mcp.mcp.server import create_http_app, create_server


@pytest.fixture
async def public_session(tmp_path: Path) -> AsyncGenerator[ClientSession]:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
        }
    )
    container = build_container(settings)
    assert isinstance(container, PublicContainer)
    await container.open()
    try:
        server = create_server(container)
        async with create_connected_server_and_client_session(
            server,
            raise_exceptions=False,
        ) as session:
            yield session
    finally:
        await container.close()


@pytest.mark.anyio
async def test_public_catalog_requires_no_account_and_hides_foundation_tools(
    public_session: ClientSession,
) -> None:
    tools = await public_session.list_tools()
    assert [tool.name for tool in tools.tools] == ["psr.service.policy"]

    result = await public_session.call_tool("psr.service.policy", {})
    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["service_mode"] == "public_ephemeral"
    assert result.structuredContent["authentication_required"] is False
    assert result.structuredContent["research_available"] is False
    assert result.structuredContent["retention"]["server_saved"] is False


@pytest.mark.anyio
async def test_public_http_lifecycle_serves_policy_without_oauth(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
        }
    )
    container = build_container(settings)
    assert isinstance(container, PublicContainer)
    app = create_http_app(container)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "psr.service.policy", "arguments": {}},
    }
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
    }
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client,
    ):
        response = await client.post("/mcp", headers=headers, json=request)

    assert response.status_code == 200
    payload = response.json()["result"]["structuredContent"]
    assert payload["authentication_required"] is False
    assert payload["research_available"] is False
    assert (tmp_path / "ephemeral").is_dir()
