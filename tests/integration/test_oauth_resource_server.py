from __future__ import annotations

from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from psr_mcp.auth.membership import ResolvedMembership
from psr_mcp.auth.providers import McpAccessTokenAuthContextProvider
from psr_mcp.bootstrap import Container, build_container
from psr_mcp.config import Settings
from psr_mcp.domain.identity import ActorType, Role
from psr_mcp.mcp.server import create_server

ISSUER = "https://idp.example.gov/"
RESOURCE = "http://127.0.0.1:8000/mcp"


class TokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        if token == "invalid":
            return None
        scopes = (
            ["project:read"]
            if token == "missing-base-scope"
            else [
                "mcp:access",
                "project:read",
            ]
        )
        return AccessToken(
            token=token,
            client_id="integration-host",
            scopes=scopes,
            expires_at=2_000_000_000,
            resource=RESOURCE,
            subject="external-subject",
            claims={"iss": ISSUER, "organization_id": "org-development-a"},
        )


class Memberships:
    async def resolve(
        self,
        *,
        issuer: str,
        external_subject: str,
        requested_organization_id: str,
    ) -> ResolvedMembership | None:
        if (
            issuer != ISSUER
            or external_subject != "external-subject"
            or requested_organization_id != "org-development-a"
        ):
            return None
        return ResolvedMembership(
            organization_id="org-development-a",
            subject_id="development-researcher",
            roles=frozenset({Role.RESEARCHER}),
            project_ids=frozenset({"project-public-ai"}),
            actor_type=ActorType.HUMAN,
        )


def _server_app() -> tuple[FastMCP, Starlette]:
    oauth_settings = Settings.from_env({"PSR_AUTH_MODE": "oauth", "PSR_ISSUER_URL": ISSUER})
    base = build_container(Settings.from_env({}))
    assert isinstance(base, Container)
    container = replace(
        base,
        settings=oauth_settings,
        auth_provider=McpAccessTokenAuthContextProvider(Memberships()),
    )
    server = create_server(container, token_verifier=TokenVerifier())
    return server, server.streamable_http_app()


@pytest.mark.anyio
async def test_protected_resource_metadata_and_authentication_challenge() -> None:
    _server, app = _server_app()
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client,
    ):
        metadata = await client.get("/.well-known/oauth-protected-resource/mcp")
        unauthorized = await client.post("/mcp", json={})
        invalid = await client.post("/mcp", json={}, headers={"authorization": "Bearer invalid"})
        insufficient = await client.post(
            "/mcp",
            json={},
            headers={"authorization": "Bearer missing-base-scope"},
        )

    assert metadata.status_code == 200
    assert metadata.json() == {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": ["mcp:access"],
        "bearer_methods_supported": ["header"],
    }
    for response in (unauthorized, invalid):
        assert response.status_code == 401
        assert (
            'resource_metadata="http://127.0.0.1:8000/.well-known/'
            'oauth-protected-resource/mcp"' in response.headers["www-authenticate"]
        )
    assert insufficient.status_code == 403
    assert 'error="insufficient_scope"' in insufficient.headers["www-authenticate"]


@pytest.mark.anyio
async def test_valid_bearer_reaches_mcp_and_membership_bound_tool() -> None:
    _server, app = _server_app()
    transport = ASGITransport(app=app)
    headers = {
        "authorization": "Bearer valid-token",
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
    }
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client,
    ):
        initialized = await client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "oauth-test", "version": "1.0"},
                },
            },
        )
        projects = await client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "psr.project.list", "arguments": {"limit": 20}},
            },
        )

    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == (
        "Public Sector Research MCP [DEVELOPMENT]"
    )
    assert projects.status_code == 200
    result = projects.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["items"][0]["id"] == "project-public-ai"
