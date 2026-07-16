from __future__ import annotations

import ipaddress
from datetime import UTC, datetime

import pytest

from psr_mcp.collectors.models import CollectionLimits, RawHttpResponse
from psr_mcp.collectors.safe import (
    CollectionError,
    CollectionErrorCode,
    SafeCollector,
)
from psr_mcp.collectors.url_policy import IpAddress, UrlPolicy, ValidatedUrl


class Clock:
    def now(self) -> datetime:
        return datetime(2026, 7, 16, tzinfo=UTC)


class Resolver:
    def __init__(self, records: dict[str, tuple[str, ...]]) -> None:
        self.records = records

    async def resolve(self, host: str, port: int) -> tuple[IpAddress, ...]:
        del port
        return tuple(ipaddress.ip_address(value) for value in self.records.get(host, ()))


class Transport:
    def __init__(self, responses: dict[str, RawHttpResponse]) -> None:
        self.responses = responses
        self.calls: list[ValidatedUrl] = []
        self.limits: list[CollectionLimits] = []

    async def fetch(
        self,
        target: ValidatedUrl,
        limits: CollectionLimits,
    ) -> RawHttpResponse:
        self.calls.append(target)
        self.limits.append(limits)
        return self.responses[target.canonical_url]


def _collector(resolver: Resolver, transport: Transport) -> SafeCollector:
    return SafeCollector(
        policy=UrlPolicy(resolver),
        transport=transport,
        clock=Clock(),
        limits=CollectionLimits(max_response_bytes=1_024),
    )


@pytest.mark.anyio
async def test_collector_follows_validated_redirect_and_returns_hashed_document() -> None:
    resolver = Resolver(
        {
            "start.go.kr": ("93.184.216.34",),
            "final.go.kr": ("93.184.216.35",),
        }
    )
    transport = Transport(
        {
            "https://start.go.kr/": RawHttpResponse(
                status=302,
                headers={"location": "https://final.go.kr/document"},
                body=b"",
            ),
            "https://final.go.kr/document": RawHttpResponse(
                status=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=b"<main>official evidence</main>",
            ),
        }
    )

    result = await _collector(resolver, transport).collect("https://start.go.kr")

    assert result.requested_url == "https://start.go.kr"
    assert result.final_url == "https://final.go.kr/document"
    assert result.redirect_chain == ("https://start.go.kr/",)
    assert result.content_type == "text/html"
    assert result.body == b"<main>official evidence</main>"
    assert result.sha256 == "a1573a4d6da2e12384d2a71b9477a50345b2849afc961adda53f6b23b94e3617"
    assert result.retrieved_at == datetime(2026, 7, 16, tzinfo=UTC)
    assert [call.host for call in transport.calls] == ["start.go.kr", "final.go.kr"]


@pytest.mark.anyio
async def test_redirect_to_private_address_is_blocked_before_second_request() -> None:
    resolver = Resolver(
        {
            "start.go.kr": ("93.184.216.34",),
            "private.go.kr": ("127.0.0.1",),
        }
    )
    transport = Transport(
        {
            "https://start.go.kr/": RawHttpResponse(
                status=302,
                headers={"location": "https://private.go.kr/admin"},
                body=b"",
            )
        }
    )

    with pytest.raises(ValueError):
        await _collector(resolver, transport).collect("https://start.go.kr")

    assert len(transport.calls) == 1


@pytest.mark.anyio
async def test_missing_content_type_is_preserved_as_unknown() -> None:
    resolver = Resolver({"source.go.kr": ("93.184.216.34",)})
    transport = Transport(
        {
            "https://source.go.kr/": RawHttpResponse(
                status=200,
                headers={},
                body=b"document",
            )
        }
    )

    result = await _collector(resolver, transport).collect("https://source.go.kr")

    assert result.content_type is None


@pytest.mark.anyio
async def test_per_request_byte_budget_is_bounded_by_collector_configuration() -> None:
    resolver = Resolver({"source.go.kr": ("93.184.216.34",)})
    transport = Transport(
        {
            "https://source.go.kr/": RawHttpResponse(
                status=200,
                headers={"content-type": "text/plain"},
                body=b"document",
            )
        }
    )
    collector = _collector(resolver, transport)

    await collector.collect("https://source.go.kr", max_response_bytes=128)
    await collector.collect("https://source.go.kr", max_response_bytes=4_096)

    assert [limits.max_response_bytes for limits in transport.limits] == [128, 1_024]
    with pytest.raises(ValueError, match="positive"):
        await collector.collect("https://source.go.kr", max_response_bytes=0)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response, code, retryable",
    [
        (
            RawHttpResponse(status=503, headers={}, body=b"down"),
            CollectionErrorCode.HTTP_STATUS_NOT_USABLE,
            True,
        ),
        (
            RawHttpResponse(status=200, headers={}, body=b""),
            CollectionErrorCode.DOCUMENT_EMPTY,
            False,
        ),
        (
            RawHttpResponse(
                status=200,
                headers={"content-encoding": "gzip"},
                body=b"compressed",
            ),
            CollectionErrorCode.CONTENT_ENCODING_NOT_ALLOWED,
            False,
        ),
        (
            RawHttpResponse(status=302, headers={}, body=b""),
            CollectionErrorCode.REDIRECT_LOCATION_MISSING,
            False,
        ),
    ],
)
async def test_collector_returns_typed_failures(
    response: RawHttpResponse,
    code: CollectionErrorCode,
    retryable: bool,
) -> None:
    resolver = Resolver({"source.go.kr": ("93.184.216.34",)})
    transport = Transport({"https://source.go.kr/": response})

    with pytest.raises(CollectionError) as error:
        await _collector(resolver, transport).collect("https://source.go.kr")

    assert error.value.code is code
    assert error.value.retryable is retryable
