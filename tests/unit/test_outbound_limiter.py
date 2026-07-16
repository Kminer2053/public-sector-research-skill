from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from psr_mcp.common.outbound import (
    OutboundLimiterCapacityError,
    ProcessOutboundLimiter,
)


class ManualTime:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds
        await asyncio.sleep(0)

    def advance(self, seconds: float) -> None:
        self.value += seconds


class BlockingSleeper:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def sleep(self, seconds: float) -> None:
        assert seconds > 0
        self.started.set()
        await self.release.wait()


@pytest.mark.anyio
async def test_limiter_enforces_global_and_per_host_concurrency() -> None:
    limiter = ProcessOutboundLimiter(max_global=2, max_per_host=1)
    release = asyncio.Event()
    active = 0
    max_active = 0
    active_by_host: dict[str, int] = {}
    max_by_host: dict[str, int] = {}

    async def worker(host: str) -> None:
        nonlocal active, max_active
        async with limiter.slot(host):
            active += 1
            max_active = max(max_active, active)
            active_by_host[host] = active_by_host.get(host, 0) + 1
            max_by_host[host] = max(
                max_by_host.get(host, 0),
                active_by_host[host],
            )
            try:
                await release.wait()
            finally:
                active -= 1
                active_by_host[host] -= 1

    tasks = [
        asyncio.create_task(worker("a.go.kr")),
        asyncio.create_task(worker("a.go.kr")),
        asyncio.create_task(worker("b.go.kr")),
        asyncio.create_task(worker("c.go.kr")),
    ]
    await _wait_until(lambda: max_active == 2)
    release.set()
    await asyncio.gather(*tasks)

    assert max_active == 2
    assert max_by_host["a.go.kr"] == 1
    assert limiter.tracked_host_count == 0


@pytest.mark.anyio
async def test_busy_host_waiters_do_not_consume_global_slots() -> None:
    limiter = ProcessOutboundLimiter(max_global=2, max_per_host=1)
    release_a = asyncio.Event()
    a_entered = asyncio.Event()
    b_entered = asyncio.Event()

    async def first_a() -> None:
        async with limiter.slot("A.GO.KR."):
            a_entered.set()
            await release_a.wait()

    async def second_a() -> None:
        async with limiter.slot("a.go.kr"):
            return

    async def only_b() -> None:
        async with limiter.slot("b.go.kr"):
            b_entered.set()

    first = asyncio.create_task(first_a())
    await a_entered.wait()
    second = asyncio.create_task(second_a())
    await _wait_until(lambda: limiter.tracked_request_count == 2)
    other = asyncio.create_task(only_b())

    await asyncio.wait_for(b_entered.wait(), timeout=0.5)
    assert first.done() is False
    release_a.set()
    await asyncio.gather(first, second, other)
    assert limiter.tracked_host_count == 0


@pytest.mark.anyio
async def test_cancelled_waiter_releases_host_tracking_and_capacity() -> None:
    limiter = ProcessOutboundLimiter(max_global=1, max_per_host=1)
    release = asyncio.Event()
    entered = asyncio.Event()

    async def holder() -> None:
        async with limiter.slot("source.go.kr"):
            entered.set()
            await release.wait()

    holder_task = asyncio.create_task(holder())
    await entered.wait()
    waiter = asyncio.create_task(_enter_once(limiter, "source.go.kr"))
    await _wait_until(lambda: limiter.tracked_request_count == 2)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert limiter.tracked_host_count == 1
    assert limiter.tracked_request_count == 1
    release.set()
    await holder_task
    assert limiter.tracked_host_count == 0

    await asyncio.wait_for(_enter_once(limiter, "source.go.kr"), timeout=0.5)
    assert limiter.tracked_host_count == 0


@pytest.mark.anyio
async def test_cancelled_global_waiter_releases_its_acquired_host_slot() -> None:
    limiter = ProcessOutboundLimiter(max_global=1, max_per_host=1)
    release = asyncio.Event()
    entered = asyncio.Event()

    async def holder() -> None:
        async with limiter.slot("busy.go.kr"):
            entered.set()
            await release.wait()

    holder_task = asyncio.create_task(holder())
    await entered.wait()
    waiter = asyncio.create_task(_enter_once(limiter, "other.go.kr"))
    await _wait_until(
        lambda: limiter.tracked_host_count == 2 and limiter.tracked_request_count == 2
    )
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert limiter.tracked_host_count == 1
    assert limiter.tracked_request_count == 1
    release.set()
    await holder_task
    await asyncio.wait_for(_enter_once(limiter, "other.go.kr"), timeout=0.5)
    assert limiter.tracked_host_count == 0


