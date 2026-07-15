"""Stable domain errors exposed through adapter-specific error mapping."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INPUT_INVALID = "INPUT_INVALID"
    AUTH_SCOPE_REQUIRED = "AUTH_SCOPE_REQUIRED"
    NOT_FOUND_OR_FORBIDDEN = "NOT_FOUND_OR_FORBIDDEN"
    PLAN_NOT_APPROVED = "PLAN_NOT_APPROVED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    INVALID_STATE = "INVALID_STATE"
    LEASE_CONFLICT = "LEASE_CONFLICT"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DomainError(Exception):
    """An expected, safe-to-map application/domain failure."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


def invalid(message: str, *, field: str | None = None) -> DomainError:
    details = {"field": field} if field else None
    return DomainError(ErrorCode.INPUT_INVALID, message, details=details)
