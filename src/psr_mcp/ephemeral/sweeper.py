"""Lifecycle-managed purge worker for expired public workspaces."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from psr_mcp.ephemeral.ports import EphemeralWorkspaceStore, PurgeResult

logger = logging.getLogger(__name__)


class PurgeSweeper:
    def __init__(
        self,
        store: EphemeralWorkspaceStore,
        *,
        interval_seconds: int,
    ) -> None:
        self._store = store
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

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
        try:
            results = await self._store.purge_expired()
        except Exception:
            logger.exception("ephemeral purge sweep failed")
            return []
        if results:
            logger.info(
                "ephemeral workspaces purged",
                extra={"purge_count": len(results)},
            )
        return results

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            await self.run_once()
