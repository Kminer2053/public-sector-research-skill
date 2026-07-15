from __future__ import annotations

import pytest

from psr_mcp.bootstrap import build_container
from psr_mcp.config import Settings


def test_development_defaults_are_loopback_and_redacted() -> None:
    settings = Settings.from_env({})
    diagnostics = settings.diagnostics()

    assert settings.host == "127.0.0.1"
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


def test_production_adapters_are_not_faked() -> None:
    settings = Settings.from_env(
        {
            "PSR_ENV": "production",
            "PSR_PUBLIC_URL": "https://research.example.gov",
            "PSR_AUTH_MODE": "oauth",
            "PSR_STORAGE_MODE": "postgres",
            "PSR_ISSUER_URL": "https://idp.example.gov",
            "PSR_DATABASE_URL_REF": "secret://database",
        }
    )
    with pytest.raises(RuntimeError, match="not implemented"):
        build_container(settings)


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
