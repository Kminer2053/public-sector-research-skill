"""Content-free operator admission signals for public research."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class PauseSignal(Protocol):
    @property
    def paused(self) -> bool: ...


class NeverPauseSignal:
    @property
    def paused(self) -> bool:
        return False


class FilePauseSignal:
    """Pause while an operator-controlled filesystem entry exists.

    The signal reads metadata only. Symlinks, directories, broken links, and
    unexpected stat failures all fail closed as paused.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def paused(self) -> bool:
        try:
            os.lstat(self._path)
        except FileNotFoundError:
            return False
        except OSError:
            return True
        return True
