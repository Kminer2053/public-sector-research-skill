"""HTTP/1.1 transport that connects only to addresses approved by UrlPolicy."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Iterable
from urllib.parse import urlsplit

import httpcore

from psr_mcp.collectors.models import CollectionLimits, RawHttpResponse
from psr_mcp.collectors.safe import CollectionError, CollectionErrorCode
from psr_mcp.collectors.url_policy import IpAddress, ValidatedUrl

type SocketOption = (
    tuple[int, int, int]
    | tuple[int, int, bytes | bytearray]
    | tuple[int, int, None, int]
)


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        *,
        expected_host: str,
        addresses: tuple[IpAddress, ...],
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        if not addresses:
            raise ValueError("pinned backend requires at least one address")
        self._expected_host = expected_host
        self._addresses = addresses
        self._inner = inner or httpcore.AnyIOBackend()
        self._connect_count = 0

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if host.casefold().rstrip(".") != self._expected_host or port != 443:
            raise httpcore.ConnectError("connection target did not match the validated origin")
        address = self._addresses[self._connect_count % len(self._addresses)]
        self._connect_count += 1
        return await self._inner.connect_tcp(
            str(address),
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del path, timeout, socket_options
        raise httpcore.ConnectError("Unix sockets are not available to the public collector")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PinnedHttpcoreTransport:
    def __init__(
        self,
        *,
        ssl_context: ssl.SSLContext | None = None,
        user_agent: str = "public-sector-research-mcp/0.1",
        max_connect_attempts: int = 3,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        if max_connect_attempts < 1 or max_connect_attempts > 3:
            raise ValueError("max_connect_attempts must be 1..3")
        self._ssl_context = ssl_context or ssl.create_default_context()
        self._user_agent = user_agent
        self._max_connect_attempts = max_connect_attempts
        self._network_backend = network_backend

    async def fetch(
        self,
        target: ValidatedUrl,
        limits: CollectionLimits,
    ) -> RawHttpResponse:
        backend = PinnedNetworkBackend(
            expected_host=target.host,
            addresses=target.resolved_addresses,
            inner=self._network_backend,
        )
        attempts = min(self._max_connect_attempts, len(target.resolved_addresses))
        pool = httpcore.AsyncConnectionPool(
            ssl_context=self._ssl_context,
            max_connections=1,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=attempts - 1,
            network_backend=backend,
        )
        request = httpcore.Request(
            method="GET",
            url=httpcore.URL(
                scheme="https",
                host=target.host,
                port=target.port,
                target=_request_target(target.canonical_url),
            ),
            headers=[
                (b"Host", target.host.encode("ascii")),
                (b"User-Agent", self._user_agent.encode("ascii")),
                (
                    b"Accept",
                    b"text/html, application/pdf, application/json, text/plain;q=0.9, */*;q=0.1",
                ),
                (b"Accept-Encoding", b"identity"),
                (b"Connection", b"close"),
            ],
            extensions={
                "timeout": {
                    "connect": limits.connect_timeout_seconds,
                    "read": limits.read_timeout_seconds,
                    "write": limits.write_timeout_seconds,
                    "pool": limits.pool_timeout_seconds,
                }
            },
        )
        try:
            async with asyncio.timeout(limits.total_timeout_seconds), pool:
                response = await pool.handle_async_request(request)
                try:
                    headers = _safe_headers(response.headers)
                    if _is_redirect(response.status):
                        return RawHttpResponse(
                            status=response.status,
                            headers=headers,
                            body=b"",
                        )
                    _validate_content_length(headers, limits.max_response_bytes)
                    encoding = headers.get("content-encoding", "").strip().casefold()
                    if encoding and encoding != "identity":
                        raise CollectionError(
                            CollectionErrorCode.CONTENT_ENCODING_NOT_ALLOWED,
                            "source ignored the identity encoding requirement",
                            retryable=False,
                            http_status=response.status,
                        )
                    body = await _read_bounded(response, limits.max_response_bytes)
                    return RawHttpResponse(
                        status=response.status,
                        headers=headers,
                        body=body,
                    )
                finally:
                    await response.aclose()
        except CollectionError:
            raise
        except (TimeoutError, httpcore.TimeoutException):
            raise CollectionError(
                CollectionErrorCode.NETWORK_TIMEOUT,
                "source request exceeded its network time budget",
                retryable=True,
            ) from None
        except (httpcore.NetworkError, httpcore.ProtocolError):
            raise CollectionError(
                CollectionErrorCode.NETWORK_FAILED,
                "source request failed at the network boundary",
                retryable=True,
            ) from None


async def _read_bounded(response: httpcore.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_stream():
        size += len(chunk)
        if size > max_bytes:
            raise CollectionError(
                CollectionErrorCode.RESPONSE_TOO_LARGE,
                "source response exceeded the byte limit",
                retryable=False,
                http_status=response.status,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_headers(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_name, raw_value in headers:
        name = raw_name.decode("ascii", errors="ignore").casefold()
        if name not in _SAFE_RESPONSE_HEADERS:
            continue
        result[name] = raw_value.decode("latin-1", errors="replace")
    return result


def _validate_content_length(headers: dict[str, str], max_bytes: int) -> None:
    value = headers.get("content-length")
    if value is None:
        return
    try:
        length = int(value)
    except ValueError:
        raise CollectionError(
            CollectionErrorCode.RESPONSE_HEADER_INVALID,
            "source returned an invalid content length",
            retryable=False,
        ) from None
    if length < 0:
        raise CollectionError(
            CollectionErrorCode.RESPONSE_HEADER_INVALID,
            "source returned an invalid content length",
            retryable=False,
        )
    if length > max_bytes:
        raise CollectionError(
            CollectionErrorCode.RESPONSE_TOO_LARGE,
            "source response exceeds the byte limit",
            retryable=False,
        )


def _request_target(url: str) -> str:
    parsed = urlsplit(url)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return target


def _is_redirect(status: int) -> bool:
    return status in {301, 302, 303, 307, 308}


_SAFE_RESPONSE_HEADERS = frozenset(
    {
        "cache-control",
        "content-disposition",
        "content-encoding",
        "content-length",
        "content-type",
        "etag",
        "last-modified",
        "location",
    }
)
