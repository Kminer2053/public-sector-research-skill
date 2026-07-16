"""Process-local concurrency policy shared by all outbound HTTP adapters."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Protocol


class OutboundLimiter(Protocol):
    """Acquire capacity for one outbound request to a validated host."""

    def slot(self, host: str) -> AbstractAsyncContextManager[None]: ...


@dataclass(slots=True)
class _HostGate:
    semaphore: asyncio.Semaphore
    borrowers: int = 0


class OutboundConcurrencyLimiter:
    """Bound total and per-host outbound requests within one event loop.

    A task acquires its host gate before the global gate. Consequently, tasks
    queued behind a busy host do not consume scarce global capacity that a
    different host could use. Host gates are removed as soon as their active
    and waiting borrower count reaches zero, so untrusted historical hostnames
    cannot grow the map without bound.
    """

    def __init__(self, *, max_global: int, max_per_host: int) -> None:
        if max_global < 1 or max_global > 32:
            raise ValueError("max_global must be 1..32")
        if max_per_host < 1 or max_per_host > 8:
            raise ValueError("max_per_host must be 1..8")
        if max_per_host > max_global:
            raise ValueError("max_per_host must not exceed max_global")
        self._global = asyncio.Semaphore(max_global)
        self._max_per_host = max_per_host
        self._hosts: dict[str, _HostGate] = {}

    @property
    def tracked_host_count(self) -> int:
        """Return current active/waiting host gates for diagnostics and tests."""

        return len(self._hosts)

    @property
    def tracked_request_count(self) -> int:
        """Return active and waiting requests without exposing hostnames."""

        return sum(gate.borrowers for gate in self._hosts.values())

    @asynccontextmanager
    async def slot(self, host: str) -> AsyncIterator[None]:
        key = _canonical_host(host)
        gate = self._borrow_host(key)
        host_acquired = False
        global_acquired = False
        try:
            await gate.semaphore.acquire()
            host_acquired = True
            await self._global.acquire()
            global_acquired = True
            yield
        finally:
            if global_acquired:
                self._global.release()
            if host_acquired:
                gate.semaphore.release()
            self._return_host(key, gate)

    def _borrow_host(self, key: str) -> _HostGate:
        gate = self._hosts.get(key)
        if gate is None:
            gate = _HostGate(asyncio.Semaphore(self._max_per_host))
            self._hosts[key] = gate
        gate.borrowers += 1
        return gate

    def _return_host(self, key: str, gate: _HostGate) -> None:
        gate.borrowers -= 1
        if gate.borrowers == 0 and self._hosts.get(key) is gate:
            del self._hosts[key]


def _canonical_host(host: str) -> str:
    if not host or host != host.strip() or any(character.isspace() for character in host):
        raise ValueError("outbound host must be non-blank without whitespace")
    canonical = host.rstrip(".").casefold()
    if not canonical or len(canonical) > 253:
        raise ValueError("outbound host must be 1..253 characters")
    return canonical
