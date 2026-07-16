from __future__ import annotations

import asyncio
from typing import cast

import pytest

from psr_mcp.ephemeral.ports import EphemeralWorkspaceStore, PurgeResult
from psr_mcp.ephemeral.sweeper import PurgeSweeper


class Store:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.results: list[PurgeResult] = []

    async def purge_expired(self) -> list[PurgeResult]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("transient deletion failure")
        return self.results


@pytest.mark.anyio
async def test_sweeper_start_is_idempotent_and_stop_runs_final_sweep() -> None:
    store = Store()
    store.results = [PurgeResult(workspace_id="expired", deleted=True)]
    sweeper = PurgeSweeper(
        cast(EphemeralWorkspaceStore, store),
        interval_seconds=0,
    )

    await sweeper.start()
    await sweeper.start()
    await asyncio.sleep(0)
    await sweeper.stop()

    assert store.calls >= 3
    await sweeper.stop()


@pytest.mark.anyio
async def test_sweeper_contains_transient_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = Store()
    store.fail = True
    sweeper = PurgeSweeper(
        cast(EphemeralWorkspaceStore, store),
        interval_seconds=60,
    )

    assert await sweeper.run_once() == []
    assert "ephemeral purge sweep failed" in caplog.text
