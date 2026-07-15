"""Environment configuration with production fail-closed checks."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal, cast
from urllib.parse import urlparse


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


@dataclass(frozen=True, slots=True)
class Settings:
    environment: Environment = Environment.DEVELOPMENT
    host: str = "127.0.0.1"
    port: int = 8000
    public_url: str = "http://127.0.0.1:8000"
    auth_mode: AuthMode = AuthMode.STATIC
    storage_mode: StorageMode = StorageMode.MEMORY
    issuer_url: str | None = None
    database_url_ref: str | None = None
    log_level: LogLevel = "INFO"
    cursor_signing_key: str = "development-only-cursor-signing-key"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = environ if environ is not None else os.environ
        try:
            settings = cls(
                environment=Environment(values.get("PSR_ENV", "development")),
                host=values.get("PSR_HOST", "127.0.0.1"),
                port=int(values.get("PSR_PORT", "8000")),
                public_url=values.get("PSR_PUBLIC_URL", "http://127.0.0.1:8000"),
                auth_mode=AuthMode(values.get("PSR_AUTH_MODE", "static")),
                storage_mode=StorageMode(values.get("PSR_STORAGE_MODE", "memory")),
                issuer_url=values.get("PSR_ISSUER_URL"),
                database_url_ref=values.get("PSR_DATABASE_URL_REF"),
                log_level=cast(LogLevel, values.get("PSR_LOG_LEVEL", "INFO").upper()),
                cursor_signing_key=values.get(
                    "PSR_CURSOR_SIGNING_KEY", "development-only-cursor-signing-key"
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
        parsed_public_url = urlparse(self.public_url)
        if parsed_public_url.scheme not in {"http", "https"} or not parsed_public_url.netloc:
            raise ValueError("PSR_PUBLIC_URL must be an absolute HTTP(S) URL")
        if self.environment is Environment.DEVELOPMENT:
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
        if self.auth_mode is not AuthMode.OAUTH:
            raise ValueError("production requires OAuth authentication")
        if self.storage_mode is not StorageMode.POSTGRES:
            raise ValueError("production requires PostgreSQL storage")
        if not self.issuer_url:
            raise ValueError("production requires PSR_ISSUER_URL")
        if not self.database_url_ref:
            raise ValueError("production requires PSR_DATABASE_URL_REF")

    def diagnostics(self) -> dict[str, object]:
        values = asdict(self)
        values["cursor_signing_key"] = "***"
        values["database_url_ref"] = bool(self.database_url_ref)
        return values
