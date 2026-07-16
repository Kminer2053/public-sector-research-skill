from __future__ import annotations

import os
from pathlib import Path

import pytest

from psr_mcp.config import Settings
from psr_mcp.public.readiness import evaluate_public_readiness


def _restricted(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _production_settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "PSR_ENV": "production",
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_PUBLIC_URL": "https://research.example.gov",
            "PSR_RESOURCE_SERVER_URL": "https://research.example.gov/mcp",
            "PSR_EPHEMERAL_ROOT": str(_restricted(tmp_path / "ephemeral")),
            "PSR_ABUSE_HMAC_KEY_REF": "env://PSR_ABUSE_KEY",
            "PSR_SEARCH_PROVIDER": "curated",
            "PSR_TRUSTED_PROXY_CIDRS": "10.0.0.0/8",
            "PSR_PUBLIC_DAILY_QUICK_BUDGET": "500",
            "PSR_PUBLIC_PAUSE_FILE": str(tmp_path / "public.pause"),
        }
    )


def test_development_fixture_is_local_smoke_ready_but_not_public_ready(
    tmp_path: Path,
) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(_restricted(tmp_path / "ephemeral")),
            "PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED": "true",
        }
    )

    readiness = evaluate_public_readiness(settings, environ={})

    assert readiness.local_smoke_ready is True
    assert readiness.public_deployment_config_ready is False
    assert readiness.accepting_new_research is True
    source = next(check for check in readiness.checks if check.id == "source_discovery")
    assert source.status == "warn"


def test_production_public_readiness_requires_available_secrets(
    tmp_path: Path,
) -> None:
    settings = _production_settings(tmp_path)

    missing = evaluate_public_readiness(settings, environ={})
    short = evaluate_public_readiness(settings, environ={"PSR_ABUSE_KEY": "short"})
    ready = evaluate_public_readiness(
        settings,
        environ={"PSR_ABUSE_KEY": "production-public-abuse-key-0001"},
    )

    assert missing.public_deployment_config_ready is False
    assert short.public_deployment_config_ready is False
    assert ready.public_deployment_config_ready is True
    assert ready.accepting_new_research is True


def test_runtime_pause_changes_acceptance_without_invalidating_configuration(
    tmp_path: Path,
) -> None:
    settings = _production_settings(tmp_path)
    environ = {"PSR_ABUSE_KEY": "production-public-abuse-key-0001"}
    pause_file = Path(settings.public_pause_file or "")

    open_state = evaluate_public_readiness(settings, environ=environ)
    pause_file.touch()
    paused_state = evaluate_public_readiness(settings, environ=environ)

    assert open_state.public_deployment_config_ready is True
    assert open_state.accepting_new_research is True
    assert paused_state.public_deployment_config_ready is True
    assert paused_state.runtime_paused is True
    assert paused_state.accepting_new_research is False


def test_unsafe_ephemeral_root_fails_readiness(tmp_path: Path) -> None:
    root = tmp_path / "ephemeral"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(root),
            "PSR_SEARCH_PROVIDER": "curated",
        }
    )

    readiness = evaluate_public_readiness(settings, environ={})

    assert readiness.local_smoke_ready is False
    root_check = next(check for check in readiness.checks if check.id == "ephemeral_root")
    assert root_check.status == "fail"


def test_readiness_rejects_non_public_mode() -> None:
    with pytest.raises(ValueError, match="public_ephemeral"):
        evaluate_public_readiness(Settings.from_env({}), environ={})


def test_disabled_backend_and_missing_development_root_are_not_smoke_ready(
    tmp_path: Path,
) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(tmp_path / "missing"),
        }
    )

    readiness = evaluate_public_readiness(settings, environ={})

    assert readiness.local_smoke_ready is False
    checks = {check.id: check for check in readiness.checks}
    assert checks["source_discovery"].status == "fail"
    assert checks["ephemeral_root"].status == "warn"


def test_brave_readiness_requires_available_search_secret(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(_restricted(tmp_path / "ephemeral")),
            "PSR_SEARCH_PROVIDER": "brave",
            "PSR_SEARCH_API_KEY_REF": "env://BRAVE_API_KEY",
        }
    )

    missing = evaluate_public_readiness(settings, environ={})
    available = evaluate_public_readiness(
        settings,
        environ={"BRAVE_API_KEY": "test-brave-api-key-123456"},
    )
    blank = evaluate_public_readiness(
        settings,
        environ={"BRAVE_API_KEY": " " * 32},
    )

    missing_checks = {check.id: check for check in missing.checks}
    available_checks = {check.id: check for check in available.checks}
    blank_checks = {check.id: check for check in blank.checks}
    assert missing_checks["search_secret"].status == "fail"
    assert available_checks["search_secret"].status == "pass"
    assert blank_checks["search_secret"].status == "fail"
    assert available_checks["source_discovery"].detail.startswith("live Brave")


def test_ephemeral_metadata_error_fails_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _restricted(tmp_path / "ephemeral")
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(root),
            "PSR_SEARCH_PROVIDER": "curated",
        }
    )
    original = Path.lstat

    def denied(path: Path) -> os.stat_result:
        if path == root:
            raise PermissionError("ephemeral metadata denied")
        return original(path)

    monkeypatch.setattr(Path, "lstat", denied)

    readiness = evaluate_public_readiness(settings, environ={})

    root_check = next(check for check in readiness.checks if check.id == "ephemeral_root")
    assert root_check.status == "fail"


def test_non_directory_ephemeral_root_fails_readiness(tmp_path: Path) -> None:
    root = tmp_path / "ephemeral"
    root.write_text("not a directory", encoding="utf-8")
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(root),
            "PSR_SEARCH_PROVIDER": "curated",
        }
    )

    readiness = evaluate_public_readiness(settings, environ={})

    root_check = next(check for check in readiness.checks if check.id == "ephemeral_root")
    assert root_check.detail == "ephemeral root is not a safe directory"


@pytest.mark.parametrize("unsafe_parent", ["missing", "file", "writable"])
def test_unsafe_pause_parent_fails_readiness(
    tmp_path: Path,
    unsafe_parent: str,
) -> None:
    parent = tmp_path / "control"
    if unsafe_parent == "file":
        parent.write_text("not a directory", encoding="utf-8")
    elif unsafe_parent == "writable":
        parent.mkdir(mode=0o777)
        parent.chmod(0o777)
    settings = Settings.from_env(
        {
            "PSR_SERVICE_MODE": "public_ephemeral",
            "PSR_EPHEMERAL_ROOT": str(_restricted(tmp_path / "ephemeral")),
            "PSR_SEARCH_PROVIDER": "curated",
            "PSR_PUBLIC_PAUSE_FILE": str(parent / "public.pause"),
        }
    )

    readiness = evaluate_public_readiness(settings, environ={})

    pause_check = next(check for check in readiness.checks if check.id == "runtime_pause")
    assert pause_check.status == "fail"
    assert readiness.runtime_paused is True
