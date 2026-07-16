from __future__ import annotations

from pathlib import Path

import pytest

from psr_mcp.auth.providers import McpAccessTokenAuthContextProvider
from psr_mcp.bootstrap import Container, PublicContainer, build_container
from psr_mcp.common.secrets import EnvironmentSecretResolver
from psr_mcp.config import SearchProviderMode, ServiceMode, Settings
from psr_mcp.storage.postgres import PostgresStore


def test_development_defaults_are_loopback_and_redacted() -> None:
    settings = Settings.from_env({})
    diagnostics = settings.diagnostics()

    assert settings.host == "127.0.0.1"
    assert settings.resource_server_url == "http://127.0.0.1:8000/mcp"
    assert diagnostics["cursor_signing_key"] == "***"
    assert diagnostics["database_url_ref"] is False
    assert diagnostics["search_api_key_ref"] is False


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
    assert isinstance(container, Container)
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


@pytest.mark.parametrize(
    "name, value, message",
    [
        ("PSR_MAX_REQUEST_BYTES", "100", "MAX_REQUEST_BYTES"),
        ("PSR_REQUEST_TIMEOUT_SECONDS", "0", "REQUEST_TIMEOUT"),
        ("PSR_RATE_LIMIT_REQUESTS", "0", "RATE_LIMIT_REQUESTS"),
        ("PSR_RATE_LIMIT_WINDOW_SECONDS", "0", "RATE_LIMIT_WINDOW"),
    ],
)
def test_remote_http_policy_configuration_is_bounded(name: str, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_env({name: value})


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"PSR_RESOURCE_SERVER_URL": "not-a-url"}, "RESOURCE_SERVER_URL"),
        ({"PSR_REQUIRED_MCP_SCOPES": ""}, "MCP_SCOPES"),
        ({"PSR_OAUTH_ORGANIZATION_CLAIM": "bad claim"}, "ORGANIZATION_CLAIM"),
        (
            {"PSR_AUTH_MODE": "oauth", "PSR_ISSUER_URL": "http://idp.example.gov"},
            "only on loopback",
        ),
        ({"PSR_OAUTH_JWKS_ORIGINS": "https://keys.example.gov/path"}, "origins only"),
        ({"PSR_AUTH_MODE": "oauth"}, "OAuth requires"),
        ({"PSR_STORAGE_MODE": "postgres"}, "PostgreSQL storage requires"),
        (
            {
                "PSR_ENV": "production",
                "PSR_PUBLIC_URL": "https://research.example.gov",
                "PSR_AUTH_MODE": "oauth",
                "PSR_STORAGE_MODE": "postgres",
                "PSR_ISSUER_URL": "http://127.0.0.1",
                "PSR_DATABASE_URL_REF": "env://PSR_DATABASE_URL",
                "PSR_CURSOR_SIGNING_KEY": "production-test-cursor-signing-key-0001",
            },
            "ISSUER_URL must use HTTPS",
        ),
        (
            {
                "PSR_ENV": "production",
                "PSR_PUBLIC_URL": "https://research.example.gov",
                "PSR_AUTH_MODE": "oauth",
                "PSR_STORAGE_MODE": "postgres",
                "PSR_ISSUER_URL": "https://idp.example.gov",
                "PSR_OAUTH_JWKS_ORIGINS": "http://127.0.0.1",
                "PSR_DATABASE_URL_REF": "env://PSR_DATABASE_URL",
                "PSR_CURSOR_SIGNING_KEY": "production-test-cursor-signing-key-0001",
            },
            "JWKS_ORIGINS must use HTTPS",
        ),
    ],
)
def test_configuration_guards_cover_each_security_boundary(
    overrides: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_env(overrides)


def test_public_ephemeral_development_requires_absolute_root(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path),
            "PSR_PUBLIC_KILL_SWITCH": "true",
            "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
        }
    )
    assert settings.service_mode is ServiceMode.PUBLIC_EPHEMERAL
    assert settings.public_kill_switch is True
    assert settings.public_fixture_research_enabled is True
    assert settings.public_max_active_quick == 8
    assert settings.public_daily_quick_budget == 0
    assert settings.diagnostics()["abuse_hmac_key_ref"] is False

    container = build_container(settings)
    assert isinstance(container, PublicContainer)


