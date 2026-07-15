"""Small validation helpers shared by domain values."""

from __future__ import annotations

from datetime import datetime

from psr_mcp.domain.errors import invalid


def require_text(value: str, field: str, *, minimum: int = 1, maximum: int = 200) -> str:
    normalized = value.strip()
    if len(normalized) < minimum or len(normalized) > maximum:
        raise invalid(f"{field} must contain {minimum}..{maximum} characters", field=field)
    return normalized


def require_utc(value: datetime, field: str) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise invalid(f"{field} must be timezone-aware UTC", field=field)
    if offset.total_seconds() != 0:
        raise invalid(f"{field} must use UTC", field=field)
    return value


def require_version(value: int, field: str = "version") -> int:
    if value < 1:
        raise invalid(f"{field} must be at least 1", field=field)
    return value
