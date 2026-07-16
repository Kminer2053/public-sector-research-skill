from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from psr_mcp.auth.tokens import (
    OidcJwtTokenVerifier,
    OidcVerifierSettings,
    _extract_scopes,
    _origin,
    _required_int,
    _required_string,
    _select_jwk,
)

ISSUER = "https://idp.example.gov"
AUDIENCE = "https://research.example.gov/mcp"
ORGANIZATION_ID = "00000000-0000-0000-0000-00000000000a"


@dataclass(slots=True)
class OidcFixture:
    keys: list[dict[str, Any]] = field(default_factory=list)
    unavailable: bool = False
    discovery_calls: int = 0
    jwks_calls: int = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            self.discovery_calls += 1
            return _json_response(
                request,
                {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/jwks"},
            )
        if request.url.path == "/jwks":
            self.jwks_calls += 1
            if self.unavailable:
                raise httpx.ConnectError("authorization server unavailable", request=request)
            return _json_response(request, {"keys": self.keys})
        return httpx.Response(404, request=request)


def _json_response(request: httpx.Request, payload: object) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )


def _new_key(key_id: str) -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    assert isinstance(jwk, dict)
    jwk.update({"kid": key_id, "alg": "RS256", "use": "sig", "key_ops": ["verify"]})
    return private_key, jwk


def _token(
    private_key: rsa.RSAPrivateKey | str,
    *,
    key_id: str = "key-1",
    algorithm: str = "RS256",
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    now: int | None = None,
    overrides: dict[str, object] | None = None,
    token_type: str = "at+jwt",
) -> str:
    issued_at = now or int(time.time())
    claims: dict[str, object] = {
        "iss": issuer,
        "sub": "external-subject-a",
        "aud": audience,
        "exp": issued_at + 300,
        "iat": issued_at,
        "client_id": "codex-host",
        "scope": "mcp:access project:read",
        "scp": ["research:run"],
        "organization_id": ORGANIZATION_ID,
        "jti": "token-id-that-must-not-leak",
    }
    claims.update(overrides or {})
    return jwt.encode(
        claims,
        private_key,
        algorithm=algorithm,
        headers={"kid": key_id, "typ": token_type},
    )


async def _verifier(
    fixture: OidcFixture,
) -> tuple[OidcJwtTokenVerifier, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(fixture.handler))
    verifier = OidcJwtTokenVerifier(
        OidcVerifierSettings(issuer=ISSUER, audience=AUDIENCE),
        http_client=client,
    )
    return verifier, client


@pytest.mark.anyio
async def test_valid_token_is_verified_with_minimal_claim_disclosure() -> None:
    private_key, jwk = _new_key("key-1")
    fixture = OidcFixture(keys=[jwk])
    verifier, client = await _verifier(fixture)
    try:
        result = await verifier.verify_token(_token(private_key))
    finally:
        await client.aclose()

    assert result is not None
    assert result.subject == "external-subject-a"
    assert result.client_id == "codex-host"
    assert result.resource == AUDIENCE
    assert result.scopes == ["mcp:access", "project:read", "research:run"]
    assert result.claims == {
        "iss": ISSUER,
        "organization_id": ORGANIZATION_ID,
        "jti_sha256": "2f49c5221ffc07f7167228e2ed96b1bb1fab87344e914a79be61f0b1530eec05",
    }
    assert "token-id-that-must-not-leak" not in str(result.claims)


@pytest.mark.anyio
async def test_optional_identity_claims_can_be_blank() -> None:
    private_key, jwk = _new_key("key-1")
    fixture = OidcFixture(keys=[jwk])
    verifier, client = await _verifier(fixture)
    try:
        result = await verifier.verify_token(
            _token(private_key, overrides={"organization_id": "", "jti": ""})
        )
    finally:
        await client.aclose()

    assert result is not None
    assert result.claims == {"iss": ISSUER}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changes",
    [
        {"issuer": "https://other-idp.example.gov"},
        {"audience": "https://other-resource.example.gov/mcp"},
        {"overrides": {"exp": int(time.time()) - 120}},
        {"overrides": {"nbf": int(time.time()) + 120}},
        {"overrides": {"client_id": None}},
        {"token_type": "JWT"},
    ],
)
async def test_invalid_security_claims_fail_closed(changes: dict[str, object]) -> None:
    private_key, jwk = _new_key("key-1")
    fixture = OidcFixture(keys=[jwk])
    verifier, client = await _verifier(fixture)
    try:
        result = await verifier.verify_token(_token(private_key, **changes))  # type: ignore[arg-type]
    finally:
        await client.aclose()
    assert result is None


