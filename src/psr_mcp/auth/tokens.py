"""OIDC discovery and RFC 9068-style JWT access-token verification."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import ParseResult, urlparse

import httpx
import jwt
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)

DEFAULT_ALGORITHMS = frozenset({"RS256"})
DEFAULT_TOKEN_TYPES = frozenset({"at+jwt", "application/at+jwt"})


@dataclass(frozen=True, slots=True)
class OidcVerifierSettings:
    issuer: str
    audience: str
    allowed_algorithms: frozenset[str] = DEFAULT_ALGORITHMS
    accepted_token_types: frozenset[str] = DEFAULT_TOKEN_TYPES
    organization_claim: str = "organization_id"
    clock_skew_seconds: int = 60
    cache_ttl_seconds: int = 300
    request_timeout_seconds: float = 5.0
    max_document_bytes: int = 1_000_000
    max_token_bytes: int = 16_384
    allowed_jwks_origins: frozenset[str] = frozenset()
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        issuer = self.issuer
        audience = self.audience
        _require_absolute_url(issuer, allow_http=self.allow_insecure_http, name="issuer")
        _require_absolute_url(audience, allow_http=self.allow_insecure_http, name="audience")
        if not self.allowed_algorithms or any(
            algorithm.lower() == "none" or algorithm.upper().startswith("HS")
            for algorithm in self.allowed_algorithms
        ):
            raise ValueError("allowed algorithms must be asymmetric and must not include none")
        if not self.accepted_token_types:
            raise ValueError("at least one JWT access-token type is required")
        if not self.organization_claim.strip():
            raise ValueError("organization claim name is required")
        if self.clock_skew_seconds < 0 or self.clock_skew_seconds > 300:
            raise ValueError("clock skew must be between 0 and 300 seconds")
        if self.cache_ttl_seconds < 1:
            raise ValueError("cache TTL must be positive")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request timeout must be positive")
        if self.max_document_bytes < 1:
            raise ValueError("maximum document size must be positive")
        if self.max_token_bytes < 1:
            raise ValueError("maximum token size must be positive")
        normalized_origins: set[str] = set()
        for origin in self.allowed_jwks_origins:
            parsed_origin = _require_absolute_url(
                origin,
                allow_http=self.allow_insecure_http,
                name="allowed JWKS origin",
            )
            if parsed_origin.path not in {"", "/"}:
                raise ValueError("allowed JWKS origins must not include a path")
            normalized_origins.add(_origin(parsed_origin))
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "audience", audience)
        object.__setattr__(self, "allowed_jwks_origins", frozenset(normalized_origins))


@dataclass(slots=True)
class _CacheEntry:
    value: Mapping[str, Any]
    expires_at: float


class OidcJwtTokenVerifier:
    """MCP SDK TokenVerifier with bounded discovery/JWKS caching and rotation refresh."""

    def __init__(
        self,
        settings: OidcVerifierSettings,
        *,
        http_client: httpx.AsyncClient | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._client = http_client
        self._owns_client = http_client is None
        self._monotonic = monotonic
        self._discovery: _CacheEntry | None = None
        self._jwks: _CacheEntry | None = None
        self._refresh_lock = asyncio.Lock()

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return only verified, minimally disclosed token data; fail closed on any error."""
        try:
            if len(token.encode()) > self._settings.max_token_bytes:
                raise ValueError("access token exceeds configured size limit")
            header = jwt.get_unverified_header(token)
            algorithm = _required_string(header, "alg")
            key_id = _required_string(header, "kid")
            token_type = _required_string(header, "typ").lower()
            if algorithm not in self._settings.allowed_algorithms:
                raise ValueError("algorithm is not allowed")
            if token_type not in {value.lower() for value in self._settings.accepted_token_types}:
                raise ValueError("JWT type is not an access-token type")

            jwk = await self._find_jwk(key_id, algorithm)
            if jwk is None:
                raise ValueError("signing key is unavailable")
            public_key = jwt.PyJWK.from_dict(dict(jwk), algorithm=algorithm).key
            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=[algorithm],
                audience=self._settings.audience,
                issuer=self._settings.issuer,
                leeway=self._settings.clock_skew_seconds,
                options={
                    "require": ["iss", "sub", "aud", "exp", "iat", "client_id"],
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                },
            )
            subject = _required_string(claims, "sub")
            client_id = _required_string(claims, "client_id")
            expires_at = _required_int(claims, "exp")
            issuer = _required_string(claims, "iss")
            scopes = _extract_scopes(claims)
            safe_claims: dict[str, Any] = {"iss": issuer}
            organization_id = claims.get(self._settings.organization_claim)
            if isinstance(organization_id, str) and organization_id.strip():
                safe_claims["organization_id"] = organization_id.strip()
            token_id = claims.get("jti")
            if isinstance(token_id, str) and token_id:
                safe_claims["jti_sha256"] = hashlib.sha256(token_id.encode()).hexdigest()
            return AccessToken(
                token=token,
                client_id=client_id,
                scopes=sorted(scopes),
                expires_at=expires_at,
                resource=self._settings.audience,
                subject=subject,
                claims=safe_claims,
            )
        except (httpx.HTTPError, jwt.PyJWTError, TypeError, ValueError):
            logger.info("access token verification denied")
            return None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _find_jwk(self, key_id: str, algorithm: str) -> Mapping[str, Any] | None:
        document = await self._get_jwks(force_refresh=False)
        match = _select_jwk(document, key_id, algorithm)
        if match is not None:
            return match
        document = await self._get_jwks(force_refresh=True)
        return _select_jwk(document, key_id, algorithm)

    async def _get_jwks(self, *, force_refresh: bool) -> Mapping[str, Any]:
        async with self._refresh_lock:
            now = self._monotonic()
            if not force_refresh and self._jwks is not None and self._jwks.expires_at > now:
                return self._jwks.value
            discovery = await self._get_discovery(now)
            jwks_uri = _required_string(discovery, "jwks_uri")
            self._validate_jwks_uri(jwks_uri)
            document = await self._get_json(jwks_uri)
            keys = document.get("keys")
            if not isinstance(keys, list):
                raise ValueError("JWKS keys must be an array")
            self._jwks = _CacheEntry(document, now + self._settings.cache_ttl_seconds)
            return document

    async def _get_discovery(self, now: float) -> Mapping[str, Any]:
        if self._discovery is not None and self._discovery.expires_at > now:
            return self._discovery.value
        url = f"{self._settings.issuer.rstrip('/')}/.well-known/openid-configuration"
        document = await self._get_json(url)
        if _required_string(document, "issuer") != self._settings.issuer:
            raise ValueError("discovered issuer does not exactly match configured issuer")
        self._discovery = _CacheEntry(document, now + self._settings.cache_ttl_seconds)
        return document

    async def _get_json(self, url: str) -> Mapping[str, Any]:
        client = self._client
        if client is None:
            client = httpx.AsyncClient(
                follow_redirects=False,
                timeout=self._settings.request_timeout_seconds,
                headers={"accept": "application/json"},
            )
            self._client = client
        content = bytearray()
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "json" not in content_type:
                raise ValueError("OIDC endpoint did not return JSON")
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > self._settings.max_document_bytes:
                    raise ValueError("OIDC document exceeds configured size limit")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("OIDC document must be a JSON object")
        return cast(Mapping[str, Any], value)

    def _validate_jwks_uri(self, value: str) -> None:
        parsed = _require_absolute_url(
            value,
            allow_http=self._settings.allow_insecure_http,
            name="jwks_uri",
        )
        issuer_origin = _origin(urlparse(self._settings.issuer))
        allowed = set(self._settings.allowed_jwks_origins) | {issuer_origin}
        if _origin(parsed) not in allowed:
            raise ValueError("jwks_uri origin is not allowlisted")


