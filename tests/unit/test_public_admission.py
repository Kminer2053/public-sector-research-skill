from __future__ import annotations

import os
from pathlib import Path

import pytest

from psr_mcp.public.admission import FilePauseSignal, NeverPauseSignal


def test_never_pause_signal_is_open() -> None:
    assert NeverPauseSignal().paused is False


def test_file_pause_signal_toggles_without_reading_content(tmp_path: Path) -> None:
    signal_path = tmp_path / "public.pause"
    signal = FilePauseSignal(signal_path)

    assert not bool(signal.paused)
    signal_path.write_text("operator note that must not be read", encoding="utf-8")
    assert bool(signal.paused)
    signal_path.unlink()
    assert not bool(signal.paused)


def test_file_pause_signal_fails_closed_for_symlink(tmp_path: Path) -> None:
    missing_target = tmp_path / "missing"
    signal_path = tmp_path / "public.pause"
    os.symlink(missing_target, signal_path)

    assert FilePauseSignal(signal_path).paused is True


def test_file_pause_signal_fails_closed_when_stat_is_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def denied(path: object) -> os.stat_result:
        del path
        raise PermissionError("operator control path is unreadable")

    monkeypatch.setattr(os, "lstat", denied)

    assert FilePauseSignal(tmp_path / "public.pause").paused is True
