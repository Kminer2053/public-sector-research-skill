"""Lifecycle-managed purge worker for expired public workspaces."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from psr_mcp.ephemeral.ports import (
    EphemeralWorkspaceStore,
    PurgeBatchError,
    PurgeResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PurgeSweepState:
    consecutive_failures: int
    next_run_seconds: float
    alert_active: bool


class PurgeSweeper:
    def __init__(
        self,
        store: EphemeralWorkspaceStore,
        *,
        interval_seconds: float,
        retry_initial_seconds: float = 1.0,
        retry_max_seconds: float | None = None,
        alert_after_failures: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("purge sweep interval must be positive")
        if retry_initial_seconds <= 0:
            raise ValueError("purge retry initial delay must be positive")
        retry_max = (
            max(interval_seconds, retry_initial_seconds)
            if retry_max_seconds is None
            else retry_max_seconds
        )
        if retry_max < retry_initial_seconds:
            raise ValueError("purge retry maximum must not precede initial delay")
        if alert_after_failures < 1:
            raise ValueError("purge alert threshold must be positive")
        self._store = store
        self._interval_seconds = interval_seconds
        self._retry_initial_seconds = retry_initial_seconds
        self._retry_max_seconds = retry_max
        self._alert_after_failures = alert_after_failures
        self._sleep = sleep
        self._monotonic = monotonic
        self._consecutive_failures = 0
        self._next_run_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def state(self) -> PurgeSweepState:
        return PurgeSweepState(
            consecutive_failures=self._consecutive_failures,
            next_run_seconds=self._next_run_seconds,
            alert_active=self._consecutive_failures >= self._alert_after_failures,
        )

    async def start(self) -> list[PurgeResult]:
        results = await self.run_once()
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="psr-ephemeral-purge")
        return results

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await self.run_once()

    async def run_once(self) -> list[PurgeResult]:
        started = self._monotonic()
        try:
            results = await self._store.purge_expired()
        except PurgeBatchError as error:
            results = list(error.successful_results)
            self._record_failure(
                failure_count=error.failure_count,
                duration_seconds=self._monotonic() - started,
            )
        except Exception:
            results = []
            self._record_failure(
                failure_count=1,
                duration_seconds=self._monotonic() - started,
            )
        else:
            self._record_success()
        if results:
            logger.info(
                "ephemeral workspaces purged",
                extra={"purge_count": len(results)},
            )
        return results

    async def _run(self) -> None:
        while True:
            await self._sleep(self._next_run_seconds)
            await self.run_once()

    def _record_failure(
        self,
        *,
        failure_count: int,
        duration_seconds: float,
    ) -> None:
        self._consecutive_failures += 1
        exponent = min(self._consecutive_failures - 1, 30)
        self._next_run_seconds = min(
            self._retry_initial_seconds * (2**exponent),
            self._retry_max_seconds,
        )
        alert_active = self._consecutive_failures >= self._alert_after_failures
        log = logger.error if alert_active else logger.warning
        log(
            "ephemeral_purge_alert" if alert_active else "ephemeral_purge_retry_scheduled",
            extra={
                "purge_failure_count": failure_count,
                "purge_consecutive_failures": self._consecutive_failures,
                "purge_retry_seconds": self._next_run_seconds,
                "purge_alert_active": alert_active,
                "purge_duration_bucket": _duration_bucket(duration_seconds),
            },
        )

    def _record_success(self) -> None:
        previous_failures = self._consecutive_failures
        self._consecutive_failures = 0
        self._next_run_seconds = self._interval_seconds
        if previous_failures:
            logger.info(
                "ephemeral_purge_recovered",
                extra={"purge_previous_consecutive_failures": previous_failures},
            )


def _duration_bucket(duration_seconds: float) -> str:
    if duration_seconds < 0.1:
        return "lt_100ms"
    if duration_seconds < 1:
        return "lt_1s"
    if duration_seconds < 10:
        return "lt_10s"
    return "gte_10s"
