"""Production and deterministic runtime adapters."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Uuid4Generator:
    """Temporary opaque ID adapter behind the IdGenerator port."""

    def new(self) -> str:
        return str(uuid.uuid4())
