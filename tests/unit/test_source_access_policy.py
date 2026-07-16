from __future__ import annotations

import asyncio
import gc
import hashlib
from datetime import UTC, datetime

import pytest

from psr_mcp.collectors.access_policy import (
    AllowAllSourceAccessPolicy,
    RobotsSourceAccessPolicy,
    SourceAccessStatus,
    _robots_url,
)
from psr_mcp.collectors.models import CollectedDocument
from psr_mcp.collectors.safe import CollectionError, CollectionErrorCode


class Collector:
    def __init__(
        self,
        outcomes: dict[str, CollectedDocument | Exception],
        *,
        delay: float = 0,
    ) -> None:
        self.outcomes = outcomes
        self.delay = delay
        self.calls: list[tuple[str, int | None]] = []

    async def collect(
        self,
        url: str,
        *,
        max_response_bytes: int | None = None,
    ) -> CollectedDocument:
        self.calls.append((url, max_response_bytes))
        if self.delay:
            await asyncio.sleep(self.delay)
        outcome = self.outcomes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _document(url: str, body: bytes) -> CollectedDocument:
    return CollectedDocument(
        requested_url=url,
        final_url=url,
        redirect_chain=(),
        status=200,
        headers={"content-type": "text/plain"},
        content_type="text/plain",
        body=body,
        sha256=hashlib.sha256(body).hexdigest(),
        retrieved_at=datetime(2026, 7, 16, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_robots_policy_disallows_path_and_reuses_public_rules() -> None:
    robots_url = "https://agency.go.kr/robots.txt"
    body = b"User-agent: *\nDisallow: /private\nAllow: /\n"
    collector = Collector({robots_url: _document(robots_url, body)})
    policy = RobotsSourceAccessPolicy(collector)

    denied = await policy.evaluate(
        "https://agency.go.kr/private/report",
        max_response_bytes=100_000,
    )
    allowed = await policy.evaluate(
        "https://agency.go.kr/public/report",
        max_response_bytes=100_000,
    )

    assert denied.status is SourceAccessStatus.DISALLOWED
    assert denied.bytes_consumed == len(body)
    assert allowed.status is SourceAccessStatus.ALLOWED
    assert allowed.bytes_consumed == 0
    assert collector.calls == [(robots_url, 65_536)]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status, expected, retryable",
    [
        (404, SourceAccessStatus.ALLOWED, False),
        (403, SourceAccessStatus.DISALLOWED, False),
        (503, SourceAccessStatus.UNAVAILABLE, True),
    ],
)
async def test_robots_policy_handles_missing_restricted_and_failed_endpoint(
    status: int,
    expected: SourceAccessStatus,
    retryable: bool,
) -> None:
    robots_url = "https://agency.go.kr/robots.txt"
    collector = Collector(
        {
            robots_url: CollectionError(
                CollectionErrorCode.HTTP_STATUS_NOT_USABLE,
                "fixture status",
                retryable=status >= 500,
                http_status=status,
            )
        }
    )
    policy = RobotsSourceAccessPolicy(collector)

    decision = await policy.evaluate(
        "https://agency.go.kr/document",
        max_response_bytes=10_000,
    )

    assert decision.status is expected
    assert decision.retryable is retryable


@pytest.mark.anyio
async def test_robots_policy_serializes_same_origin_fetch() -> None:
    robots_url = "https://agency.go.kr/robots.txt"
    collector = Collector(
        {robots_url: _document(robots_url, b"User-agent: *\nAllow: /\n")},
        delay=0.01,
    )
    policy = RobotsSourceAccessPolicy(collector)

    first, second = await asyncio.gather(
        policy.evaluate(
            "https://agency.go.kr/one",
            max_response_bytes=10_000,
        ),
        policy.evaluate(
            "https://agency.go.kr/two",
            max_response_bytes=10_000,
        ),
    )

    assert first.allowed and second.allowed
    assert len(collector.calls) == 1


@pytest.mark.anyio
async def test_robots_policy_does_not_retain_one_lock_per_seen_origin() -> None:
    outcomes: dict[str, CollectedDocument | Exception] = {
        f"https://agency{index}.go.kr/robots.txt": _document(
            f"https://agency{index}.go.kr/robots.txt",
            b"User-agent: *\nAllow: /\n",
        )
        for index in range(20)
    }
    policy = RobotsSourceAccessPolicy(
        Collector(outcomes),
        max_cache_entries=2,
    )

    for index in range(20):
        decision = await policy.evaluate(
            f"https://agency{index}.go.kr/document",
            max_response_bytes=10_000,
        )
        assert decision.allowed

    gc.collect()

    assert len(policy._locks) == 0
    assert len(policy._cache) == 2


@pytest.mark.anyio
async def test_source_access_policies_fail_closed_on_bad_url_and_exception() -> None:
    allow_all = await AllowAllSourceAccessPolicy().evaluate(
        "fixture://source",
        max_response_bytes=1,
    )
    assert allow_all.allowed

    collector = Collector({"https://agency.go.kr/robots.txt": RuntimeError("collector exploded")})
    policy = RobotsSourceAccessPolicy(collector)
    failed = await policy.evaluate(
        "https://agency.go.kr/document",
        max_response_bytes=10_000,
    )
    invalid = await policy.evaluate(
        "https://user:pass@agency.go.kr/document",
        max_response_bytes=10_000,
    )
    no_budget = await policy.evaluate(
        "https://other.go.kr/document",
        max_response_bytes=0,
    )

    assert failed.status is SourceAccessStatus.UNAVAILABLE
    assert failed.retryable is True
    assert invalid.status is SourceAccessStatus.URL_NOT_ALLOWED
    assert no_budget.status is SourceAccessStatus.UNAVAILABLE


def test_robots_url_and_configuration_reject_unsafe_values() -> None:
    assert _robots_url("http://agency.go.kr/document") is None
    assert _robots_url("https://agency.go.kr:444/document") is None
    assert _robots_url("https://[invalid") is None
    assert _robots_url("https://agency.go.kr/document") == ("https://agency.go.kr/robots.txt")

    collector = Collector({})
    with pytest.raises(ValueError, match="user_agent"):
        RobotsSourceAccessPolicy(collector, user_agent="")
    with pytest.raises(ValueError, match="cache_ttl_seconds"):
        RobotsSourceAccessPolicy(collector, cache_ttl_seconds=0)
    with pytest.raises(ValueError, match="max_cache_entries"):
        RobotsSourceAccessPolicy(collector, max_cache_entries=0)
    with pytest.raises(ValueError, match="max_robots_bytes"):
        RobotsSourceAccessPolicy(collector, max_robots_bytes=1_023)