@pytest.mark.anyio
@pytest.mark.parametrize("algorithm", ["HS256", "none"])
async def test_unsigned_or_symmetric_algorithm_is_rejected_without_key_fetch(
    algorithm: str,
) -> None:
    fixture = OidcFixture()
    verifier, client = await _verifier(fixture)
    key = "symmetric-secret-at-least-32-bytes" if algorithm == "HS256" else ""
    try:
        result = await verifier.verify_token(_token(key, algorithm=algorithm))
    finally:
        await client.aclose()
    assert result is None
    assert fixture.discovery_calls == 0
    assert fixture.jwks_calls == 0


@pytest.mark.anyio
async def test_unknown_rotated_key_forces_one_jwks_refresh() -> None:
    old_private, old_jwk = _new_key("old-key")
    new_private, new_jwk = _new_key("new-key")
    fixture = OidcFixture(keys=[old_jwk])
    verifier, client = await _verifier(fixture)
    try:
        assert await verifier.verify_token(_token(old_private, key_id="old-key")) is not None
        fixture.keys = [new_jwk]
        assert await verifier.verify_token(_token(new_private, key_id="new-key")) is not None
    finally:
        await client.aclose()
    assert fixture.discovery_calls == 1
    assert fixture.jwks_calls == 2


@pytest.mark.anyio
async def test_unknown_key_and_authorization_server_outage_fails_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    old_private, old_jwk = _new_key("old-key")
    unknown_private, _ = _new_key("unknown-key")
    fixture = OidcFixture(keys=[old_jwk])
    verifier, client = await _verifier(fixture)
    raw_token = _token(unknown_private, key_id="unknown-key")
    try:
        assert await verifier.verify_token(_token(old_private, key_id="old-key")) is not None
        fixture.unavailable = True
        with caplog.at_level("INFO"):
            assert await verifier.verify_token(raw_token) is None
    finally:
        await client.aclose()
    assert raw_token not in caplog.text
    assert "external-subject-a" not in caplog.text


