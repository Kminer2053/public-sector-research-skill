from __future__ import annotations

import ipaddress
import ssl
from collections.abc import Iterable

import httpcore
import pytest

from psr_mcp.collectors.httpcore_transport import (
    PinnedHttpcoreTransport,
    SocketOption,
    _validate_content_length,
)
from psr_mcp.collectors.models import CollectionLimits
from psr_mcp.collectors.safe import CollectionError, CollectionErrorCode
from psr_mcp.collectors.url_policy import ValidatedUrl


class ScriptedStream(httpcore.AsyncNetworkStream):
    def __init__(self, response: bytes) -> None:
        self._response = response
        self.writes = bytearray()
        self.server_hostname: str | None = None
        self.closed = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        del timeout
        chunk = self._response[:max_bytes]
        self._response = self._response[max_bytes:]
        return chunk

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        del timeout
        self.writes.extend(buffer)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del ssl_context, timeout
        self.server_hostname = server_hostname
        return self

    def get_extra_info(self, info: str) -> object:
        del info
        return None


class ScriptedBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        response: bytes = b"",
        *,
        error: Exception | None = None,
    ) -> None:
        self.stream = ScriptedStream(response)
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del timeout, local_address, socket_options
        self.calls.append((host, port))
        if self.error is not None:
            raise self.error
        return self.stream

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del path, timeout, socket_options
        raise AssertionError("Unix socket must not be used")

    async def sleep(self, seconds: float) -> None:
        del seconds


def _target(url: str = "https://source.go.kr/document?id=1") -> ValidatedUrl:
    return ValidatedUrl(
        original_url=url,
        canonical_url=url,
        host="source.go.kr",
        port=443,
        resolved_addresses=(ipaddress.ip_address("93.184.216.34"),),
        redirect_count=0,
    )


@pytest.mark.anyio
async def test_transport_pins_ip_preserves_sni_host_and_redacts_headers() -> None:
    backend = ScriptedBackend(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Length: 5\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"ETag: test-etag\r\n"
        b"Set-Cookie: secret=value\r\n"
        b"Connection: close\r\n\r\n"
        b"hello"
    )
    transport = PinnedHttpcoreTransport(
        ssl_context=ssl.create_default_context(),
        network_backend=backend,
    )

    response = await transport.fetch(
        _target(),
        CollectionLimits(max_response_bytes=10),
    )

    assert response.status == 200
    assert response.body == b"hello"
    assert response.headers == {
        "content-length": "5",
        "content-type": "text/plain; charset=utf-8",
        "etag": "test-etag",
    }
    assert backend.calls == [("93.184.216.34", 443)]
    assert backend.stream.server_hostname == "source.go.kr"
    request = bytes(backend.stream.writes)
    assert b"GET /document?id=1 HTTP/1.1" in request
    assert b"Host: source.go.kr" in request
    assert b"Accept-Encoding: identity" in request
    assert backend.stream.closed is True


@pytest.mark.anyio
async def test_transport_returns_redirect_without_reading_body() -> None:
    backend = ScriptedBackend(
        b"HTTP/1.1 302 Found\r\n"
        b"Location: /next\r\n"
        b"Content-Length: 1000\r\n"
        b"Connection: close\r\n\r\n"
    )

    response = await PinnedHttpcoreTransport(network_backend=backend).fetch(
        _target("https://source.go.kr/"),
        CollectionLimits(max_response_bytes=10),
    )

    assert response.status == 302
    assert response.headers["location"] == "/next"
    assert response.body == b""


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response, code",
    [
        (
            b"HTTP/1.1 200 OK\r\nContent-Length: 11\r\nConnection: close\r\n\r\n",
            CollectionErrorCode.RESPONSE_TOO_LARGE,
        ),
        (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Encoding: gzip\r\n"
            b"Content-Length: 4\r\n"
            b"Connection: close\r\n\r\ngzip",
            CollectionErrorCode.CONTENT_ENCODING_NOT_ALLOWED,
        ),
        (
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Connection: close\r\n\r\n"
            b"6\r\n123456\r\n6\r\n789012\r\n0\r\n\r\n",
            CollectionErrorCode.RESPONSE_TOO_LARGE,
        ),
    ],
)
async def test_transport_enforces_header_encoding_and_stream_limits(
    response: bytes,
    code: CollectionErrorCode,
) -> None:
    backend = ScriptedBackend(response)

    with pytest.raises(CollectionError) as error:
        await PinnedHttpcoreTransport(network_backend=backend).fetch(
            _target(),
            CollectionLimits(max_response_bytes=10),
        )

    assert error.value.code is code


@pytest.mark.parametrize("value", ["not-a-number", "-1"])
def test_transport_rejects_invalid_content_length(value: str) -> None:
    with pytest.raises(CollectionError) as error:
        _validate_content_length({"content-length": value}, 10)

    assert error.value.code is CollectionErrorCode.RESPONSE_HEADER_INVALID


@pytest.mark.anyio
@pytest.mark.parametrize(
    "network_error, code",
    [
        (httpcore.ConnectTimeout("timeout"), CollectionErrorCode.NETWORK_TIMEOUT),
        (httpcore.ConnectError("failed"), CollectionErrorCode.NETWORK_FAILED),
    ],
)
async def test_transport_normalizes_network_failures(
    network_error: Exception,
    code: CollectionErrorCode,
) -> None:
    backend = ScriptedBackend(error=network_error)

    with pytest.raises(CollectionError) as error:
        await PinnedHttpcoreTransport(
            network_backend=backend,
            max_connect_attempts=1,
        ).fetch(
            _target(),
            CollectionLimits(max_response_bytes=10),
        )

    assert error.value.code is code
    assert error.value.retryable is True
