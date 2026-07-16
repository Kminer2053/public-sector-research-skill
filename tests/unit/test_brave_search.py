from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest

from psr_mcp.search import (
    BraveSearchProvider,
    GovernmentSourceRegistry,
    SearchQuery,
    SourceTier,
)


class RecordingLimiter:
    def __init__(self) -> None:
        self.hosts: list[str] = []

    @asynccontextmanager
    async def slot(self, host: str) -> AsyncIterator[None]:
        self.hosts.append(host)
        yield


def _query(
    *,
    text: str = "AI 구매 법령 (site:law.go.kr)",
    max_results: int = 5,
) -> SearchQuery:
    return SearchQuery(
        id="qry-test",
        track_id="law-regulation",
        research_question="공공기관 AI 구매 원칙을 조사해줘",
        text=text,
        preferred_domains=("law.go.kr", "moleg.go.kr"),
        max_results=max_results,
    )


def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
    **kwargs: object,
) -> tuple[BraveSearchProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        trust_env=False,
    )
    return (
        BraveSearchProvider(
            api_key="test-api-key-1234567890",
            client=client,
            registry=GovernmentSourceRegistry(),
            **kwargs,  # type: ignore[arg-type]
        ),
        client,
    )


def _response(
    body: bytes,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        headers=headers,
        stream=httpx.ByteStream(body),
    )


def _json_response(payload: object) -> httpx.Response:
    return _response(
        json.dumps(payload, ensure_ascii=False).encode(),
        headers={"content-type": "application/json"},
    )


@pytest.mark.anyio
async def test_brave_search_maps_results_without_treating_them_as_evidence() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _json_response(
            {
                "web": {
                    "results": [
                        {
                            "title": "국가법령정보센터 &amp; AI 법령",
                            "url": "https://www.law.go.kr/법령/인공지능",
                        },
                        {
                            "title": "Unknown result",
                            "url": "https://news.example.com/ai",
                        },
                        {"url": "https://law.go.kr/missing-title"},
                        None,
                        {
                            "title": " ",
                            "url": "https://law.go.kr/blank-title",
                        },
                    ]
                }
            }
        )

    provider, client = _provider(handler)
    try:
        first = await provider.search(_query())
        second = await provider.search(_query())
    finally:
        await client.aclose()

    assert first == second
    assert len(first.candidates) == 2
    official, unknown = first.candidates
    assert official.title == "국가법령정보센터 & AI 법령"
    assert official.publisher == "국가법령정보센터"
    assert official.source_tier is SourceTier.OFFICIAL_PRIMARY
    assert unknown.source_tier is SourceTier.UNVERIFIED_WEB
    assert first.failures[0].code == "RESULT_ENTRY_INVALID"
    assert requests[0].headers["x-subscription-token"] == "test-api-key-1234567890"
    assert requests[0].headers["accept-encoding"] == "identity"
    assert requests[0].url.params["country"] == "KR"
    assert requests[0].url.params["search_lang"] == "ko"
    assert requests[0].url.params["safesearch"] == "strict"
    assert requests[0].url.params["result_filter"] == "web"


