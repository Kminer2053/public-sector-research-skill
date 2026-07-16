"""Authentication context providers for development and verified MCP requests."""

from __future__ import annotations

from typing import Protocol

from mcp.server.auth.middleware.auth_context import get_access_token

from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.auth.membership import MembershipResolver
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.identity import MembershipStatus


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


class McpAccessTokenAuthContextProvider:
    """Resolve a verified SDK access token against internal tenant membership."""

    def __init__(self, memberships: MembershipResolver) -> None:
        self._memberships = memberships

    async def resolve(self) -> AuthorizationContext:
        token = get_access_token()
        if token is None or token.subject is None:
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the authenticated identity is not authorized",
            )
        claims = token.claims or {}
        issuer = claims.get("iss")
        organization_id = claims.get("organization_id")
        if not isinstance(issuer, str) or not isinstance(organization_id, str):
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the authenticated identity is not authorized",
            )
        membership = await self._memberships.resolve(
            issuer=issuer,
            external_subject=token.subject,
            requested_organization_id=organization_id,
        )
        if (
            membership is None
            or membership.status is not MembershipStatus.ACTIVE
            or membership.organization_id != organization_id
        ):
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the authenticated identity is not authorized",
            )
        token_id = claims.get("jti_sha256")
        return AuthorizationContext(
            organization_id=membership.organization_id,
            subject_id=membership.subject_id,
            roles=membership.roles,
            scopes=frozenset(token.scopes),
            project_ids=membership.project_ids,
            actor_type=membership.actor_type,
            token_id=token_id if isinstance(token_id, str) else None,
            client_id=token.client_id,
        )
