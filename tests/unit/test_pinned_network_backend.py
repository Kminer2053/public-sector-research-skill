from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from typing import cast

import httpcore
import pytest

from psr_mcp.collectors.httpcore_transport import PinnedNetworkBackend, SocketOption


class Stream(httpcore.AsyncNetworkStream):
    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        del max_bytes, timeout
        return b""

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        del buffer, timeout

    async def aclose(self) -> None:
        return

    async def start_tls(
        self,
        ssl_context: object,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del ssl_context, server_hostname, timeout
        return self


class Backend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.sleeps: list[float] = []

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
        return Stream()

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del path, timeout, socket_options
        return Stream()

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


@pytest.mark.anyio
async def test_pinned_backend_connects_only_to_validated_addresses_and_rotates() -> None:
    inner = Backend()
    backend = PinnedNetworkBackend(
        expected_host="source.go.kr",
        addresses=(
            ipaddress.ip_address("93.184.216.34"),
            ipaddress.ip_address("93.184.216.35"),
        ),
        inner=cast(httpcore.AsyncNetworkBackend, inner),
    )

    await backend.connect_tcp("source.go.kr", 443)
    await backend.connect_tcp("source.go.kr", 443)
    await backend.sleep(0.1)

    assert inner.calls == [("93.184.216.34", 443), ("93.184.216.35", 443)]
    assert inner.sleeps == [0.1]

    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("attacker.example", 443)
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("source.go.kr", 80)
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_unix_socket("/tmp/socket")


def test_pinned_backend_and_transport_configuration_fail_closed() -> None:
    from psr_mcp.collectors.httpcore_transport import PinnedHttpcoreTransport

    with pytest.raises(ValueError, match="at least one"):
        PinnedNetworkBackend(expected_host="source.go.kr", addresses=())
    with pytest.raises(ValueError, match=r"1\.\.3"):
        PinnedHttpcoreTransport(max_connect_attempts=4)