@pytest.mark.anyio
async def test_brave_search_uses_shared_outbound_limiter() -> None:
    limiter = RecordingLimiter()
    provider, client = _provider(
        lambda request: _json_response({"web": {"results": []}}),
        outbound_limiter=limiter,
    )
    try:
        result = await provider.search(_query())
    finally:
        await client.aclose()

    assert result.failures == ()
    assert limiter.hosts == ["api.search.brave.com"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status, code, retryable",
    [
        (401, "AUTH_FAILED", False),
        (429, "RATE_LIMITED", True),
        (503, "UPSTREAM_FAILED", True),
        (422, "UPSTREAM_FAILED", False),
    ],
)
async def test_brave_search_http_failures_are_typed(
    status: int,
    code: str,
    retryable: bool,
) -> None:
    provider, client = _provider(lambda request: httpx.Response(status, request=request))
    try:
        result = await provider.search(_query())
    finally:
        await client.aclose()

    assert result.candidates == ()
    assert result.failures[0].code == code
    assert result.failures[0].retryable is retryable


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response, code",
    [
        (
            httpx.Response(
                200,
                headers={"content-encoding": "gzip"},
                stream=httpx.ByteStream(b"compressed"),
            ),
            "RESPONSE_ENCODING_INVALID",
        ),
        (
            _response(
                b"{}",
                headers={"content-length": "invalid"},
            ),
            "RESPONSE_TOO_LARGE",
        ),
        (
            _response(b"x" * 2_000),
            "RESPONSE_TOO_LARGE",
        ),
        (
            _response(b"not-json"),
            "RESPONSE_INVALID",
        ),
        (
            _json_response([]),
            "RESPONSE_INVALID",
        ),
        (
            _json_response({"web": {"results": {}}}),
            "RESPONSE_INVALID",
        ),
    ],
)
async def test_brave_search_rejects_unbounded_or_malformed_responses(
    response: httpx.Response,
    code: str,
) -> None:
    provider, client = _provider(
        lambda request: response,
        max_response_bytes=1_024,
    )
    try:
        result = await provider.search(_query())
    finally:
        await client.aclose()

    assert result.failures[0].code == code


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error, code",
    [
        (httpx.ConnectError("offline"), "NETWORK_FAILED"),
        (httpx.ReadTimeout("slow"), "TIMEOUT"),
    ],
)
async def test_brave_search_network_failures_do_not_expose_credentials(
    error: httpx.HTTPError,
    code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    provider, client = _provider(handler)
    try:
        result = await provider.search(_query())
    finally:
        await client.aclose()

    assert result.failures[0].code == code
    assert "test-api-key" not in result.failures[0].message


@pytest.mark.anyio
async def test_brave_search_validates_query_before_network() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _json_response({"web": {"results": []}})

    provider, client = _provider(handler)
    try:
        too_long = await provider.search(_query(text="x" * 401))
        too_many = await provider.search(_query(max_results=21))
        empty_web = await provider.search(_query())
    finally:
        await client.aclose()

    assert too_long.failures[0].code == "QUERY_INVALID"
    assert too_many.failures[0].code == "QUERY_INVALID"
    assert empty_web.candidates == ()
    assert empty_web.failures == ()
    assert calls == 1


@pytest.mark.anyio
async def test_brave_search_handles_no_web_and_result_cap() -> None:
    responses = [
        _json_response({}),
        _json_response(
            {
                "web": {
                    "results": [
                        {
                            "title": "First",
                            "url": "https://law.go.kr/first",
                        },
                        {
                            "title": "Second",
                            "url": "https://law.go.kr/second",
                        },
                    ]
                }
            }
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return responses.pop(0)

    provider, client = _provider(handler)
    try:
        no_web = await provider.search(_query())
        capped = await provider.search(_query(max_results=1))
    finally:
        await client.aclose()

    assert no_web == type(no_web)(candidates=())
    assert len(capped.candidates) == 1


@pytest.mark.anyio
async def test_brave_search_rejects_declared_oversize_response() -> None:
    provider, client = _provider(
        lambda request: _response(
            b"{}",
            headers={"content-length": "2048"},
        ),
        max_response_bytes=1_024,
    )
    try:
        result = await provider.search(_query())
    finally:
        await client.aclose()

    assert result.failures[0].code == "RESPONSE_TOO_LARGE"


def test_brave_search_and_registry_configuration_fail_closed() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    try:
        with pytest.raises(ValueError, match="too short"):
            BraveSearchProvider(
                api_key="short",
                client=client,
                registry=GovernmentSourceRegistry(),
            )
        with pytest.raises(ValueError, match="timeout_seconds"):
            BraveSearchProvider(
                api_key="test-api-key-1234567890",
                client=client,
                registry=GovernmentSourceRegistry(),
                timeout_seconds=31,
            )
        with pytest.raises(ValueError, match="max_response_bytes"):
            BraveSearchProvider(
                api_key="test-api-key-1234567890",
                client=client,
                registry=GovernmentSourceRegistry(),
                max_response_bytes=1_023,
            )
        with pytest.raises(ValueError, match="max_concurrency"):
            BraveSearchProvider(
                api_key="test-api-key-1234567890",
                client=client,
                registry=GovernmentSourceRegistry(),
                max_concurrency=0,
            )
    finally:
        import asyncio

        asyncio.run(client.aclose())

    registry = GovernmentSourceRegistry()
    subdomain = registry.classify(
        "https://sub.pipc.go.kr/document",
        preferred_domains=(),
    )
    preferred = registry.classify(
        "https://agency.go.kr/document",
        preferred_domains=("agency.go.kr",),
    )
    malformed = registry.classify(
        "https://[invalid",
        preferred_domains=(),
    )
    nist_publication = registry.classify(
        "https://www.nist.gov/publications/artificial-intelligence-risk-management-framework",
        preferred_domains=(),
    )
    nist_hosted_third_party = registry.classify(
        "https://www.nist.gov/system/files/documents/2021/08/23/ai-rmf-rfi-0039-1.pdf",
        preferred_domains=(),
    )
    nist_catalog_pdf = registry.classify(
        "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=936225",
        preferred_domains=(),
    )
    assert subdomain.publisher == "개인정보보호위원회"
    assert preferred.source_tier is SourceTier.OFFICIAL_SECONDARY
    assert malformed.source_tier is SourceTier.UNVERIFIED_WEB
    assert nist_publication.source_tier is SourceTier.OFFICIAL_PRIMARY
    assert nist_catalog_pdf.source_tier is SourceTier.OFFICIAL_PRIMARY
    assert nist_hosted_third_party.source_tier is SourceTier.OFFICIAL_SECONDARY
    assert "저자 미확인" in nist_hosted_third_party.publisher
