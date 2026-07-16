from __future__ import annotations

import pytest

from psr_mcp.auth.providers import McpAccessTokenAuthContextProvider
from psr_mcp.bootstrap import build_container
from psr_mcp.common.secrets import EnvironmentSecretResolver
from psr_mcp.config import Settings
from psr_mcp.storage.postgres import PostgresStore


def test_development_defaults_are_loopback_and_redacted() -> None:
    settings = Settings.from_env({})
    diagnostics = settings.diagnostics()

    assert settings.host == "127.0.0.1"
    assert settings.resource_server_url == "http://127.0.0.1:8000/mcp"
    assert diagnostics["cursor_signing_key"] == "***"
    assert diagnostics["database_url_ref"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"PSR_ENV": "production"},
        {
            "PSR_ENV": "production",
            "PSR_PUBLIC_URL": "http://research.example.gov",
            "PSR_AUTH_MODE": "oauth",
            "PSR_STORAGE_MODE": "postgres",
            "PSR_ISSUER_URL": "https://idp.example.gov",
            "PSR_DATABASE_URL_REF": "secret://database",
        },
        {"PSR_HOST": "0.0.0.0"},
    ],
)
def test_insecure_configuration_fails_closed(overrides: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        Settings.from_env(overrides)


def test_production_composition_uses_oauth_and_postgres_adapters() -> None:
    settings = Settings.from_env(
        {
            "PSR_ENV": "production",
            "PSR_PUBLIC_URL": "https://research.example.gov",
            "PSR_AUTH_MODE": "oauth",
            "PSR_STORAGE_MODE": "postgres",
            "PSR_ISSUER_URL": "https://idp.example.gov",
            "PSR_DATABASE_URL_REF": "env://PSR_DATABASE_URL",
            "PSR_CURSOR_SIGNING_KEY": "production-test-cursor-signing-key-0001",
        }
    )
    container = build_container(
        settings,
        secret_resolver=EnvironmentSecretResolver(
            {"PSR_DATABASE_URL": "postgresql://runtime:secret@db.example.gov/psr"}
        ),
    )
    assert isinstance(container.store, PostgresStore)
    assert isinstance(container.auth_provider, McpAccessTokenAuthContextProvider)
    assert container.token_verifier is not None


def test_environment_secret_resolver_does_not_allow_implicit_or_missing_values() -> None:
    resolver = EnvironmentSecretResolver({"PSR_DATABASE_URL": "postgresql://db/psr"})
    assert resolver.resolve("env://PSR_DATABASE_URL") == "postgresql://db/psr"
    with pytest.raises(ValueError, match="only env"):
        resolver.resolve("secret://database")
    with pytest.raises(ValueError, match="unavailable"):
        resolver.resolve("env://MISSING")


def test_production_rejects_development_cursor_key() -> None:
    with pytest.raises(ValueError, match="non-development"):
        Settings.from_env(
            {
                "PSR_ENV": "production",
                "PSR_PUBLIC_URL": "https://research.example.gov",
                "PSR_AUTH_MODE": "oauth",
                "PSR_STORAGE_MODE": "postgres",
                "PSR_ISSUER_URL": "https://idp.example.gov",
                "PSR_DATABASE_URL_REF": "env://PSR_DATABASE_URL",
            }
        )


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"PSR_PORT": "0"}, "1..65535"),
        ({"PSR_LOG_LEVEL": "TRACE"}, "LOG_LEVEL"),
        ({"PSR_CURSOR_SIGNING_KEY": "short"}, "32 bytes"),
        ({"PSR_PUBLIC_URL": "not-a-url"}, "absolute"),
        ({"PSR_HOST": "research.example.gov"}, "loopback"),
        (
            {"PSR_ENV": "production", "PSR_PUBLIC_URL": "https://research.example.gov"},
            "OAuth",
        ),
        (
            {
                "PSR_ENV": "production",
                "PSR_PUBLIC_URL": "https://research.example.gov",
                "PSR_AUTH_MODE": "oauth",
            },
            "PostgreSQL",
        ),
        (
            {
                "PSR_ENV": "production",
                "PSR_PUBLIC_URL": "https://research.example.gov",
                "PSR_AUTH_MODE": "oauth",
                "PSR_STORAGE_MODE": "postgres",
            },
            "ISSUER_URL",
        ),
        (
            {
                "PSR_ENV": "production",
                "PSR_PUBLIC_URL": "https://research.example.gov",
                "PSR_AUTH_MODE": "oauth",
                "PSR_STORAGE_MODE": "postgres",
                "PSR_ISSUER_URL": "https://idp.example.gov",
            },
            "DATABASE_URL_REF",
        ),
    ],
)
def test_specific_configuration_guards(overrides: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_env(overrides)


def test_localhost_name_is_allowed_in_development() -> None:
    assert Settings.from_env({"PSR_HOST": "localhost"}).host == "localhost"


def test_oauth_resource_server_configuration_is_explicit_and_redacted() -> None:
    settings = Settings.from_env(
        {
            "PSR_AUTH_MODE": "oauth",
            "PSR_ISSUER_URL": "https://idp.example.gov/tenant",
            "PSR_REQUIRED_MCP_SCOPES": "mcp:access project:read",
            "PSR_OAUTH_ALLOWED_ALGORITHMS": "RS256,ES256",
            "PSR_OAUTH_ORGANIZATION_CLAIM": "institution_id",
            "PSR_OAUTH_JWKS_ORIGINS": "https://keys.example.gov",
        }
    )

    assert settings.resource_server_url == "http://127.0.0.1:8000/mcp"
    assert settings.required_mcp_scopes == ("mcp:access", "project:read")
    assert settings.oauth_allowed_algorithms == ("RS256", "ES256")
    assert settings.oauth_organization_claim == "institution_id"
    assert settings.oauth_jwks_origins == ("https://keys.example.gov",)
    assert settings.diagnostics()["cursor_signing_key"] == "***"


@pytest.mark.parametrize(
    "overrides, message",
    [
        (
            {"PSR_RESOURCE_SERVER_URL": "https://other.example.gov/mcp"},
            "PUBLIC_URL origin",
        ),
        ({"PSR_OAUTH_ALLOWED_ALGORITHMS": "HS256"}, "asymmetric"),
        (
            {"PSR_AUTH_MODE": "oauth", "PSR_ISSUER_URL": "https://user@idp.example.gov"},
            "safe absolute",
        ),
        (
            {"PSR_AUTH_MODE": "oauth", "PSR_ISSUER_URL": "https://idp.example.gov?q=1"},
            "safe absolute",
        ),
    ],
)
def test_oauth_resource_server_configuration_rejects_unsafe_values(
    overrides: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_env(overrides)
