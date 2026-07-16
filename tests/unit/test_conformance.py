from __future__ import annotations

from pathlib import Path

import pytest

from psr_mcp.conformance import (
    ConformanceError,
    ConformanceOptions,
    PublicConformanceOptions,
    _require_public_policy,
)


@pytest.mark.parametrize(
    "options, message",
    [
        (ConformanceOptions(endpoint="not-a-url"), "safe absolute"),
        (
            ConformanceOptions(endpoint="http://research.example.gov/mcp"),
            "must use HTTPS",
        ),
        (
            ConformanceOptions(endpoint="https://user:secret@research.example.gov/mcp"),
            "safe absolute",
        ),
        (
            ConformanceOptions(endpoint="https://research.example.gov/mcp", timeout_seconds=0),
            "timeout",
        ),
        (
            ConformanceOptions(
                endpoint="https://research.example.gov/mcp", idempotency_key="short"
            ),
            "idempotency",
        ),
        (
            ConformanceOptions(
                endpoint="https://research.example.gov/mcp",
                ca_bundle="/path/that/does/not/exist.pem",
            ),
            "readable file",
        ),
    ],
)
def test_conformance_options_fail_closed(options: ConformanceOptions, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        options.validate()


def test_ca_bundle_is_rejected_for_plain_http(tmp_path: Path) -> None:
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("not parsed during option validation")
    options = ConformanceOptions(
        endpoint="http://127.0.0.1:8000/mcp",
        ca_bundle=str(ca_bundle),
    )
    with pytest.raises(ValueError, match="only for HTTPS"):
        options.validate()


@pytest.mark.parametrize(
    "options, message",
    [
        (PublicConformanceOptions(endpoint="not-a-url"), "safe absolute"),
        (
            PublicConformanceOptions(endpoint="http://research.example.gov/mcp"),
            "must use HTTPS",
        ),
        (
            PublicConformanceOptions(
                endpoint="https://research.example.gov/mcp",
                timeout_seconds=301,
            ),
            "timeout",
        ),
    ],
)
def test_public_conformance_options_fail_closed(
    options: PublicConformanceOptions,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        options.validate()


def _valid_public_policy() -> dict[str, object]:
    return {
        "service_mode": "public_ephemeral",
        "authentication_required": False,
        "research_available": True,
        "kill_switch_active": False,
        "source_discovery": "curated_seed",
        "supported_profiles": ["government-v0"],
        "retention": {
            "server_saved": False,
            "feedback_content_linked": False,
        },
    }


@pytest.mark.parametrize(
    "update, message",
    [
        ({"service_mode": "foundation"}, "wrong mode"),
        ({"authentication_required": True}, "requires authentication"),
        ({"research_available": False}, "not accepting"),
        ({"kill_switch_active": True}, "paused"),
        ({"retention": None}, "omitted retention"),
        (
            {
                "retention": {
                    "server_saved": True,
                    "feedback_content_linked": False,
                }
            },
            "persistent server content",
        ),
        (
            {
                "retention": {
                    "server_saved": False,
                    "feedback_content_linked": True,
                }
            },
            "linked feedback",
        ),
        ({"supported_profiles": []}, "reviewed profile"),
    ],
)
def test_public_policy_contract_rejects_unsafe_or_inconsistent_values(
    update: dict[str, object],
    message: str,
) -> None:
    policy = {**_valid_public_policy(), **update}

    with pytest.raises(ConformanceError, match=message):
        _require_public_policy(policy)


def test_public_policy_contract_accepts_reviewed_values() -> None:
    _require_public_policy(_valid_public_policy())