@pytest.mark.anyio
async def test_per_host_token_bucket_paces_requests_without_cross_host_delay() -> None:
    clock = ManualTime()
    limiter = ProcessOutboundLimiter(
        max_global=4,
        max_per_host=2,
        per_host_rate_requests=2,
        per_host_rate_window_seconds=1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    await _enter_once(limiter, "source.go.kr")
    await _enter_once(limiter, "source.go.kr")
    await _enter_once(limiter, "other.go.kr")
    assert clock.sleeps == []

    await _enter_once(limiter, "source.go.kr")
    await _enter_once(limiter, "source.go.kr")

    assert clock.sleeps == pytest.approx([0.5, 0.5])
    assert limiter.tracked_request_count == 0
    assert limiter.tracked_rate_host_count == 1

    clock.advance(1.1)
    await _enter_once(limiter, "fresh.go.kr")
    assert limiter.tracked_rate_host_count == 1


@pytest.mark.anyio
async def test_cancelled_rate_waiter_releases_concurrency_capacity() -> None:
    sleeper = BlockingSleeper()
    limiter = ProcessOutboundLimiter(
        max_global=1,
        max_per_host=1,
        per_host_rate_requests=1,
        per_host_rate_window_seconds=10,
        sleep=sleeper.sleep,
    )
    await _enter_once(limiter, "source.go.kr")

    waiter = asyncio.create_task(_enter_once(limiter, "source.go.kr"))
    await sleeper.started.wait()
    assert limiter.tracked_request_count == 1
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert limiter.tracked_host_count == 0
    assert limiter.tracked_request_count == 0
    assert limiter.tracked_rate_host_count == 1


@pytest.mark.anyio
async def test_rate_tracking_capacity_fails_closed_without_leaking_host_gate() -> None:
    limiter = ProcessOutboundLimiter(
        max_global=2,
        max_per_host=1,
        per_host_rate_requests=1,
        per_host_rate_window_seconds=60,
        max_rate_hosts=1,
    )
    await _enter_once(limiter, "first.go.kr")

    with pytest.raises(OutboundLimiterCapacityError, match="capacity"):
        await _enter_once(limiter, "second.go.kr")

    assert limiter.tracked_host_count == 0
    assert limiter.tracked_request_count == 0
    assert limiter.tracked_rate_host_count == 1


@pytest.mark.anyio
async def test_rate_pruning_preserves_a_stale_bucket_while_host_is_active() -> None:
    clock = ManualTime()
    limiter = ProcessOutboundLimiter(
        max_global=2,
        max_per_host=1,
        per_host_rate_requests=2,
        per_host_rate_window_seconds=1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    await _enter_once(limiter, "active.go.kr")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with limiter.slot("active.go.kr"):
            entered.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await entered.wait()
    clock.advance(1.1)
    await _enter_once(limiter, "other.go.kr")

    assert limiter.tracked_rate_host_count == 2
    release.set()
    await task


@pytest.mark.parametrize(
    "factory, message",
    [
        (lambda: ProcessOutboundLimiter(max_global=0, max_per_host=1), "max_global"),
        (lambda: ProcessOutboundLimiter(max_global=33, max_per_host=1), "max_global"),
        (lambda: ProcessOutboundLimiter(max_global=8, max_per_host=0), "max_per_host"),
        (lambda: ProcessOutboundLimiter(max_global=8, max_per_host=9), "max_per_host"),
        (lambda: ProcessOutboundLimiter(max_global=1, max_per_host=2), "must not exceed"),
    ],
)
def test_limiter_configuration_fails_closed(
    factory: Callable[[], ProcessOutboundLimiter],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_rate_limiter_configuration_fails_closed() -> None:
    with pytest.raises(ValueError, match="rate_requests"):
        ProcessOutboundLimiter(
            max_global=2,
            max_per_host=1,
            per_host_rate_requests=0,
        )
    with pytest.raises(ValueError, match="rate_requests"):
        ProcessOutboundLimiter(
            max_global=2,
            max_per_host=1,
            per_host_rate_requests=61,
        )
    with pytest.raises(ValueError, match="window_seconds"):
        ProcessOutboundLimiter(
            max_global=2,
            max_per_host=1,
            per_host_rate_window_seconds=0.09,
        )
    with pytest.raises(ValueError, match="window_seconds"):
        ProcessOutboundLimiter(
            max_global=2,
            max_per_host=1,
            per_host_rate_window_seconds=61,
        )
    with pytest.raises(ValueError, match="max_rate_hosts"):
        ProcessOutboundLimiter(
            max_global=2,
            max_per_host=1,
            max_rate_hosts=0,
        )
    with pytest.raises(ValueError, match="max_rate_hosts"):
        ProcessOutboundLimiter(
            max_global=2,
            max_per_host=1,
            max_rate_hosts=10_001,
        )


@pytest.mark.anyio
@pytest.mark.parametrize("host", ["", " source.go.kr", "source .go.kr", "." * 254])
async def test_limiter_rejects_invalid_host_keys(host: str) -> None:
    limiter = ProcessOutboundLimiter(max_global=2, max_per_host=1)
    with pytest.raises(ValueError, match="host"):
        async with limiter.slot(host):
            pass
    assert limiter.tracked_host_count == 0


async def _enter_once(limiter: ProcessOutboundLimiter, host: str) -> None:
    async with limiter.slot(host):
        return


async def _wait_until(predicate: Callable[[], bool]) -> None:
    for _ in range(1_000):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")
