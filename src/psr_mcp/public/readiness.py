"""Read-only Public Preview configuration readiness evaluation."""

from __future__ import annotations

import stat
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from psr_mcp.config import Environment, SearchProviderMode, ServiceMode, Settings
from psr_mcp.public.admission import FilePauseSignal

CheckStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    id: str
    status: CheckStatus
    detail: str


@dataclass(frozen=True, slots=True)
class PublicReadiness:
    local_smoke_ready: bool
    public_deployment_config_ready: bool
    accepting_new_research: bool
    runtime_paused: bool
    checks: tuple[ReadinessCheck, ...]
    external_gates_pending: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_public_readiness(
    settings: Settings,
    *,
    environ: Mapping[str, str],
) -> PublicReadiness:
    if settings.service_mode is not ServiceMode.PUBLIC_EPHEMERAL:
        raise ValueError("public readiness requires public_ephemeral mode")

    source = _source_check(settings)
    ephemeral = _ephemeral_root_check(settings)
    abuse_secret = _abuse_secret_check(settings, environ)
    search_secret = _search_secret_check(settings, environ)
    trusted_proxy = ReadinessCheck(
        id="trusted_proxy",
        status="pass" if settings.trusted_proxy_cidrs else "warn",
        detail=(
            "trusted proxy networks configured"
            if settings.trusted_proxy_cidrs
            else "trusted proxy networks are not configured"
        ),
    )
    daily_budget = ReadinessCheck(
        id="daily_quick_budget",
        status="pass" if settings.public_daily_quick_budget > 0 else "warn",
        detail=(
            "UTC daily quick budget configured"
            if settings.public_daily_quick_budget > 0
            else "daily quick budget is disabled"
        ),
    )
    pause, runtime_paused = _pause_check(settings)
    checks = (
        source,
        ephemeral,
        abuse_secret,
        search_secret,
        trusted_proxy,
        daily_budget,
        pause,
    )
    local_smoke_ready = all(
        check.status != "fail" for check in (source, ephemeral, abuse_secret, search_secret)
    )
    deployment_required = (
        source,
        ephemeral,
        abuse_secret,
        search_secret,
        trusted_proxy,
        daily_budget,
        pause,
    )
    public_deployment_config_ready = settings.environment is Environment.PRODUCTION and all(
        check.status == "pass" for check in deployment_required
    )
    return PublicReadiness(
        local_smoke_ready=local_smoke_ready,
        public_deployment_config_ready=public_deployment_config_ready,
        accepting_new_research=(
            local_smoke_ready and not settings.public_kill_switch and not runtime_paused
        ),
        runtime_paused=settings.public_kill_switch or runtime_paused,
        checks=checks,
        external_gates_pending=(
            "actual NGINX OCI and staging quota rehearsal",
            "multi-replica shared quota and provider hard cap",
            "staging retention canary and purge game day",
            "real-user helpfulness and save-feature-interest validation",
        ),
    )


def _source_check(settings: Settings) -> ReadinessCheck:
    if settings.public_fixture_research_enabled:
        return ReadinessCheck(
            id="source_discovery",
            status="warn",
            detail="development fixture supports lifecycle smoke only",
        )
    if settings.search_provider is SearchProviderMode.DISABLED:
        return ReadinessCheck(
            id="source_discovery",
            status="fail",
            detail="public research backend is disabled",
        )
    if settings.search_provider is SearchProviderMode.CURATED:
        return ReadinessCheck(
            id="source_discovery",
            status="pass",
            detail="curated official-source discovery configured",
        )
    return ReadinessCheck(
        id="source_discovery",
        status="pass",
        detail="live Brave Search discovery configured",
    )


def _ephemeral_root_check(settings: Settings) -> ReadinessCheck:
    root = Path(settings.ephemeral_root or "")
    try:
        metadata = root.lstat()
    except FileNotFoundError:
        return ReadinessCheck(
            id="ephemeral_root",
            status=("warn" if settings.environment is Environment.DEVELOPMENT else "fail"),
            detail="ephemeral root does not exist yet",
        )
    except OSError:
        return ReadinessCheck(
            id="ephemeral_root",
            status="fail",
            detail="ephemeral root metadata is unavailable",
        )
    mode = metadata.st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        return ReadinessCheck(
            id="ephemeral_root",
            status="fail",
            detail="ephemeral root is not a safe directory",
        )
    if stat.S_IMODE(mode) & 0o077:
        return ReadinessCheck(
            id="ephemeral_root",
            status="fail",
            detail="ephemeral root permissions are broader than 0700",
        )
    return ReadinessCheck(
        id="ephemeral_root",
        status="pass",
        detail="ephemeral root exists with restricted permissions",
    )


def _abuse_secret_check(
    settings: Settings,
    environ: Mapping[str, str],
) -> ReadinessCheck:
    if settings.abuse_hmac_key_ref:
        available = _secret_available(settings.abuse_hmac_key_ref, environ, minimum_length=32)
        return ReadinessCheck(
            id="abuse_hmac_secret",
            status="pass" if available else "fail",
            detail=(
                "abuse HMAC secret is available"
                if available
                else "abuse HMAC secret is unavailable or too short"
            ),
        )
    return ReadinessCheck(
        id="abuse_hmac_secret",
        status="warn",
        detail="development cursor key fallback is in use",
    )


def _search_secret_check(
    settings: Settings,
    environ: Mapping[str, str],
) -> ReadinessCheck:
    if settings.search_provider is not SearchProviderMode.BRAVE:
        return ReadinessCheck(
            id="search_secret",
            status="pass",
            detail="external Search secret is not required",
        )
    available = bool(
        settings.search_api_key_ref
        and _secret_available(settings.search_api_key_ref, environ, minimum_length=16)
    )
    return ReadinessCheck(
        id="search_secret",
        status="pass" if available else "fail",
        detail=(
            "Search API secret is available"
            if available
            else "Search API secret is unavailable or too short"
        ),
    )


def _pause_check(settings: Settings) -> tuple[ReadinessCheck, bool]:
    if settings.public_pause_file is None:
        return (
            ReadinessCheck(
                id="runtime_pause",
                status="warn",
                detail="operator runtime pause file is not configured",
            ),
            False,
        )
    path = Path(settings.public_pause_file)
    parent = path.parent
    try:
        parent_metadata = parent.lstat()
    except OSError:
        return (
            ReadinessCheck(
                id="runtime_pause",
                status="fail",
                detail="runtime pause parent directory is unavailable",
            ),
            True,
        )
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(parent_metadata.st_mode):
        return (
            ReadinessCheck(
                id="runtime_pause",
                status="fail",
                detail="runtime pause parent is not a safe directory",
            ),
            True,
        )
    if stat.S_IMODE(parent_metadata.st_mode) & 0o022:
        return (
            ReadinessCheck(
                id="runtime_pause",
                status="fail",
                detail="runtime pause parent is writable by group or others",
            ),
            True,
        )
    paused = FilePauseSignal(path).paused
    return (
        ReadinessCheck(
            id="runtime_pause",
            status="pass",
            detail=(
                "operator runtime pause is configured and active"
                if paused
                else "operator runtime pause is configured and open"
            ),
        ),
        paused,
    )


def _secret_available(
    reference: str,
    environ: Mapping[str, str],
    *,
    minimum_length: int,
) -> bool:
    variable = reference.removeprefix("env://")
    value = environ.get(variable)
    return value is not None and bool(value.strip()) and len(value) >= minimum_length
