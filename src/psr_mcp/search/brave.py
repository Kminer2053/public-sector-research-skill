"""Bounded Brave Web Search adapter; search results remain candidates only."""

from __future__ import annotations

import asyncio
import hashlib
import json
from html import unescape

import httpx

from psr_mcp.search.models import (
    SearchFailure,
    SearchQuery,
    SearchResult,
    SourceCandidate,
)
from psr_mcp.search.registry import GovernmentSourceRegistry

BRAVE_WEB_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    def __init__(
        self,
        *,
        api_key: str,
        client: httpx.AsyncClient,
        registry: GovernmentSourceRegistry,
        timeout_seconds: float = 5.0,
        max_response_bytes: int = 1_048_576,
        max_concurrency: int = 3,
    ) -> None:
        if len(api_key) < 16:
            raise ValueError("Brave Search API key is too short")
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("timeout_seconds must be >0 and <=30")
        if max_response_bytes < 1_024 or max_response_bytes > 10_485_760:
            raise ValueError("max_response_bytes must be 1024..10485760")
        if max_concurrency < 1 or max_concurrency > 10:
            raise ValueError("max_concurrency must be 1..10")
        self._api_key = api_key
        self._client = client
        self._registry = registry
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def search(self, query: SearchQuery) -> SearchResult:
        if (
            not query.text
            or len(query.text) > 400
            or len(query.text.split()) > 50
            or query.max_results < 1
            or query.max_results > 20
        ):
            return _failed(
                query,
                code="QUERY_INVALID",
                message="search query exceeded the configured provider limits",
                retryable=False,
            )
        try:
            async with (
                self._semaphore,
                asyncio.timeout(self._timeout_seconds),
                self._client.stream(
                    "GET",
                    BRAVE_WEB_SEARCH_ENDPOINT,
                    params={
                        "q": query.text,
                        "count": query.max_results,
                        "country": "KR",
                        "search_lang": "ko",
                        "ui_lang": "ko-KR",
                        "safesearch": "strict",
                        "spellcheck": "false",
                        "text_decorations": "false",
                        "result_filter": "web",
                    },
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "Cache-Control": "no-cache",
                        "User-Agent": "public-sector-research-mcp/0.1",
                        "X-Subscription-Token": self._api_key,
                    },
                ) as response,
            ):
                status = response.status_code
                if status != 200:
                    return _http_failure(query, status)
                encoding = response.headers.get("content-encoding", "identity")
                if encoding.casefold() not in {"", "identity"}:
                    return _failed(
                        query,
                        code="RESPONSE_ENCODING_INVALID",
                        message="search provider returned an unsupported encoding",
                        retryable=False,
                    )
                body = await _read_bounded(response, self._max_response_bytes)
        except (TimeoutError, httpx.TimeoutException):
            return _failed(
                query,
                code="TIMEOUT",
                message="search provider exceeded its time budget",
                retryable=True,
            )
        except (httpx.NetworkError, httpx.ProtocolError):
            return _failed(
                query,
                code="NETWORK_FAILED",
                message="search provider request failed",
                retryable=True,
            )
        except _ResponseTooLarge:
            return _failed(
                query,
                code="RESPONSE_TOO_LARGE",
                message="search provider response exceeded the byte limit",
                retryable=False,
            )
        return _parse_response(query, body, self._registry)


async def _read_bounded(response: httpx.Response, max_bytes: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            length = int(declared)
            if length < 0 or length > max_bytes:
                raise _ResponseTooLarge
        except ValueError:
            raise _ResponseTooLarge from None
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_raw():
        size += len(chunk)
        if size > max_bytes:
            raise _ResponseTooLarge
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_response(
    query: SearchQuery,
    body: bytes,
    registry: GovernmentSourceRegistry,
) -> SearchResult:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _failed(
            query,
            code="RESPONSE_INVALID",
            message="search provider returned malformed JSON",
            retryable=False,
        )
    if not isinstance(payload, dict):
        return _failed(
            query,
            code="RESPONSE_INVALID",
            message="search provider response was not an object",
            retryable=False,
        )
    web = payload.get("web")
    if web is None:
        return SearchResult(candidates=())
    if not isinstance(web, dict) or not isinstance(web.get("results"), list):
        return _failed(
            query,
            code="RESPONSE_INVALID",
            message="search provider web results were malformed",
            retryable=False,
        )

    candidates: list[SourceCandidate] = []
    invalid_results = 0
    for record in web["results"]:
        candidate = _candidate(query, record, registry)
        if candidate is None:
            invalid_results += 1
            continue
        candidates.append(candidate)
        if len(candidates) >= query.max_results:
            break
    failures: tuple[SearchFailure, ...] = ()
    if invalid_results:
        failures = (
            SearchFailure(
                query_id=query.id,
                code="RESULT_ENTRY_INVALID",
                message=f"{invalid_results} search result entries were ignored",
                retryable=False,
            ),
        )
    return SearchResult(
        candidates=tuple(candidates),
        failures=failures,
    )


def _candidate(
    query: SearchQuery,
    record: object,
    registry: GovernmentSourceRegistry,
) -> SourceCandidate | None:
    if not isinstance(record, dict):
        return None
    title = record.get("title")
    url = record.get("url")
    if not isinstance(title, str) or not isinstance(url, str):
        return None
    normalized_title = _display_text(title, 500)
    if not normalized_title or len(url) > 2_048:
        return None
    identity = registry.classify(
        url,
        preferred_domains=query.preferred_domains,
    )
    digest = hashlib.sha256(f"{query.id}\0{url}".encode()).hexdigest()[:16]
    return SourceCandidate(
        id=f"src-{digest}",
        track_id=query.track_id,
        url=url,
        title=normalized_title,
        publisher=identity.publisher,
        source_tier=identity.source_tier,
    )


def _display_text(value: str, limit: int) -> str:
    return " ".join(unescape(value).split())[:limit]


def _http_failure(query: SearchQuery, status: int) -> SearchResult:
    if status == 429:
        return _failed(
            query,
            code="RATE_LIMITED",
            message="search provider rate limit was reached",
            retryable=True,
        )
    if status in {401, 403}:
        return _failed(
            query,
            code="AUTH_FAILED",
            message="search provider rejected its server credential",
            retryable=False,
        )
    return _failed(
        query,
        code="UPSTREAM_FAILED",
        message="search provider returned an unusable status",
        retryable=status >= 500,
    )


def _failed(
    query: SearchQuery,
    *,
    code: str,
    message: str,
    retryable: bool,
) -> SearchResult:
    return SearchResult(
        candidates=(),
        failures=(
            SearchFailure(
                query_id=query.id,
                code=code,
                message=message,
                retryable=retryable,
            ),
        ),
    )


class _ResponseTooLarge(RuntimeError):
    pass
