"""Value objects for bounded public document collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CollectionLimits:
    max_response_bytes: int = 10_485_760
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    write_timeout_seconds: float = 5.0
    pool_timeout_seconds: float = 5.0
    total_timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if self.max_response_bytes < 1 or self.max_response_bytes > 104_857_600:
            raise ValueError("max_response_bytes must be 1..104857600")
        component_timeouts = (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.write_timeout_seconds,
            self.pool_timeout_seconds,
        )
        if any(value <= 0 or value > 60 for value in component_timeouts):
            raise ValueError("component collection timeouts must be >0 and <=60")
        if self.total_timeout_seconds <= 0 or self.total_timeout_seconds > 120:
            raise ValueError("total collection timeout must be >0 and <=120")


@dataclass(frozen=True, slots=True)
class RawHttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class CollectedDocument:
    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    status: int
    headers: dict[str, str]
    content_type: str | None
    body: bytes
    sha256: str
    retrieved_at: datetime
