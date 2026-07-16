from __future__ import annotations

import asyncio
from typing import cast

import pytest

from psr_mcp.ephemeral.ports import EphemeralWorkspaceStore, PurgeBatchError, PurgeResult
from psr_mcp.ephemeral.sweeper import PurgeSweeper


class Store:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.failure_message = "transient deletion failure"
        self.batch_error: PurgeBatchError | None = None
        self.results: list[PurgeResult] = []

    async def purge_expired(self) -> list[PurgeResult]:
        self.calls += 1
        if self.batch_error is not None:
            raise self.batch_error
        if self.fail:
            raise RuntimeError(self.failure_message)
        return self.results


@pytest.mark.anyio
async def test_sweeper_start_is_idempotent_and_stop_runs_final_sweep() -> None:
    store = Store()
    store.results = [PurgeResult(workspace_id="expired", deleted=True)]
    sweeper = PurgeSweeper(
        cast(EphemeralWorkspaceStore, store),
        interval_seconds=60,
    )

    await sweeper.start()
    await sweeper.start()
    await asyncio.sleep(0)
    await sweeper.stop()

    assert store.calls >= 3
    await sweeper.stop()


@pytest.mark.anyio
async def test_background_loop_uses_retry_delay_then_returns_to_normal_interval() -> None:
    store = Store()
    store.fail = True
    delays: list[float] = []
    second_sleep_started = asyncio.Event()

    async def controlled_sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 1:
            store.fail = False
            return
        second_sleep_started.set()
        raise asyncio.CancelledError

    sweeper = PurgeSweeper(
        cast(EphemeralWorkspaceStore, store),
        interval_seconds=60,
        retry_initial_seconds=1,
        sleep=controlled_sleep,
    )

    await sweeper.start()
    await second_sleep_started.wait()
    await sweeper.stop()

    assert delays == [1, 60]
    assert sweeper.state.consecutive_failures == 0


@pytest.mark.anyio
async def test_sweeper_contains_transient_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    store = Store()
    store.fail = True
    store.failure_message = "QUESTION-CONTENT-CANARY /secret/workspace-id"
    sweeper = PurgeSweeper(
        cast(EphemeralWorkspaceStore, store),
        interval_seconds=60,
        retry_initial_seconds=1,
        retry_max_seconds=8,
        alert_after_failures=3,
    )

    assert await sweeper.run_once() == []
    first_state = sweeper.state
    assert first_state.consecutive_failures == 1
    assert first_state.next_run_seconds == 1
    assert not first_state.alert_active
    assert "ephemeral_purge_retry_scheduled" in caplog.text

    assert await sweeper.run_once() == []
    assert sweeper.state.next_run_seconds == 2
    assert await sweeper.run_once() == []
    alert_state = sweeper.state
    assert alert_state.next_run_seconds == 4
    assert alert_state.alert_active
    assert "ephemeral_purge_alert" in caplog.text
    assert "QUESTION-CONTENT-CANARY" not in caplog.text
    assert "/secret/workspace-id" not in caplog.text
    failure_records = [
        record
        for record in caplog.records
        if record.message in {"ephemeral_purge_retry_scheduled", "ephemeral_purge_alert"}
    ]
    assert failure_records
    assert all(
        getattr(record, "purge_duration_bucket", None) == "lt_100ms" for record in failure_records
    )
    assert all(not hasattr(record, "purge_error_type") for record in failure_records)

    store.fail = False
    assert await sweeper.run_once() == []
    recovered_state = sweeper.state
    assert recovered_state.consecutive_failures == 0
    assert recovered_state.next_run_seconds == 60
    assert not recovered_state.alert_active
    assert "ephemeral_purge_recovered" in caplog.text


@pytest.mark.anyio
async def test_sweeper_preserves_partial_success_without_logging_workspace_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = Store()
    store.batch_error = PurgeBatchError(
        failure_count=2,
        successful_results=(PurgeResult(workspace_id="WORKSPACE-HANDLE-CANARY", deleted=True),),
    )
    sweeper = PurgeSweeper(
        cast(EphemeralWorkspaceStore, store),
        interval_seconds=60,
    )

    results = await sweeper.run_once()

    assert len(results) == 1
    assert results[0].deleted is True
    assert sweeper.state.consecutive_failures == 1
    assert "WORKSPACE-HANDLE-CANARY" not in caplog.text


def test_sweeper_configuration_is_bounded() -> None:
    store = cast(EphemeralWorkspaceStore, Store())
    with pytest.raises(ValueError, match="positive"):
        PurgeBatchError(failure_count=0)
    with pytest.raises(ValueError, match="interval"):
        PurgeSweeper(store, interval_seconds=0)
    with pytest.raises(ValueError, match="initial"):
        PurgeSweeper(store, interval_seconds=60, retry_initial_seconds=0)
    with pytest.raises(ValueError, match="maximum"):
        PurgeSweeper(
            store,
            interval_seconds=60,
            retry_initial_seconds=2,
            retry_max_seconds=1,
        )
    with pytest.raises(ValueError, match="threshold"):
        PurgeSweeper(store, interval_seconds=60, alert_after_failures=0)


@pytest.mark.parametrize(
    "duration, expected",
    [
        (0.09, "lt_100ms"),
        (0.1, "lt_1s"),
        (1, "lt_10s"),
        (10, "gte_10s"),
    ],
)
@pytest.mark.anyio
async def test_failure_duration_is_content_free_bucket(
    duration: float,
    expected: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = Store()
    store.fail = True
    values = iter((0.0, duration))
    sweeper = PurgeSweeper(
        cast(EphemeralWorkspaceStore, store),
        interval_seconds=60,
        monotonic=lambda: next(values),
    )

    await sweeper.run_once()

    record = caplog.records[-1]
    assert getattr(record, "purge_duration_bucket", None) == expected
