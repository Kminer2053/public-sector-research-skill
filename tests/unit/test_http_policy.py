from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from psr_mcp.mcp.http_policy import (
    FixedWindowRateLimitMiddleware,
    _rate_keys,
    _request_id,
    compose_http_policy,
)


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


async def _client_scope_app(scope: Scope, receive: Receive, send: Send) -> None:
    del receive
    payload = json.dumps(
        {
            "client": scope.get("client", ("unknown", 0))[0],
            "forwarded_header_present": any(
                key.lower() == b"x-psr-client-ip" for key, _ in scope.get("headers", [])
            ),
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


def _policy(*, limit: int = 10, timeout: float = 1.0) -> ASGIApp:
    return compose_http_policy(
        _echo_app,
        request_id_factory=lambda: "generated-request-id",
        max_request_bytes=16,
        request_timeout_seconds=timeout,
        rate_limit_requests=limit,
        rate_limit_window_seconds=60,
        rate_limit_hmac_key=b"testing-rate-limit-hmac-key-32-bytes",
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
@pytest.mark.parametrize(
    "value, expected",
    [
        ("invalid", {"error": "invalid_content_length"}),
        ("-1", {"error": "invalid_content_length"}),
    ],
)
async def test_invalid_declared_request_size_is_rejected(
    value: str,
    expected: dict[str, str],
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_policy()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/mcp",
            content=b"x",
            headers={"content-length": value},
        )
    assert response.status_code == 400
    assert response.json() == expected


@pytest.mark.anyio
async def test_chunked_body_is_limited_by_observed_bytes() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"x" * 10
        yield b"y" * 10

    async with AsyncClient(
        transport=ASGITransport(app=_policy()), base_url="http://test"
    ) as client:
        response = await client.post("/mcp", content=chunks())
    assert response.status_code == 413


@pytest.mark.anyio
async def test_timeout_buffers_partial_response_and_returns_retryable_504() -> None:
    app = compose_http_policy(
        _echo_app,
        request_id_factory=lambda: "generated-request-id",
        max_request_bytes=1024,
        request_timeout_seconds=0.01,
        rate_limit_requests=10,
        rate_limit_window_seconds=60,
        rate_limit_hmac_key=b"testing-rate-limit-hmac-key-32-bytes",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", content=b"slow")
    assert response.status_code == 504
    assert response.json() == {"error": "request_timeout", "retryable": True}


@pytest.mark.anyio
async def test_rate_limit_is_ip_first_and_does_not_log_token(
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
    assert other_token.status_code == 429
    assert raw_token not in caplog.text


@pytest.mark.anyio
async def test_invalid_bearer_rotation_cannot_bypass_ip_quota() -> None:
    app = _policy(limit=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/mcp", content=b"first", headers={"authorization": "Bearer invalid-1"}
        )
        second = await client.post(
            "/mcp", content=b"second", headers={"authorization": "Bearer invalid-2"}
        )
        limited = await client.post(
            "/mcp", content=b"third", headers={"authorization": "Bearer invalid-3"}
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert limited.status_code == 429


@pytest.mark.anyio
async def test_trusted_proxy_client_ip_drives_quota_without_trusting_spoofed_headers() -> None:
    app = compose_http_policy(
        _echo_app,
        request_id_factory=lambda: "generated-request-id",
        max_request_bytes=1024,
        request_timeout_seconds=1,
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
        rate_limit_hmac_key=b"testing-rate-limit-hmac-key-32-bytes",
        trusted_proxy_cidrs=("10.0.0.0/8",),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("10.0.0.10", 1234)),
        base_url="http://test",
    ) as trusted:
        first = await trusted.post(
            "/mcp",
            content=b"first",
            headers={"x-psr-client-ip": "203.0.113.10"},
        )
        limited = await trusted.post(
            "/mcp",
            content=b"second",
            headers={"x-psr-client-ip": "203.0.113.10"},
        )
        other_client = await trusted.post(
            "/mcp",
            content=b"third",
            headers={"x-psr-client-ip": "203.0.113.11"},
        )
    assert first.status_code == 200
    assert limited.status_code == 429
    assert other_client.status_code == 200

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("198.51.100.20", 1234)),
        base_url="http://test",
    ) as direct:
        direct_first = await direct.post(
            "/mcp",
            content=b"direct-first",
            headers={"x-psr-client-ip": "203.0.113.100"},
        )
        direct_limited = await direct.post(
            "/mcp",
            content=b"direct-second",
            headers={"x-psr-client-ip": "203.0.113.101"},
        )
    assert direct_first.status_code == 200
    assert direct_limited.status_code == 429


@pytest.mark.anyio
async def test_client_ip_header_is_consumed_before_downstream_application() -> None:
    app = compose_http_policy(
        _client_scope_app,
        request_id_factory=lambda: "generated-request-id",
        max_request_bytes=1024,
        request_timeout_seconds=1,
        rate_limit_requests=10,
        rate_limit_window_seconds=60,
        rate_limit_hmac_key=b"testing-rate-limit-hmac-key-32-bytes",
        trusted_proxy_cidrs=("10.0.0.0/8",),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("10.0.0.10", 1234)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/mcp",
            content=b"request",
            headers={"x-psr-client-ip": "203.0.113.10"},
        )

    assert response.json() == {
        "client": "203.0.113.10",
        "forwarded_header_present": False,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "headers, error",
    [
        ({}, "trusted_proxy_client_ip_missing"),
        ({"x-psr-client-ip": "not-an-ip"}, "trusted_proxy_client_ip_invalid"),
        ({"x-psr-client-ip": "203.0.113.1, 203.0.113.2"}, "trusted_proxy_client_ip_invalid"),
    ],
)
async def test_trusted_proxy_client_ip_fails_closed(
    headers: dict[str, str],
    error: str,
) -> None:
    app = compose_http_policy(
        _echo_app,
        request_id_factory=lambda: "generated-request-id",
        max_request_bytes=1024,
        request_timeout_seconds=1,
        rate_limit_requests=10,
        rate_limit_window_seconds=60,
        rate_limit_hmac_key=b"testing-rate-limit-hmac-key-32-bytes",
        trusted_proxy_cidrs=("10.0.0.0/8",),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("10.0.0.10", 1234)),
        base_url="http://test",
    ) as client:
        response = await client.post("/mcp", content=b"request", headers=headers)

    assert response.status_code == 400
    assert response.json() == {"error": error}


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


def test_rate_limit_key_is_hmac_pseudonymous_and_rotates() -> None:
    scope: Scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer secret")],
    }
    first = _rate_keys(
        scope,
        hmac_key=b"testing-rate-limit-hmac-key-32-bytes",
        wall_time=0,
        rotation_seconds=60,
    )
    second = _rate_keys(
        scope,
        hmac_key=b"testing-rate-limit-hmac-key-32-bytes",
        wall_time=61,
        rotation_seconds=60,
    )
    assert first != second
    assert all("unknown" not in key and "secret" not in key for key in first)


def test_rate_limiter_rejects_short_hmac_key() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        FixedWindowRateLimitMiddleware(
            _echo_app,
            requests=1,
            window_seconds=60,
            hmac_key=b"short",
        )


def test_request_id_rejects_non_ascii_bytes() -> None:
    scope: Scope = {
        "type": "http",
        "headers": [(b"x-request-id", b"\xff" * 8)],
    }
    assert _request_id(scope) is None
