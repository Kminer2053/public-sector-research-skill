"""Bounded process-local HTTP policies around the MCP Streamable HTTP app."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
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
    rate_limit_hmac_key: bytes,
    trusted_proxy_cidrs: tuple[str, ...] = (),
) -> ASGIApp:
    policy: ASGIApp = RequestTimeoutMiddleware(
        app,
        timeout_seconds=request_timeout_seconds,
    )
    policy = FixedWindowRateLimitMiddleware(
        policy,
        requests=rate_limit_requests,
        window_seconds=rate_limit_window_seconds,
        hmac_key=rate_limit_hmac_key,
    )
    policy = RequestBodyLimitMiddleware(policy, max_bytes=max_request_bytes)
    policy = TrustedClientIpMiddleware(
        policy,
        trusted_proxy_cidrs=trusted_proxy_cidrs,
    )
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


class TrustedClientIpMiddleware:
    """Accept one canonical client IP only from explicitly trusted proxy networks."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_proxy_cidrs: tuple[str, ...],
        header_name: bytes = b"x-psr-client-ip",
    ) -> None:
        self._app = app
        self._trusted_proxies = tuple(
            ipaddress.ip_network(value, strict=False) for value in trusted_proxy_cidrs
        )
        self._header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/mcp" or not self._trusted_proxies:
            await self._app(scope, receive, send)
            return
        peer = scope.get("client")
        if peer is None:
            await _send_json(send, 400, {"error": "client_ip_unavailable"})
            return
        try:
            peer_ip = ipaddress.ip_address(peer[0])
        except ValueError:
            await _send_json(send, 400, {"error": "client_ip_invalid"})
            return
        if not any(peer_ip in network for network in self._trusted_proxies):
            await self._app(_without_header(scope, self._header_name), receive, send)
            return
        forwarded = _header(scope, self._header_name)
        if forwarded is None:
            await _send_json(send, 400, {"error": "trusted_proxy_client_ip_missing"})
            return
        try:
            client_ip = ipaddress.ip_address(forwarded.decode("ascii").strip())
        except (UnicodeDecodeError, ValueError):
            await _send_json(send, 400, {"error": "trusted_proxy_client_ip_invalid"})
            return
        normalized_scope = {
            **_without_header(scope, self._header_name),
            "client": (str(client_ip), peer[1]),
        }
        await self._app(normalized_scope, receive, send)


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
        wall_time: Callable[[], float] = time.time,
        hmac_key: bytes,
        key_rotation_seconds: int = 86_400,
    ) -> None:
        if len(hmac_key) < 32:
            raise ValueError("rate-limit HMAC key must contain at least 32 bytes")
        self._app = app
        self._requests = requests
        self._window_seconds = window_seconds
        self._max_keys = max_keys
        self._monotonic = monotonic
        self._wall_time = wall_time
        self._hmac_key = hmac_key
        self._key_rotation_seconds = key_rotation_seconds
        self._windows: OrderedDict[str, _Window] = OrderedDict()
        self._lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/mcp":
            await self._app(scope, receive, send)
            return
        retry_after = 0.0
        for key in _rate_keys(
            scope,
            hmac_key=self._hmac_key,
            wall_time=self._wall_time(),
            rotation_seconds=self._key_rotation_seconds,
        ):
            allowed, key_retry_after = await self._consume(key)
            retry_after = max(retry_after, key_retry_after)
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


def _rate_keys(
    scope: Scope,
    *,
    hmac_key: bytes,
    wall_time: float,
    rotation_seconds: int,
) -> tuple[str, ...]:
    authorization = _header(scope, b"authorization")
    client = scope.get("client")
    host = client[0] if client else "unknown"
    rotation = int(wall_time // rotation_seconds)
    ip_digest = hmac.new(
        hmac_key,
        f"{rotation}:{host}".encode(),
        hashlib.sha256,
    ).hexdigest()
    keys = [f"ip:{rotation}:{ip_digest}"]
    if authorization and authorization.lower().startswith(b"bearer "):
        digest = hashlib.sha256(authorization[7:]).hexdigest()
        keys.append(f"credential:{rotation}:{ip_digest}:{digest}")
    return tuple(keys)


def _header(scope: Scope, name: bytes) -> bytes | None:
    return next((value for key, value in scope.get("headers", []) if key.lower() == name), None)


def _without_header(scope: Scope, name: bytes) -> Scope:
    return {
        **scope,
        "headers": [(key, value) for key, value in scope.get("headers", []) if key.lower() != name],
    }


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
