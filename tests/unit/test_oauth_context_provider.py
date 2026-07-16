from __future__ import annotations

import contextlib
from collections.abc import Generator

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from psr_mcp.auth.membership import ResolvedMembership
from psr_mcp.auth.providers import McpAccessTokenAuthContextProvider
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.identity import ActorType, MembershipStatus, Role

ORGANIZATION_ID = "00000000-0000-0000-0000-00000000000a"
USER_ID = "00000000-0000-0000-0000-00000000001a"
PROJECT_ID = "00000000-0000-0000-0000-0000000000a1"


class Memberships:
    def __init__(self, result: ResolvedMembership | None) -> None:
        self.result = result
        self.calls: list[tuple[str, str, str]] = []

    async def resolve(
        self,
        *,
        issuer: str,
        external_subject: str,
        requested_organization_id: str,
    ) -> ResolvedMembership | None:
        self.calls.append((issuer, external_subject, requested_organization_id))
        return self.result


def _access_token(*, include_organization: bool = True) -> AccessToken:
    claims = {
        "iss": "https://idp.example.gov",
        "jti_sha256": "hashed-token-id",
    }
    if include_organization:
        claims["organization_id"] = ORGANIZATION_ID
    return AccessToken(
        token="raw-bearer-token-must-not-propagate",
        client_id="codex-host",
        scopes=["mcp:access", "project:read"],
        expires_at=2_000_000_000,
        resource="https://research.example.gov/mcp",
        subject="external-subject-a",
        claims=claims,
    )


@contextlib.contextmanager
def _authenticated(token: AccessToken) -> Generator[None]:
    marker = auth_context_var.set(AuthenticatedUser(token))
    try:
        yield
    finally:
        auth_context_var.reset(marker)


@pytest.mark.anyio
async def test_verified_token_and_membership_create_internal_context_without_raw_token() -> None:
    membership = ResolvedMembership(
        organization_id=ORGANIZATION_ID,
        subject_id=USER_ID,
        roles=frozenset({Role.RESEARCHER}),
        project_ids=frozenset({PROJECT_ID}),
        actor_type=ActorType.HUMAN,
    )
    memberships = Memberships(membership)
    provider = McpAccessTokenAuthContextProvider(memberships)
    with _authenticated(_access_token()):
        result = await provider.resolve()

    assert result.organization_id == ORGANIZATION_ID
    assert result.subject_id == USER_ID
    assert result.roles == frozenset({Role.RESEARCHER})
    assert result.scopes == frozenset({"mcp:access", "project:read"})
    assert result.project_ids == frozenset({PROJECT_ID})
    assert result.token_id == "hashed-token-id"
    assert result.client_id == "codex-host"
    assert "raw-bearer-token" not in repr(result)
    assert memberships.calls == [("https://idp.example.gov", "external-subject-a", ORGANIZATION_ID)]


@pytest.mark.anyio
@pytest.mark.parametrize("missing_organization", [True, False])
async def test_missing_organization_or_membership_is_denied(missing_organization: bool) -> None:
    provider = McpAccessTokenAuthContextProvider(Memberships(None))
    with (
        _authenticated(_access_token(include_organization=not missing_organization)),
        pytest.raises(DomainError) as caught,
    ):
        await provider.resolve()
    assert caught.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN


@pytest.mark.anyio
async def test_revoked_membership_is_denied() -> None:
    membership = ResolvedMembership(
        organization_id=ORGANIZATION_ID,
        subject_id=USER_ID,
        roles=frozenset({Role.RESEARCHER}),
        project_ids=None,
        actor_type=ActorType.HUMAN,
        status=MembershipStatus.REVOKED,
    )
    provider = McpAccessTokenAuthContextProvider(Memberships(membership))
    with _authenticated(_access_token()), pytest.raises(DomainError) as caught:
        await provider.resolve()
    assert caught.value.code is ErrorCode.NOT_FOUND_OR_FORBIDDEN
