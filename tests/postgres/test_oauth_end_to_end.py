from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from psr_mcp.auth.tokens import OidcJwtTokenVerifier, OidcVerifierSettings
from psr_mcp.bootstrap import build_container
from psr_mcp.common.secrets import EnvironmentSecretResolver
from psr_mcp.config import Settings
from psr_mcp.mcp.server import create_http_app

from .conftest import ORG_A, ORG_B, PLAN_A1, TEST_ISSUER, PostgresUrls

RESOURCE = "http://127.0.0.1:8000/mcp"


def _key() -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    assert isinstance(jwk, dict)
    jwk.update({"kid": "integration-key", "alg": "RS256", "use": "sig"})
    return private_key, jwk


def _token(
    private_key: rsa.RSAPrivateKey,
    *,
    organization_id: str = ORG_A,
    subject: str = "subject-a",
    issuer: str = TEST_ISSUER,
    audience: str = RESOURCE,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "exp": now + 300,
            "iat": now,
            "client_id": "postgres-oauth-test",
            "scope": "mcp:access project:read research:run",
            "organization_id": organization_id,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "integration-key", "typ": "at+jwt"},
    )


def _oidc_handler(jwk: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        payload: dict[str, object]
        if request.url.path.endswith("/.well-known/openid-configuration"):
            payload = {"issuer": TEST_ISSUER, "jwks_uri": f"{TEST_ISSUER}jwks"}
        elif request.url.path == "/jwks":
            payload = {"keys": [jwk]}
        else:
            return httpx.Response(404, request=request)
        return httpx.Response(
            200,
            request=request,
            content=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
        )

    return handler


def _tool_request(raw_token: str) -> tuple[dict[str, str], dict[str, object]]:
    return (
        {
            "authorization": f"Bearer {raw_token}",
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "psr.project.list", "arguments": {"limit": 20}},
        },
    )


def _run_start_request(raw_token: str) -> tuple[dict[str, str], dict[str, object]]:
    headers, _ = _tool_request(raw_token)
    return (
        headers,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "psr.research.run.start",
                "arguments": {
                    "approved_plan_id": PLAN_A1,
                    "idempotency_key": "oauth-audit-trace-0001",
                },
            },
        },
    )


@pytest.mark.postgres
@pytest.mark.oauth
@pytest.mark.anyio
async def test_real_jwt_mcp_and_postgres_membership_boundary(
    seeded_postgres: PostgresUrls,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_key, jwk = _key()
    oidc_client = httpx.AsyncClient(transport=httpx.MockTransport(_oidc_handler(jwk)))
    settings = Settings.from_env(
        {
            "PSR_AUTH_MODE": "oauth",
            "PSR_STORAGE_MODE": "postgres",
            "PSR_ISSUER_URL": TEST_ISSUER,
            "PSR_DATABASE_URL_REF": "env://PSR_DATABASE_URL",
        }
    )
    container = build_container(
        settings,
        secret_resolver=EnvironmentSecretResolver({"PSR_DATABASE_URL": seeded_postgres.runtime}),
    )
    verifier = OidcJwtTokenVerifier(
        OidcVerifierSettings(
            issuer=TEST_ISSUER,
            audience=RESOURCE,
            allow_insecure_http=True,
        ),
        http_client=oidc_client,
    )
    container = replace(container, token_verifier=verifier)
    app = create_http_app(container)
    valid_token = _token(private_key)
    manipulated_token = _token(private_key, organization_id=ORG_B)
    wrong_audience_token = _token(private_key, audience="https://other.example.gov/mcp")

    async with (
        oidc_client,
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client,
    ):
        headers, payload = _tool_request(valid_token)
        valid = await client.post("/mcp", headers=headers, json=payload)

        headers, payload = _run_start_request(valid_token)
        started = await client.post("/mcp", headers=headers, json=payload)
        started_output = started.json()["result"]["structuredContent"]
        operation_id = started_output["operation_id"]
        run_id = started_output["run"]["id"]

        with psycopg.connect(seeded_postgres.owner) as connection:
            connection.execute("SELECT set_config('app.organization_id', %s, true)", (ORG_A,))
            audit_row = connection.execute(
                """
                SELECT operation_id, operation, target_id, outcome, actor_subject_id
                  FROM audit_events
                 WHERE organization_id = %s AND operation_id = %s
                """,
                (ORG_A, operation_id),
            ).fetchone()

        headers, payload = _tool_request(manipulated_token)
        manipulated = await client.post("/mcp", headers=headers, json=payload)

        headers, payload = _tool_request(wrong_audience_token)
        wrong_audience = await client.post("/mcp", headers=headers, json=payload)

        with psycopg.connect(seeded_postgres.owner) as connection:
            connection.execute("SELECT set_config('app.organization_id', %s, true)", (ORG_A,))
            connection.execute(
                "UPDATE memberships SET status = 'REVOKED' WHERE organization_id = %s",
                (ORG_A,),
            )
        headers, payload = _tool_request(valid_token)
        revoked = await client.post("/mcp", headers=headers, json=payload)

    assert valid.status_code == 200
    assert valid.json()["result"]["structuredContent"]["items"][0]["id"] == (
        "00000000-0000-0000-0000-0000000000a1"
    )
    assert started.status_code == 200
    assert audit_row == (
        operation_id,
        "research.run.start",
        run_id,
        "SUCCEEDED",
        "00000000-0000-0000-0000-00000000001a",
    )
    assert manipulated.status_code == 200
    assert manipulated.json()["result"]["isError"] is True
    assert "NOT_FOUND_OR_FORBIDDEN" in manipulated.text
    assert wrong_audience.status_code == 401
    assert revoked.status_code == 200
    assert revoked.json()["result"]["isError"] is True
    assert "NOT_FOUND_OR_FORBIDDEN" in revoked.text
    assert valid_token not in caplog.text
    assert manipulated_token not in caplog.text