def _select_jwk(
    document: Mapping[str, Any], key_id: str, algorithm: str
) -> Mapping[str, Any] | None:
    keys = document.get("keys")
    if not isinstance(keys, list):
        return None
    for candidate in keys:
        if not isinstance(candidate, dict) or candidate.get("kid") != key_id:
            continue
        if candidate.get("use") not in {None, "sig"}:
            continue
        key_ops = candidate.get("key_ops")
        if isinstance(key_ops, list) and "verify" not in key_ops:
            continue
        if candidate.get("alg") not in {None, algorithm}:
            continue
        return cast(Mapping[str, Any], candidate)
    return None


def _extract_scopes(claims: Mapping[str, Any]) -> frozenset[str]:
    values: set[str] = set()
    scope = claims.get("scope")
    if isinstance(scope, str):
        values.update(scope.split())
    scp = claims.get("scp")
    if isinstance(scp, str):
        values.update(scp.split())
    elif isinstance(scp, Collection) and not isinstance(scp, (str, bytes, Mapping)):
        values.update(value for value in scp if isinstance(value, str))
    normalized = frozenset(value for value in values if value)
    if len(normalized) > 64 or any(
        len(value) > 128 or any(character.isspace() for character in value) for value in normalized
    ):
        raise ValueError("token scopes exceed configured limits")
    return normalized


def _required_string(values: Mapping[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _required_int(values: Mapping[str, Any], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _require_absolute_url(value: str, *, allow_http: bool, name: str) -> ParseResult:
    parsed = urlparse(value)
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} must be a safe absolute URL")
    return parsed


def _origin(parsed: Any) -> str:
    host = parsed.hostname
    if not host:
        raise ValueError("URL origin requires a host")
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port or default_port
    return f"{parsed.scheme}://{host.lower()}:{port}"