def test_trusted_proxy_cidrs_are_validated_and_canonicalized(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path),
            "PSR_TRUSTED_PROXY_CIDRS": "10.0.0.7/8, 2001:db8::1/64",
        }
    )
    assert settings.trusted_proxy_cidrs == ("10.0.0.0/8", "2001:db8::/64")

    with pytest.raises(ValueError, match="TRUSTED_PROXY_CIDRS"):
        Settings.from_env(
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": str(tmp_path),
                "PSR_TRUSTED_PROXY_CIDRS": "not-a-network",
            }
        )


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"PSR_SERVICE_MODE": "public_ephemeral"}, "EPHEMERAL_ROOT"),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "relative",
            },
            "absolute",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_AUTH_MODE": "oauth",
                "PSR_ISSUER_URL": "https://idp.example.gov",
            },
            "must not configure OAuth",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_STORAGE_MODE": "postgres",
                "PSR_DATABASE_URL_REF": "env://PSR_DATABASE_URL",
            },
            "must not configure persistent",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_RUN_TTL_SECONDS": "3601",
            },
            "RUN_TTL_SECONDS",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_PUBLIC_KILL_SWITCH": "sometimes",
            },
            "invalid PSR configuration",
        ),
        (
            {
                "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
            },
            "only in public ephemeral",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_QUICK_TIMEOUT_SECONDS": "31",
            },
            "QUICK_TIMEOUT_SECONDS",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_PUBLIC_MAX_ACTIVE_QUICK": "0",
            },
            "PUBLIC_MAX_ACTIVE_QUICK",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_PUBLIC_MAX_ACTIVE_QUICK": "101",
            },
            "PUBLIC_MAX_ACTIVE_QUICK",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_PUBLIC_DAILY_QUICK_BUDGET": "-1",
            },
            "PUBLIC_DAILY_QUICK_BUDGET",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_PUBLIC_DAILY_QUICK_BUDGET": "1000001",
            },
            "PUBLIC_DAILY_QUICK_BUDGET",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_MAX_RUN_SOURCES": "0",
            },
            "MAX_RUN_SOURCES",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_SEARCH_PROVIDER": "brave",
            },
            "SEARCH_API_KEY_REF",
        ),
        (
            {
                "PSR_SEARCH_API_KEY_REF": "env://BRAVE_API_KEY",
            },
            "requires PSR_SEARCH_PROVIDER",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_SEARCH_PROVIDER": "curated",
                "PSR_SEARCH_API_KEY_REF": "env://BRAVE_API_KEY",
            },
            "requires PSR_SEARCH_PROVIDER",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_SEARCH_PROVIDER": "brave",
                "PSR_SEARCH_API_KEY_REF": "secret://key",
            },
            "SEARCH_API_KEY_REF",
        ),
        (
            {
                "PSR_SEARCH_PROVIDER": "brave",
                "PSR_SEARCH_API_KEY_REF": "env://BRAVE_API_KEY",
            },
            "only in public ephemeral",
        ),
        (
            {
                "PSR_SEARCH_PROVIDER": "curated",
            },
            "only in public ephemeral",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_SEARCH_PROVIDER": "brave",
                "PSR_SEARCH_API_KEY_REF": "env://BRAVE_API_KEY",
                "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
            },
            "cannot be enabled together",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_SEARCH_PROVIDER": "curated",
                "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
            },
            "cannot be enabled together",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_SEARCH_MAX_CONCURRENCY": "0",
            },
            "SEARCH_MAX_CONCURRENCY",
        ),
        (
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": "/tmp/psr",
                "PSR_COLLECTION_MAX_CONCURRENCY": "21",
            },
            "COLLECTION_MAX_CONCURRENCY",
        ),
    ],
)
def test_public_ephemeral_configuration_fails_closed(
    overrides: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_env(overrides)


def test_public_production_requires_https_root_and_abuse_key() -> None:
    base = {
        "PSR_ENV": "production",
        "PSR_SERVICE_MODE": "public_ephemeral",
        "PSR_PUBLIC_URL": "https://research.example.gov",
        "PSR_RESOURCE_SERVER_URL": "https://research.example.gov/mcp",
        "PSR_EPHEMERAL_ROOT": "/var/lib/psr/ephemeral",
    }
    with pytest.raises(ValueError, match="ABUSE_HMAC_KEY_REF"):
        Settings.from_env(base)

    with pytest.raises(ValueError, match="TRUSTED_PROXY_CIDRS"):
        Settings.from_env(
            {
                **base,
                "PSR_ABUSE_HMAC_KEY_REF": "env://PSR_ABUSE_KEY",
            }
        )

    with pytest.raises(ValueError, match="PUBLIC_DAILY_QUICK_BUDGET"):
        Settings.from_env(
            {
                **base,
                "PSR_ABUSE_HMAC_KEY_REF": "env://PSR_ABUSE_KEY",
                "PSR_TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
            }
        )

    settings = Settings.from_env(
        {
            **base,
            "PSR_ABUSE_HMAC_KEY_REF": "env://PSR_ABUSE_KEY",
            "PSR_SEARCH_PROVIDER": "curated",
            "PSR_TRUSTED_PROXY_CIDRS": "127.0.0.1/32, 10.0.0.7/8",
            "PSR_PUBLIC_DAILY_QUICK_BUDGET": "500",
        }
    )
    assert settings.service_mode is ServiceMode.PUBLIC_EPHEMERAL
    assert settings.search_provider is SearchProviderMode.CURATED
    assert settings.public_daily_quick_budget == 500
    assert settings.trusted_proxy_cidrs == ("127.0.0.1/32", "10.0.0.0/8")
    container = build_container(
        settings,
        secret_resolver=EnvironmentSecretResolver(
            {"PSR_ABUSE_KEY": "production-public-abuse-key-0001"}
        ),
    )
    assert isinstance(container, PublicContainer)
    assert container.search_client is None
    assert container.quick_service.available is True

    with pytest.raises(ValueError, match="must not enable fixture"):
        Settings.from_env(
            {
                **base,
                "PSR_ABUSE_HMAC_KEY_REF": "env://PSR_ABUSE_KEY",
                "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
                "PSR_TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
            }
        )


@pytest.mark.anyio
async def test_brave_public_composition_is_explicit_and_closes_client(
    tmp_path: Path,
) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
            "PSR_SEARCH_PROVIDER": "brave",
            "PSR_SEARCH_API_KEY_REF": "env://BRAVE_API_KEY",
        }
    )
    container = build_container(
        settings,
        secret_resolver=EnvironmentSecretResolver({"BRAVE_API_KEY": "test-brave-api-key-123456"}),
    )

    assert isinstance(container, PublicContainer)
    assert settings.search_provider is SearchProviderMode.BRAVE
    assert settings.diagnostics()["search_api_key_ref"] is True
    assert container.search_client is not None
    assert container.quick_service.available is True

    await container.open()
    await container.close()
    assert container.search_client.is_closed


def test_curated_public_composition_requires_no_search_secret_or_client(
    tmp_path: Path,
) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "ephemeral"),
            "PSR_SEARCH_PROVIDER": "curated",
        }
    )

    container = build_container(settings)

    assert isinstance(container, PublicContainer)
    assert settings.search_provider is SearchProviderMode.CURATED
    assert settings.diagnostics()["search_api_key_ref"] is False
    assert container.search_client is None
    assert container.quick_service.available is True


@pytest.mark.parametrize(
    "mode",
    ["account_opt_in", "paid_persistent", "enterprise"],
)
def test_future_persistent_modes_fail_closed_until_composition_exists(mode: str) -> None:
    settings = Settings.from_env({"PSR_SERVICE_MODE": mode})

    with pytest.raises(RuntimeError, match="designed but not implemented"):
        build_container(settings)