def test_verifier_configuration_rejects_unsafe_network_and_algorithm_options() -> None:
    with pytest.raises(ValueError, match="safe absolute URL"):
        OidcVerifierSettings(issuer="http://idp.example.gov", audience=AUDIENCE)
    with pytest.raises(ValueError, match="asymmetric"):
        OidcVerifierSettings(
            issuer=ISSUER,
            audience=AUDIENCE,
            allowed_algorithms=frozenset({"HS256"}),
        )


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"accepted_token_types": frozenset()}, "token type"),
        ({"organization_claim": " "}, "claim name"),
        ({"clock_skew_seconds": 301}, "clock skew"),
        ({"cache_ttl_seconds": 0}, "cache TTL"),
        ({"request_timeout_seconds": 0}, "request timeout"),
        ({"max_document_bytes": 0}, "document size"),
        ({"max_token_bytes": 0}, "token size"),
        ({"allowed_jwks_origins": frozenset({"https://keys.example.gov/path"})}, "path"),
    ],
)
def test_verifier_configuration_bounds_are_enforced(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        OidcVerifierSettings(issuer=ISSUER, audience=AUDIENCE, **overrides)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_allowlisted_cross_origin_jwks_is_supported_but_default_is_denied() -> None:
    private_key, jwk = _new_key("key-1")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = (
            {"issuer": ISSUER, "jwks_uri": "https://keys.example.gov/jwks"}
            if request.url.path.endswith("openid-configuration")
            else {"keys": [jwk]}
        )
        return _json_response(request, payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        denied = OidcJwtTokenVerifier(
            OidcVerifierSettings(issuer=ISSUER, audience=AUDIENCE),
            http_client=client,
        )
        allowed = OidcJwtTokenVerifier(
            OidcVerifierSettings(
                issuer=ISSUER,
                audience=AUDIENCE,
                allowed_jwks_origins=frozenset({"https://keys.example.gov"}),
            ),
            http_client=client,
        )
        raw_token = _token(private_key)
        assert await denied.verify_token(raw_token) is None
        assert await allowed.verify_token(raw_token) is not None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mode",
    ["issuer", "content-type", "oversized", "unusable-key", "keys-shape", "root-shape"],
)
async def test_malformed_or_untrusted_oidc_documents_fail_closed(mode: str) -> None:
    private_key, jwk = _new_key("key-1")
    if mode == "unusable-key":
        jwk["use"] = "enc"

    def handler(request: httpx.Request) -> httpx.Response:
        if mode == "root-shape":
            return _json_response(request, [])
        if request.url.path.endswith("openid-configuration"):
            payload: object = {
                "issuer": "https://wrong.example.gov" if mode == "issuer" else ISSUER,
                "jwks_uri": f"{ISSUER}/jwks",
            }
        else:
            payload = {"keys": {} if mode == "keys-shape" else [jwk]}
        if mode == "oversized":
            return httpx.Response(
                200,
                request=request,
                content=b"{" + (b" " * 128) + b"}",
                headers={"content-type": "application/json"},
            )
        response = _json_response(request, payload)
        if mode == "content-type":
            response.headers["content-type"] = "text/html"
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = OidcJwtTokenVerifier(
            OidcVerifierSettings(
                issuer=ISSUER,
                audience=AUDIENCE,
                max_document_bytes=64 if mode == "oversized" else 1_000_000,
            ),
            http_client=client,
        )
        assert await verifier.verify_token(_token(private_key)) is None


@pytest.mark.anyio
async def test_oversized_token_and_invalid_scope_shape_fail_without_disclosure() -> None:
    private_key, jwk = _new_key("key-1")
    fixture = OidcFixture(keys=[jwk])
    client = httpx.AsyncClient(transport=httpx.MockTransport(fixture.handler))
    verifier = OidcJwtTokenVerifier(
        OidcVerifierSettings(issuer=ISSUER, audience=AUDIENCE, max_token_bytes=32),
        http_client=client,
    )
    try:
        assert await verifier.verify_token(_token(private_key)) is None
        scope_verifier = OidcJwtTokenVerifier(
            OidcVerifierSettings(issuer=ISSUER, audience=AUDIENCE),
            http_client=client,
        )
        assert (
            await scope_verifier.verify_token(
                _token(private_key, overrides={"scp": ["invalid scope"]})
            )
            is None
        )
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_owned_http_client_is_closed() -> None:
    verifier = OidcJwtTokenVerifier(OidcVerifierSettings(issuer=ISSUER, audience=AUDIENCE))
    verifier._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    )

    await verifier.aclose()

    assert verifier._client is None


def test_jwk_scope_and_required_claim_helpers_fail_closed() -> None:
    assert _select_jwk({"keys": "not-an-array"}, "key-1", "RS256") is None
    assert (
        _select_jwk(
            {"keys": [{"kid": "key-1", "alg": "RS256", "key_ops": ["sign"]}]},
            "key-1",
            "RS256",
        )
        is None
    )
    assert (
        _select_jwk(
            {"keys": [{"kid": "key-1", "alg": "ES256"}]},
            "key-1",
            "RS256",
        )
        is None
    )
    assert _extract_scopes({"scope": None, "scp": "project:read research:run"}) == {
        "project:read",
        "research:run",
    }
    assert _extract_scopes({"scp": 123}) == frozenset()
    with pytest.raises(ValueError, match="non-empty"):
        _required_string({}, "sub")
    with pytest.raises(ValueError, match="integer"):
        _required_int({"exp": True}, "exp")
    with pytest.raises(ValueError, match="requires a host"):
        _origin(urlparse("https:///missing-host"))
