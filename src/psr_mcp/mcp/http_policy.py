"""Bounded process-local HTTP policies around the MCP Streamable HTTP app."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}")
current_request_id: ContextVar[str | None] = ContextVar("psr_request_id", default=None)


def compose_http_policy(
    app: ASGIApp,
    *,
    request_id_factory: Callable[[], str],
    max_request_bytes: int,
    request_timeout_seconds: float,
    rate_limit_requests: int,
    rate_limit_window_seconds: float,
) -> ASGIApp:
    policy: ASGIApp = RequestTimeoutMiddleware(
        app,
        timeout_seconds=request_timeout_seconds,
    )
    policy = FixedWindowRateLimitMiddleware(
        policy,
        requests=rate_limit_requests,
        window_seconds=rate_limit_window_seconds,
    )
    policy = RequestBodyLimitMiddleware(policy, max_bytes=max_request_bytes)
    return RequestTraceMiddleware(policy, request_id_factory=request_id_factory)


class RequestTraceMiddleware:
    def __init__(self, app: ASGIApp, *, request_id_factory: Callable[[], str]) -> None:
        self._app = app
        self._request_id_factory = request_id_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        request_id = _request_id(scope) or self._request_id_factory()
        marker = current_request_id.set(request_id)
        started = time.monotonic()
        status_code = 500

        async def traced_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._app(scope, receive, traced_send)
        finally:
            logger.info(
                "remote request completed",
                extra={
                    "request_id": request_id,
                    "http_path": scope.get("path", ""),
                    "http_status": status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                },
            )
            current_request_id.reset(marker)


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/mcp":
            await self._app(scope, receive, send)
            return
        content_length = _header(scope, b"content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                await _send_json(send, 400, {"error": "invalid_content_length"})
                return
            if declared_size < 0:
                await _send_json(send, 400, {"error": "invalid_content_length"})
                return
            if declared_size > self._max_bytes:
                await _send_json(send, 413, {"error": "request_too_large"})
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self._app(scope, limited_receive, send)
        except _RequestTooLarge:
            await _send_json(send, 413, {"error": "request_too_large"})


class RequestTimeoutMiddleware:
    """Bound stateless JSON MCP requests and buffer response until completion."""

    def __init__(self, app: ASGIApp, *, timeout_seconds: float) -> None:
        self._app = app
        self._timeout_seconds = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/mcp":
            await self._app(scope, receive, send)
            return
        messages: list[Message] = []

        async def buffered_send(message: Message) -> None:
            messages.append(message)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._app(scope, receive, buffered_send)
        except TimeoutError:
            await _send_json(send, 504, {"error": "request_timeout", "retryable": True})
            return
        for message in messages:
            await send(message)


@dataclass(slots=True)
class _Window:
    started_at: float
    count: int


class FixedWindowRateLimitMiddleware:
    """Bounded single-process limiter; multi-replica quota belongs at the gateway."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests: int,
        window_seconds: float,
        max_keys: int = 10_000,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._app = app
        self._requests = requests
        self._window_seconds = window_seconds
        self._max_keys = max_keys
        self._monotonic = monotonic
        self._windows: OrderedDict[str, _Window] = OrderedDict()
        self._lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/mcp":
            await self._app(scope, receive, send)
            return
        allowed, retry_after = await self._consume(_rate_key(scope))
        if not allowed:
            await _send_json(
                send,
                429,
                {"error": "rate_limited", "retryable": True},
                headers=[(b"retry-after", str(max(1, math.ceil(retry_after))).encode())],
            )
            return
        await self._app(scope, receive, send)

    async def _consume(self, key: str) -> tuple[bool, float]:
        now = self._monotonic()
        async with self._lock:
            window = self._windows.get(key)
            if window is None or now - window.started_at >= self._window_seconds:
                self._windows[key] = _Window(now, 1)
                self._windows.move_to_end(key)
                while len(self._windows) > self._max_keys:
                    self._windows.popitem(last=False)
                return True, 0.0
            self._windows.move_to_end(key)
            if window.count >= self._requests:
                return False, self._window_seconds - (now - window.started_at)
            window.count += 1
            return True, 0.0


class _RequestTooLarge(Exception):
    pass


def _request_id(scope: Scope) -> str | None:
    value = _header(scope, b"x-request-id")
    if value is None:
        return None
    try:
        decoded = value.decode("ascii")
    except UnicodeDecodeError:
        return None
    return decoded if REQUEST_ID_PATTERN.fullmatch(decoded) else None


def _rate_key(scope: Scope) -> str:
    authorization = _header(scope, b"authorization")
    client = scope.get("client")
    host = client[0] if client else "unknown"
    if authorization and authorization.lower().startswith(b"bearer "):
        digest = hashlib.sha256(authorization[7:]).hexdigest()
        return f"token:{digest}:{host}"
    return f"anonymous:{host}"


def _header(scope: Scope, name: bytes) -> bytes | None:
    return next((value for key, value in scope.get("headers", []) if key.lower() == name), None)


async def _send_json(
    send: Send,
    status: int,
    payload: dict[str, object],
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    response_headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        *(headers or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": body})
