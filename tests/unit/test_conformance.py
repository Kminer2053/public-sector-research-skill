from __future__ import annotations

from pathlib import Path

import pytest

from psr_mcp.conformance import ConformanceOptions


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
