from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from psr_mcp.bootstrap import PublicContainer, build_container
from psr_mcp.common.secrets import EnvironmentSecretResolver
from psr_mcp.config import Settings
from psr_mcp.mcp.server import create_http_app, create_server


@pytest.fixture
async def public_session(tmp_path: Path) -> AsyncGenerator[ClientSession]:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
            "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
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
    assert [tool.name for tool in tools.tools] == [
        "psr.service.policy",
        "psr.research.quick",
    ]

    result = await public_session.call_tool("psr.service.policy", {})
    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["service_mode"] == "public_ephemeral"
    assert result.structuredContent["source_discovery"] == "development_fixture"
    assert result.structuredContent["authentication_required"] is False
    assert result.structuredContent["research_available"] is True
    assert result.structuredContent["retention"]["server_saved"] is False
    assert result.structuredContent["limits"]["trusted_proxy_networks"] == 0


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


@pytest.mark.anyio
async def test_public_http_composition_enforces_trusted_proxy_client_ip(
    tmp_path: Path,
) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
            "PSR_TRUSTED_PROXY_CIDRS": "10.0.0.0/8",
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
            transport=ASGITransport(app=app, client=("10.0.0.10", 1234)),
            base_url="http://127.0.0.1:8000",
        ) as client,
    ):
        missing = await client.post("/mcp", headers=headers, json=request)
        accepted = await client.post(
            "/mcp",
            headers={**headers, "x-psr-client-ip": "203.0.113.10"},
            json=request,
        )

    assert missing.status_code == 400
    assert missing.json() == {"error": "trusted_proxy_client_ip_missing"}
    assert accepted.status_code == 200


@pytest.mark.anyio
async def test_service_policy_discloses_external_search_retention(
    tmp_path: Path,
) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
            "PSR_SEARCH_PROVIDER": "brave",
            "PSR_SEARCH_API_KEY_REF": "env://BRAVE_API_KEY",
        }
    )
    container = build_container(
        settings,
        secret_resolver=EnvironmentSecretResolver({"BRAVE_API_KEY": "test-brave-api-key-123456"}),
    )
    assert isinstance(container, PublicContainer)
    await container.open()
    try:
        server = create_server(container)
        assert server.instructions is not None
        assert "외부 provider" in server.instructions
        assert "psr.service.policy" in server.instructions
        async with create_connected_server_and_client_session(
            server,
            raise_exceptions=False,
        ) as session:
            result = await session.call_tool("psr.service.policy", {})
    finally:
        await container.close()

    assert result.structuredContent is not None
    external = result.structuredContent["external_services"]
    assert external[0]["provider"] == "Brave Search API"
    assert "90일" in external[0]["provider_retention"]
    assert "검색어" in external[0]["data_sent"][0]


@pytest.mark.anyio
async def test_curated_policy_is_available_without_account_or_search_processor(
    tmp_path: Path,
) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
            "PSR_SEARCH_PROVIDER": "curated",
        }
    )
    container = build_container(settings)
    assert isinstance(container, PublicContainer)
    await container.open()
    try:
        server = create_server(container)
        assert server.instructions is not None
        assert "실시간 웹 검색이 아닙니다" in server.instructions
        async with create_connected_server_and_client_session(
            server,
            raise_exceptions=False,
        ) as session:
            result = await session.call_tool("psr.service.policy", {})
    finally:
        await container.close()

    assert result.structuredContent is not None
    assert result.structuredContent["authentication_required"] is False
    assert result.structuredContent["research_available"] is True
    assert result.structuredContent["source_discovery"] == "curated_seed"
    assert result.structuredContent["external_services"] == []


@pytest.mark.anyio
async def test_quick_fixture_returns_result_and_purges_all_content(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    question_canary = "QUESTION-CANARY-9f3d 공공기관 AI 구매 데이터 권리를 조사해줘"
    root = tmp_path / "ephemeral"
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(root),
            "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
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
            with caplog.at_level(logging.INFO):
                result = await session.call_tool(
                    "psr.research.quick",
                    {"question": question_canary},
                )
    finally:
        await container.close()

    assert result.isError is False
    assert result.structuredContent is not None
    output = result.structuredContent
    assert output["status"] == "PARTIAL"
    assert output["scope"]["source_discovery"] == "development_fixture"
    assert output["retention"]["server_saved"] is False
    assert output["retention"]["purge_state"] == "PURGED"
    assert "data-rights" in output["scope"]["source_tracks"]
    assert "procurement" in output["scope"]["source_tracks"]
    assert output["failures"][0]["code"] == "FIXTURE_ONLY"
    assert output["citations"]
    assert output["citations"][0]["source_tier"] == "TEST_FIXTURE"
    assert output["citations"][0]["score"]["authority"]["value"] == 0.0
    assert len(output["citations"][0]["document_sha256"]) == 64
    assert list(root.iterdir()) == []

    serialized = json.dumps(output, ensure_ascii=False)
    assert question_canary not in serialized
    assert question_canary not in caplog.text
    assert "PSR-SOURCE-CONTENT-CANARY" not in caplog.text
    assert "PSR-RESULT-CONTENT-CANARY" not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "overrides, expected_code",
    [
        (
            {
                "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
                "PSR_PUBLIC_KILL_SWITCH": "true",
            },
            "PUBLIC_SERVICE_PAUSED",
        ),
        ({}, "RESEARCH_NOT_AVAILABLE"),
    ],
)
async def test_quick_fails_safely_when_paused_or_backend_unavailable(
    tmp_path: Path,
    overrides: dict[str, str],
    expected_code: str,
) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
            **overrides,
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
            result = await session.call_tool(
                "psr.research.quick",
                {"question": "공공기관 AI 구매 원칙을 공식자료 중심으로 조사해줘"},
            )
    finally:
        await container.close()

    assert result.isError is True
    assert expected_code in result.content[0].text  # type: ignore[union-attr]
    assert list((tmp_path / "ephemeral").iterdir()) == []
