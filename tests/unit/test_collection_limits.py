from __future__ import annotations

import pytest

from psr_mcp.collectors.models import CollectionLimits


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"max_response_bytes": 0}, "max_response_bytes"),
        ({"connect_timeout_seconds": 0}, "component"),
        ({"read_timeout_seconds": 61}, "component"),
        ({"total_timeout_seconds": 0}, "total"),
        ({"total_timeout_seconds": 121}, "total"),
    ],
)
def test_collection_limits_fail_closed(
    kwargs: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        CollectionLimits(**kwargs)
