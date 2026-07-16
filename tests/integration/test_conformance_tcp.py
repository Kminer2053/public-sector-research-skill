from __future__ import annotations

import asyncio
import socket

import pytest
import uvicorn

from psr_mcp.bootstrap import build_container
from psr_mcp.config import Settings
from psr_mcp.conformance import ConformanceOptions, run_conformance
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
