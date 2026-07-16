"""Environment configuration with production fail-closed checks."""

from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
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


class SearchProviderMode(StrEnum):
    DISABLED = "disabled"
    CURATED = "curated"
    BRAVE = "brave"


class ServiceMode(StrEnum):
    FOUNDATION = "foundation"
    PUBLIC_EPHEMERAL = "public_ephemeral"
    ACCOUNT_OPT_IN = "account_opt_in"
    PAID_PERSISTENT = "paid_persistent"
    ENTERPRISE = "enterprise"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_CURSOR_SIGNING_KEY = "development-only-cursor-signing-key"


@dataclass(frozen=True, slots=True)
class Settings:
    environment: Environment = Environment.DEVELOPMENT
    service_mode: ServiceMode = ServiceMode.FOUNDATION
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
    ephemeral_root: str | None = None
    run_ttl_seconds: int = 3_600
    delivered_purge_seconds: int = 60
    failed_content_ttl_seconds: int = 600
    orphan_max_age_seconds: int = 7_200
    purge_sweep_seconds: int = 60
    public_kill_switch: bool = False
    public_pause_file: str | None = None
    public_fixture_research_enabled: bool = False
    quick_timeout_seconds: float = 20.0
    public_max_active_quick: int = 8
    public_daily_quick_budget: int = 0
    feedback_token_ttl_seconds: int = 86_400
    max_run_sources: int = 12
    max_run_bytes: int = 31_457_280
    search_provider: SearchProviderMode = SearchProviderMode.DISABLED
    search_api_key_ref: str | None = None
    search_timeout_seconds: float = 5.0
    search_max_response_bytes: int = 1_048_576
    search_max_concurrency: int = 7
    collection_max_concurrency: int = 4
    outbound_max_concurrency: int = 8
    source_host_max_concurrency: int = 2
    source_host_rate_requests: int = 2
    source_host_rate_window_seconds: float = 1.0
    abuse_hmac_key_ref: str | None = None
    trusted_proxy_cidrs: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = environ if environ is not None else os.environ
        try:
            public_url = values.get("PSR_PUBLIC_URL", "http://127.0.0.1:8000")
            settings = cls(
                environment=Environment(values.get("PSR_ENV", "development")),
                service_mode=ServiceMode(values.get("PSR_SERVICE_MODE", "foundation")),
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
                ephemeral_root=values.get("PSR_EPHEMERAL_ROOT"),
                run_ttl_seconds=int(values.get("PSR_RUN_TTL_SECONDS", "3600")),
                delivered_purge_seconds=int(values.get("PSR_DELIVERED_PURGE_SECONDS", "60")),
                failed_content_ttl_seconds=int(values.get("PSR_FAILED_CONTENT_TTL_SECONDS", "600")),
                orphan_max_age_seconds=int(values.get("PSR_ORPHAN_MAX_AGE_SECONDS", "7200")),
                purge_sweep_seconds=int(values.get("PSR_PURGE_SWEEP_SECONDS", "60")),
                public_kill_switch=_parse_bool(
                    values.get("PSR_PUBLIC_KILL_SWITCH", "false"),
                    name="PSR_PUBLIC_KILL_SWITCH",
                ),
                public_pause_file=values.get("PSR_PUBLIC_PAUSE_FILE"),
                public_fixture_research_enabled=_parse_bool(
                    values.get("PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED", "false"),
                    name="PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED",
                ),
                quick_timeout_seconds=float(values.get("PSR_QUICK_TIMEOUT_SECONDS", "20")),
                public_max_active_quick=int(values.get("PSR_PUBLIC_MAX_ACTIVE_QUICK", "8")),
                public_daily_quick_budget=int(values.get("PSR_PUBLIC_DAILY_QUICK_BUDGET", "0")),
                feedback_token_ttl_seconds=int(
                    values.get("PSR_FEEDBACK_TOKEN_TTL_SECONDS", "86400")
                ),
                max_run_sources=int(values.get("PSR_MAX_RUN_SOURCES", "12")),
                max_run_bytes=int(values.get("PSR_MAX_RUN_BYTES", "31457280")),
                search_provider=SearchProviderMode(values.get("PSR_SEARCH_PROVIDER", "disabled")),
                search_api_key_ref=values.get("PSR_SEARCH_API_KEY_REF"),
                search_timeout_seconds=float(values.get("PSR_SEARCH_TIMEOUT_SECONDS", "5")),
                search_max_response_bytes=int(
                    values.get("PSR_SEARCH_MAX_RESPONSE_BYTES", "1048576")
                ),
                search_max_concurrency=int(values.get("PSR_SEARCH_MAX_CONCURRENCY", "7")),
                collection_max_concurrency=int(values.get("PSR_COLLECTION_MAX_CONCURRENCY", "4")),
                outbound_max_concurrency=int(values.get("PSR_OUTBOUND_MAX_CONCURRENCY", "8")),
                source_host_max_concurrency=int(values.get("PSR_SOURCE_HOST_MAX_CONCURRENCY", "2")),
                source_host_rate_requests=int(values.get("PSR_SOURCE_HOST_RATE_REQUESTS", "2")),
                source_host_rate_window_seconds=float(
                    values.get("PSR_SOURCE_HOST_RATE_WINDOW_SECONDS", "1")
                ),
                abuse_hmac_key_ref=values.get("PSR_ABUSE_HMAC_KEY_REF"),
                trusted_proxy_cidrs=tuple(
                    value.strip()
                    for value in values.get("PSR_TRUSTED_PROXY_CIDRS", "").split(",")
                    if value.strip()
                ),
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
        if self.run_ttl_seconds < 60 or self.run_ttl_seconds > 3_600:
            raise ValueError("PSR_RUN_TTL_SECONDS must be 60..3600")
        if self.delivered_purge_seconds < 1 or self.delivered_purge_seconds > 60:
            raise ValueError("PSR_DELIVERED_PURGE_SECONDS must be 1..60")
        if self.failed_content_ttl_seconds < 1 or self.failed_content_ttl_seconds > 600:
            raise ValueError("PSR_FAILED_CONTENT_TTL_SECONDS must be 1..600")
        if self.orphan_max_age_seconds < self.run_ttl_seconds:
            raise ValueError("PSR_ORPHAN_MAX_AGE_SECONDS must be at least PSR_RUN_TTL_SECONDS")
        if self.orphan_max_age_seconds > 7_200:
            raise ValueError("PSR_ORPHAN_MAX_AGE_SECONDS must be at most 7200")
        if self.purge_sweep_seconds < 1 or self.purge_sweep_seconds > 60:
            raise ValueError("PSR_PURGE_SWEEP_SECONDS must be 1..60")
        if self.quick_timeout_seconds < 1 or self.quick_timeout_seconds > 30:
            raise ValueError("PSR_QUICK_TIMEOUT_SECONDS must be 1..30")
        if self.quick_timeout_seconds > self.request_timeout_seconds:
            raise ValueError("PSR_QUICK_TIMEOUT_SECONDS must not exceed request timeout")
        if self.public_max_active_quick < 1 or self.public_max_active_quick > 100:
            raise ValueError("PSR_PUBLIC_MAX_ACTIVE_QUICK must be 1..100")
        if self.public_daily_quick_budget < 0 or self.public_daily_quick_budget > 1_000_000:
            raise ValueError("PSR_PUBLIC_DAILY_QUICK_BUDGET must be 0..1000000")
        if self.feedback_token_ttl_seconds < 300 or self.feedback_token_ttl_seconds > 604_800:
            raise ValueError("PSR_FEEDBACK_TOKEN_TTL_SECONDS must be 300..604800")
        if self.max_run_sources < 1 or self.max_run_sources > 100:
            raise ValueError("PSR_MAX_RUN_SOURCES must be 1..100")
        if self.max_run_bytes < 1_048_576 or self.max_run_bytes > 104_857_600:
            raise ValueError("PSR_MAX_RUN_BYTES must be 1048576..104857600")
        if self.search_timeout_seconds <= 0 or self.search_timeout_seconds > 30:
            raise ValueError("PSR_SEARCH_TIMEOUT_SECONDS must be >0 and <=30")
        if self.search_max_response_bytes < 1_024 or self.search_max_response_bytes > 10_485_760:
            raise ValueError("PSR_SEARCH_MAX_RESPONSE_BYTES must be 1024..10485760")
        if self.search_max_concurrency < 1 or self.search_max_concurrency > 10:
            raise ValueError("PSR_SEARCH_MAX_CONCURRENCY must be 1..10")
        if self.collection_max_concurrency < 1 or self.collection_max_concurrency > 20:
            raise ValueError("PSR_COLLECTION_MAX_CONCURRENCY must be 1..20")
        if self.outbound_max_concurrency < 1 or self.outbound_max_concurrency > 32:
            raise ValueError("PSR_OUTBOUND_MAX_CONCURRENCY must be 1..32")
        if self.source_host_max_concurrency < 1 or self.source_host_max_concurrency > 8:
            raise ValueError("PSR_SOURCE_HOST_MAX_CONCURRENCY must be 1..8")
        if self.source_host_max_concurrency > self.outbound_max_concurrency:
            raise ValueError(
                "PSR_SOURCE_HOST_MAX_CONCURRENCY must not exceed PSR_OUTBOUND_MAX_CONCURRENCY"
            )
        if self.source_host_rate_requests < 1 or self.source_host_rate_requests > 60:
            raise ValueError("PSR_SOURCE_HOST_RATE_REQUESTS must be 1..60")
        if self.source_host_rate_window_seconds < 0.1 or self.source_host_rate_window_seconds > 60:
            raise ValueError("PSR_SOURCE_HOST_RATE_WINDOW_SECONDS must be 0.1..60")
        canonical_proxy_cidrs: list[str] = []
        for value in self.trusted_proxy_cidrs:
            try:
                canonical_proxy_cidrs.append(str(ipaddress.ip_network(value, strict=False)))
            except ValueError:
                raise ValueError("PSR_TRUSTED_PROXY_CIDRS must contain valid IP networks") from None
        object.__setattr__(self, "trusted_proxy_cidrs", tuple(canonical_proxy_cidrs))
        if self.ephemeral_root is not None and not Path(self.ephemeral_root).is_absolute():
            raise ValueError("PSR_EPHEMERAL_ROOT must be an absolute path")
        if self.public_pause_file is not None and not Path(self.public_pause_file).is_absolute():
            raise ValueError("PSR_PUBLIC_PAUSE_FILE must be an absolute path")
        if self.abuse_hmac_key_ref and not re.fullmatch(
            r"env://[A-Za-z_][A-Za-z0-9_]*", self.abuse_hmac_key_ref
        ):
            raise ValueError("PSR_ABUSE_HMAC_KEY_REF must use env://VARIABLE")
        if self.search_api_key_ref and not re.fullmatch(
            r"env://[A-Za-z_][A-Za-z0-9_]*", self.search_api_key_ref
        ):
            raise ValueError("PSR_SEARCH_API_KEY_REF must use env://VARIABLE")
        if self.search_provider is SearchProviderMode.BRAVE:
            if self.service_mode is not ServiceMode.PUBLIC_EPHEMERAL:
                raise ValueError("Brave search is available only in public ephemeral mode")
            if not self.search_api_key_ref:
                raise ValueError("Brave search requires PSR_SEARCH_API_KEY_REF")
            if self.public_fixture_research_enabled:
                raise ValueError("fixture research and Brave search cannot be enabled together")
        elif self.search_provider is SearchProviderMode.CURATED:
            if self.service_mode is not ServiceMode.PUBLIC_EPHEMERAL:
                raise ValueError(
                    "curated source discovery is available only in public ephemeral mode"
                )
            if self.search_api_key_ref:
                raise ValueError("PSR_SEARCH_API_KEY_REF requires PSR_SEARCH_PROVIDER=brave")
            if self.public_fixture_research_enabled:
                raise ValueError(
                    "fixture research and curated source discovery cannot be enabled together"
                )
        elif self.search_api_key_ref:
            raise ValueError("PSR_SEARCH_API_KEY_REF requires PSR_SEARCH_PROVIDER=brave")
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
        if self.service_mode is ServiceMode.PUBLIC_EPHEMERAL:
            if self.auth_mode is not AuthMode.STATIC:
                raise ValueError("public ephemeral mode must not configure OAuth authentication")
            if self.storage_mode is not StorageMode.MEMORY:
                raise ValueError("public ephemeral mode must not configure persistent storage")
            if not self.ephemeral_root:
                raise ValueError("public ephemeral mode requires PSR_EPHEMERAL_ROOT")
        elif self.public_fixture_research_enabled:
            raise ValueError("fixture research is available only in public ephemeral mode")
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
        if self.service_mode is ServiceMode.PUBLIC_EPHEMERAL:
            if self.public_fixture_research_enabled:
                raise ValueError("production public mode must not enable fixture research")
            if not self.abuse_hmac_key_ref:
                raise ValueError("public production requires PSR_ABUSE_HMAC_KEY_REF")
            if not self.trusted_proxy_cidrs:
                raise ValueError("public production requires PSR_TRUSTED_PROXY_CIDRS")
            if self.public_daily_quick_budget < 1:
                raise ValueError("public production requires PSR_PUBLIC_DAILY_QUICK_BUDGET")
            return
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
        values["abuse_hmac_key_ref"] = bool(self.abuse_hmac_key_ref)
        values["search_api_key_ref"] = bool(self.search_api_key_ref)
        values["public_pause_file"] = bool(self.public_pause_file)
        return values


def _origin(parsed_url: ParseResult) -> tuple[str, str, int]:
    default_port = 443 if parsed_url.scheme == "https" else 80
    return parsed_url.scheme, parsed_url.hostname or "", parsed_url.port or default_port


def _parse_bool(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
