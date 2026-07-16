from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import pytest
import uvicorn

from psr_mcp.bootstrap import build_container
from psr_mcp.config import Settings
from psr_mcp.conformance import (
    ConformanceError,
    ConformanceOptions,
    PublicConformanceOptions,
    run_conformance,
    run_public_conformance,
)
from psr_mcp.mcp.server import create_http_app


@pytest.mark.remote
@pytest.mark.anyio
async def test_official_sdk_conformance_over_real_tcp_and_reconnect() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    settings = Settings.from_env(
        {
            "PSR_PORT": str(port),
            "PSR_PUBLIC_URL": f"http://127.0.0.1:{port}",
        }
    )
    app = create_http_app(build_container(settings))
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="error",
            proxy_headers=False,
        )
    )
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started
        result = await run_conformance(
            ConformanceOptions(
                endpoint=f"http://127.0.0.1:{port}/mcp",
                project_id="project-public-ai",
                approved_plan_id="plan-approved-public-ai",
                idempotency_key="tcp-conformance-0001",
            )
        )
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=5)
        listener.close()

    assert result["status"] == "PASS"
    assert result["protocol_version"] == "2025-11-25"
    assert result["reconnect_verified"] is True
    assert result["run_id"]
    assert result["bearer_token_used"] is False


@pytest.mark.remote
@pytest.mark.anyio
async def test_public_sdk_conformance_over_real_tcp_without_account(
    tmp_path: Path,
) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path),
            "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
            "PSR_PORT": str(port),
            "PSR_PUBLIC_URL": f"http://127.0.0.1:{port}",
            "PSR_RESOURCE_SERVER_URL": f"http://127.0.0.1:{port}/mcp",
        }
    )
    app = create_http_app(build_container(settings))
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="error",
            proxy_headers=False,
        )
    )
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started
        endpoint = f"http://127.0.0.1:{port}/mcp"
        result = await run_public_conformance(
            PublicConformanceOptions(
                endpoint=endpoint,
                release_gate=False,
                verify_feedback_submission=True,
            )
        )
        with pytest.raises(ConformanceError):
            await run_public_conformance(PublicConformanceOptions(endpoint=endpoint))
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=5)
        listener.close()

    assert result["status"] == "PASS"
    assert result["protocol_version"] == "2025-11-25"
    assert result["source_discovery"] == "development_fixture"
    assert result["authentication_required"] is False
    assert result["purge_verified"] is True
    assert result["feedback_token_present"] is True
    assert result["feedback_submission_verified"] is True
    assert result["release_gate_checked"] is False
    assert result["reconnect_verified"] is True
    serialized = str(result)
    assert "feedback-token" not in serialized
    assert "공공기관 AI 구매 원칙" not in serialized
