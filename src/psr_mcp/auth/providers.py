"""Authentication context provider ports and development implementation."""

from __future__ import annotations

from typing import Protocol

from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.domain.errors import DomainError, ErrorCode


class AuthContextProvider(Protocol):
    async def resolve(self) -> AuthorizationContext: ...


class StaticAuthContextProvider:
    """Development/test only provider selected by the composition root."""

    def __init__(self, context: AuthorizationContext) -> None:
        self._context = context

    async def resolve(self) -> AuthorizationContext:
        return self._context


class UnconfiguredOAuthContextProvider:
    """Fail-closed placeholder until the production OAuth adapter increment."""

    async def resolve(self) -> AuthorizationContext:
        raise DomainError(
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            "production OAuth context provider is not configured",
        )
