from __future__ import annotations

import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from psr_mcp.mcp.http_policy import compose_http_policy


async def _echo_app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        return
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        body.extend(message.get("body", b""))
        if not message.get("more_body", False):
            break
    if body == b"slow":
        await asyncio.sleep(0.05)
    response: Message = {
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"application/octet-stream")],
    }
    await send(response)
    await send({"type": "http.response.body", "body": bytes(body)})


def _policy(*, limit: int = 10, timeout: float = 1.0) -> ASGIApp:
    return compose_http_policy(
        _echo_app,
        request_id_factory=lambda: "generated-request-id",
        max_request_bytes=16,
        request_timeout_seconds=timeout,
        rate_limit_requests=limit,
        rate_limit_window_seconds=60,
    )


@pytest.mark.anyio
async def test_request_size_is_rejected_before_application_processing() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_policy()), base_url="http://test"
    ) as client:
        response = await client.post("/mcp", content=b"x" * 17)
    assert response.status_code == 413
    assert response.json() == {"error": "request_too_large"}


@pytest.mark.anyio
async def test_timeout_buffers_partial_response_and_returns_retryable_504() -> None:
    app = compose_http_policy(
        _echo_app,
        request_id_factory=lambda: "generated-request-id",
        max_request_bytes=1024,
        request_timeout_seconds=0.01,
        rate_limit_requests=10,
        rate_limit_window_seconds=60,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", content=b"slow")
    assert response.status_code == 504
    assert response.json() == {"error": "request_timeout", "retryable": True}


@pytest.mark.anyio
async def test_rate_limit_is_per_token_hash_and_does_not_log_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_token = "raw-token-that-must-not-appear"
    app = _policy(limit=1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with caplog.at_level(logging.INFO):
            first = await client.post(
                "/mcp",
                content=b"first",
                headers={"authorization": f"Bearer {raw_token}"},
            )
            limited = await client.post(
                "/mcp",
                content=b"second",
                headers={"authorization": f"Bearer {raw_token}"},
            )
            other_token = await client.post(
                "/mcp",
                content=b"third",
                headers={"authorization": "Bearer another-token"},
            )
    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert other_token.status_code == 200
    assert raw_token not in caplog.text


@pytest.mark.anyio
async def test_request_id_is_validated_and_reflected() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_policy()), base_url="http://test"
    ) as client:
        accepted = await client.post(
            "/mcp", content=b"ok", headers={"x-request-id": "client-request-0001"}
        )
        replaced = await client.post("/other", content=b"ok", headers={"x-request-id": "bad value"})
    assert accepted.headers["x-request-id"] == "client-request-0001"
    assert replaced.headers["x-request-id"] == "generated-request-id"
