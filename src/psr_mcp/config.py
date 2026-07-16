"""Environment configuration with production fail-closed checks."""

from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal, cast
from urllib.parse import ParseResult, urlparse


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    STATIC = "static"
    OAUTH = "oauth"


class StorageMode(StrEnum):
    MEMORY = "memory"
    POSTGRES = "postgres"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_CURSOR_SIGNING_KEY = "development-only-cursor-signing-key"


@dataclass(frozen=True, slots=True)
class Settings:
    environment: Environment = Environment.DEVELOPMENT
    host: str = "127.0.0.1"
    port: int = 8000
    public_url: str = "http://127.0.0.1:8000"
    resource_server_url: str = "http://127.0.0.1:8000/mcp"
    auth_mode: AuthMode = AuthMode.STATIC
    storage_mode: StorageMode = StorageMode.MEMORY
    issuer_url: str | None = None
    required_mcp_scopes: tuple[str, ...] = ("mcp:access",)
    oauth_allowed_algorithms: tuple[str, ...] = ("RS256",)
    oauth_organization_claim: str = "organization_id"
    oauth_jwks_origins: tuple[str, ...] = ()
    max_request_bytes: int = 1_048_576
    request_timeout_seconds: float = 30.0
    rate_limit_requests: int = 120
    rate_limit_window_seconds: float = 60.0
    database_url_ref: str | None = None
    log_level: LogLevel = "INFO"
    cursor_signing_key: str = DEFAULT_CURSOR_SIGNING_KEY

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = environ if environ is not None else os.environ
        try:
            public_url = values.get("PSR_PUBLIC_URL", "http://127.0.0.1:8000")
            settings = cls(
                environment=Environment(values.get("PSR_ENV", "development")),
                host=values.get("PSR_HOST", "127.0.0.1"),
                port=int(values.get("PSR_PORT", "8000")),
                public_url=public_url,
                resource_server_url=values.get(
                    "PSR_RESOURCE_SERVER_URL", f"{public_url.rstrip('/')}/mcp"
                ),
                auth_mode=AuthMode(values.get("PSR_AUTH_MODE", "static")),
                storage_mode=StorageMode(values.get("PSR_STORAGE_MODE", "memory")),
                issuer_url=values.get("PSR_ISSUER_URL"),
                required_mcp_scopes=tuple(
                    values.get("PSR_REQUIRED_MCP_SCOPES", "mcp:access").split()
                ),
                oauth_allowed_algorithms=tuple(
                    value.strip().upper()
                    for value in values.get("PSR_OAUTH_ALLOWED_ALGORITHMS", "RS256").split(",")
                    if value.strip()
                ),
                oauth_organization_claim=values.get(
                    "PSR_OAUTH_ORGANIZATION_CLAIM", "organization_id"
                ),
                oauth_jwks_origins=tuple(
                    value.strip().rstrip("/")
                    for value in values.get("PSR_OAUTH_JWKS_ORIGINS", "").split(",")
                    if value.strip()
                ),
                max_request_bytes=int(values.get("PSR_MAX_REQUEST_BYTES", "1048576")),
                request_timeout_seconds=float(values.get("PSR_REQUEST_TIMEOUT_SECONDS", "30")),
                rate_limit_requests=int(values.get("PSR_RATE_LIMIT_REQUESTS", "120")),
                rate_limit_window_seconds=float(values.get("PSR_RATE_LIMIT_WINDOW_SECONDS", "60")),
                database_url_ref=values.get("PSR_DATABASE_URL_REF"),
                log_level=cast(LogLevel, values.get("PSR_LOG_LEVEL", "INFO").upper()),
                cursor_signing_key=values.get("PSR_CURSOR_SIGNING_KEY", DEFAULT_CURSOR_SIGNING_KEY),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("invalid PSR configuration value") from error
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.port < 1 or self.port > 65_535:
            raise ValueError("PSR_PORT must be 1..65535")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("PSR_LOG_LEVEL is invalid")
        if len(self.cursor_signing_key.encode()) < 32:
            raise ValueError("PSR_CURSOR_SIGNING_KEY must contain at least 32 bytes")
        if self.max_request_bytes < 1_024 or self.max_request_bytes > 10_485_760:
            raise ValueError("PSR_MAX_REQUEST_BYTES must be 1024..10485760")
        if self.request_timeout_seconds < 1 or self.request_timeout_seconds > 300:
            raise ValueError("PSR_REQUEST_TIMEOUT_SECONDS must be 1..300")
        if self.rate_limit_requests < 1 or self.rate_limit_requests > 10_000:
            raise ValueError("PSR_RATE_LIMIT_REQUESTS must be 1..10000")
        if self.rate_limit_window_seconds < 1 or self.rate_limit_window_seconds > 3_600:
            raise ValueError("PSR_RATE_LIMIT_WINDOW_SECONDS must be 1..3600")
        parsed_public_url = urlparse(self.public_url)
        if (
            parsed_public_url.scheme not in {"http", "https"}
            or not parsed_public_url.netloc
            or parsed_public_url.username is not None
            or parsed_public_url.password is not None
            or parsed_public_url.query
            or parsed_public_url.fragment
        ):
            raise ValueError("PSR_PUBLIC_URL must be an absolute HTTP(S) URL")
        parsed_resource_url = urlparse(self.resource_server_url)
        if (
            parsed_resource_url.scheme not in {"http", "https"}
            or not parsed_resource_url.netloc
            or parsed_resource_url.username is not None
            or parsed_resource_url.password is not None
            or parsed_resource_url.query
            or parsed_resource_url.fragment
        ):
            raise ValueError("PSR_RESOURCE_SERVER_URL must be a safe absolute HTTP(S) URL")
        if _origin(parsed_resource_url) != _origin(parsed_public_url):
            raise ValueError("PSR_RESOURCE_SERVER_URL must use the PSR_PUBLIC_URL origin")
        if not self.required_mcp_scopes or any(
            not scope.strip() or any(character.isspace() for character in scope)
            for scope in self.required_mcp_scopes
        ):
            raise ValueError("PSR_REQUIRED_MCP_SCOPES must contain non-blank scopes")
        if not self.oauth_allowed_algorithms or any(
            algorithm.lower() == "none" or algorithm.upper().startswith("HS")
            for algorithm in self.oauth_allowed_algorithms
        ):
            raise ValueError("PSR_OAUTH_ALLOWED_ALGORITHMS must contain asymmetric algorithms")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}", self.oauth_organization_claim):
            raise ValueError("PSR_OAUTH_ORGANIZATION_CLAIM is invalid")
        if self.database_url_ref and not re.fullmatch(
            r"env://[A-Za-z_][A-Za-z0-9_]*", self.database_url_ref
        ):
            raise ValueError("PSR_DATABASE_URL_REF must use env://VARIABLE")
        if self.auth_mode is AuthMode.OAUTH and self.issuer_url:
            parsed_issuer_url = urlparse(self.issuer_url)
            if (
                parsed_issuer_url.scheme not in {"http", "https"}
                or not parsed_issuer_url.netloc
                or parsed_issuer_url.username is not None
                or parsed_issuer_url.password is not None
                or parsed_issuer_url.query
                or parsed_issuer_url.fragment
            ):
                raise ValueError("PSR_ISSUER_URL must be a safe absolute HTTP(S) URL")
            if parsed_issuer_url.scheme == "http" and parsed_issuer_url.hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError("HTTP PSR_ISSUER_URL is allowed only on loopback")
            if parsed_issuer_url.path in {"", "/"}:
                object.__setattr__(
                    self,
                    "issuer_url",
                    f"{parsed_issuer_url.scheme}://{parsed_issuer_url.netloc}/",
                )
        for origin in self.oauth_jwks_origins:
            parsed_origin = urlparse(origin)
            if (
                parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.netloc
                or parsed_origin.path not in {"", "/"}
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                raise ValueError("PSR_OAUTH_JWKS_ORIGINS must contain origins only")
        if self.environment is Environment.DEVELOPMENT:
            if self.auth_mode is AuthMode.OAUTH and not self.issuer_url:
                raise ValueError("OAuth requires PSR_ISSUER_URL")
            if self.storage_mode is StorageMode.POSTGRES and not self.database_url_ref:
                raise ValueError("PostgreSQL storage requires PSR_DATABASE_URL_REF")
            try:
                if not ipaddress.ip_address(self.host).is_loopback:
                    raise ValueError("development server must bind to a loopback address")
            except ValueError as error:
                if "loopback" in str(error):
                    raise
                if self.host != "localhost":
                    raise ValueError(
                        "development server must bind to a loopback address"
                    ) from error
            return
        if parsed_public_url.scheme != "https":
            raise ValueError("production PSR_PUBLIC_URL must use HTTPS")
        if parsed_resource_url.scheme != "https":
            raise ValueError("production PSR_RESOURCE_SERVER_URL must use HTTPS")
        if self.auth_mode is not AuthMode.OAUTH:
            raise ValueError("production requires OAuth authentication")
        if self.storage_mode is not StorageMode.POSTGRES:
            raise ValueError("production requires PostgreSQL storage")
        if not self.issuer_url:
            raise ValueError("production requires PSR_ISSUER_URL")
        if urlparse(self.issuer_url or "").scheme != "https":
            raise ValueError("production PSR_ISSUER_URL must use HTTPS")
        if any(urlparse(origin).scheme != "https" for origin in self.oauth_jwks_origins):
            raise ValueError("production PSR_OAUTH_JWKS_ORIGINS must use HTTPS")
        if not self.database_url_ref:
            raise ValueError("production requires PSR_DATABASE_URL_REF")
        if self.cursor_signing_key == DEFAULT_CURSOR_SIGNING_KEY:
            raise ValueError("production requires a non-development PSR_CURSOR_SIGNING_KEY")

    def diagnostics(self) -> dict[str, object]:
        values = asdict(self)
        values["cursor_signing_key"] = "***"
        values["database_url_ref"] = bool(self.database_url_ref)
        return values


def _origin(parsed_url: ParseResult) -> tuple[str, str, int]:
    default_port = 443 if parsed_url.scheme == "https" else 80
    return parsed_url.scheme, parsed_url.hostname or "", parsed_url.port or default_port
