"""Process-local concurrency and pacing shared by outbound HTTP adapters."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Protocol, cast


class OutboundLimiter(Protocol):
    """Acquire capacity for one outbound request to a validated host."""

    def slot(self, host: str) -> AbstractAsyncContextManager[None]: ...


@dataclass(slots=True)
class _HostGate:
    semaphore: asyncio.Semaphore
    borrowers: int = 0


@dataclass(slots=True)
class _RateBucket:
    tokens: float
    updated_at: float


class OutboundLimiterCapacityError(RuntimeError):
    """Raised when bounded per-host rate tracking cannot admit another host."""


class ProcessOutboundLimiter:
    """Bound and pace outbound requests within one event loop.

    A task acquires its host concurrency gate and rate permit before the global
    gate. Consequently, tasks queued or paced behind a busy host do not consume
    scarce global capacity that a different host could use. Concurrency gates
    disappear when their borrowers reach zero. Optional token-bucket state is
    time-pruned and hard-bounded.
    """

    def __init__(
        self,
        *,
        max_global: int,
        max_per_host: int,
        per_host_rate_requests: int | None = None,
        per_host_rate_window_seconds: float = 1.0,
        max_rate_hosts: int = 10_000,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_global < 1 or max_global > 32:
            raise ValueError("max_global must be 1..32")
        if max_per_host < 1 or max_per_host > 8:
            raise ValueError("max_per_host must be 1..8")
        if max_per_host > max_global:
            raise ValueError("max_per_host must not exceed max_global")
        if per_host_rate_requests is not None and (
            per_host_rate_requests < 1 or per_host_rate_requests > 60
        ):
            raise ValueError("per_host_rate_requests must be 1..60")
        if per_host_rate_window_seconds < 0.1 or per_host_rate_window_seconds > 60:
            raise ValueError("per_host_rate_window_seconds must be 0.1..60")
        if max_rate_hosts < 1 or max_rate_hosts > 10_000:
            raise ValueError("max_rate_hosts must be 1..10000")
        self._global = asyncio.Semaphore(max_global)
        self._max_per_host = max_per_host
        self._hosts: dict[str, _HostGate] = {}
        self._rate_capacity = per_host_rate_requests
        self._rate_window_seconds = per_host_rate_window_seconds
        self._max_rate_hosts = max_rate_hosts
        self._rate_buckets: OrderedDict[str, _RateBucket] = OrderedDict()
        self._rate_lock = asyncio.Lock()
        self._monotonic = monotonic
        self._sleep = sleep

    @property
    def tracked_host_count(self) -> int:
        """Return current active/waiting host gates for diagnostics and tests."""

        return len(self._hosts)

    @property
    def tracked_request_count(self) -> int:
        """Return active and waiting requests without exposing hostnames."""

        return sum(gate.borrowers for gate in self._hosts.values())

    @property
    def tracked_rate_host_count(self) -> int:
        """Return bounded token-bucket count without exposing hostnames."""

        return len(self._rate_buckets)

    @asynccontextmanager
    async def slot(self, host: str) -> AsyncIterator[None]:
        key = _canonical_host(host)
        gate = self._borrow_host(key)
        host_acquired = False
        global_acquired = False
        try:
            await gate.semaphore.acquire()
            host_acquired = True
            await self._wait_for_rate(key)
            await self._global.acquire()
            global_acquired = True
            yield
        finally:
            if global_acquired:
                self._global.release()
            if host_acquired:
                gate.semaphore.release()
            self._return_host(key, gate)

    async def _wait_for_rate(self, key: str) -> None:
        if self._rate_capacity is None:
            return
        while True:
            async with self._rate_lock:
                delay = self._consume_or_delay(key, self._monotonic())
            if delay <= 0:
                return
            await self._sleep(delay)

    def _consume_or_delay(self, key: str, now: float) -> float:
        capacity = cast(int, self._rate_capacity)
        self._prune_rate_buckets(now)
        bucket = self._rate_buckets.get(key)
        if bucket is None:
            if len(self._rate_buckets) >= self._max_rate_hosts:
                raise OutboundLimiterCapacityError(
                    "outbound per-host rate tracking capacity is exhausted"
                )
            bucket = _RateBucket(tokens=float(capacity), updated_at=now)
            self._rate_buckets[key] = bucket
        else:
            elapsed = max(0.0, now - bucket.updated_at)
            refill_per_second = capacity / self._rate_window_seconds
            bucket.tokens = min(
                float(capacity),
                bucket.tokens + elapsed * refill_per_second,
            )
            bucket.updated_at = now
            self._rate_buckets.move_to_end(key)
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return 0.0
        refill_per_second = capacity / self._rate_window_seconds
        return (1.0 - bucket.tokens) / refill_per_second

    def _prune_rate_buckets(self, now: float) -> None:
        stale_before = now - self._rate_window_seconds
        for key, bucket in tuple(self._rate_buckets.items()):
            if bucket.updated_at > stale_before:
                break
            if key in self._hosts:
                continue
            del self._rate_buckets[key]

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
