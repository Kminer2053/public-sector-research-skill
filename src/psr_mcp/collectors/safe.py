"""Manual-redirect SafeCollector over an IP-pinned transport."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from enum import StrEnum
from typing import Protocol
from urllib.parse import urljoin

from psr_mcp.application.ports import Clock
from psr_mcp.collectors.models import CollectedDocument, CollectionLimits, RawHttpResponse
from psr_mcp.collectors.url_policy import UrlPolicy, ValidatedUrl
from psr_mcp.common.outbound import OutboundLimiter


class CollectionErrorCode(StrEnum):
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    NETWORK_FAILED = "NETWORK_FAILED"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    RESPONSE_HEADER_INVALID = "RESPONSE_HEADER_INVALID"
    CONTENT_ENCODING_NOT_ALLOWED = "CONTENT_ENCODING_NOT_ALLOWED"
    HTTP_STATUS_NOT_USABLE = "HTTP_STATUS_NOT_USABLE"
    REDIRECT_LOCATION_MISSING = "REDIRECT_LOCATION_MISSING"
    DOCUMENT_EMPTY = "DOCUMENT_EMPTY"


class CollectionError(RuntimeError):
    def __init__(
        self,
        code: CollectionErrorCode,
        message: str,
        *,
        retryable: bool,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


class PinnedHttpTransport(Protocol):
    async def fetch(
        self,
        target: ValidatedUrl,
        limits: CollectionLimits,
    ) -> RawHttpResponse: ...


class SafeCollector:
    def __init__(
        self,
        *,
        policy: UrlPolicy,
        transport: PinnedHttpTransport,
        clock: Clock,
        limits: CollectionLimits,
        outbound_limiter: OutboundLimiter | None = None,
    ) -> None:
        self._policy = policy
        self._transport = transport
        self._clock = clock
        self._limits = limits
        self._outbound_limiter = outbound_limiter

    async def collect(
        self,
        url: str,
        *,
        max_response_bytes: int | None = None,
    ) -> CollectedDocument:
        limits = self._limits
        if max_response_bytes is not None:
            if max_response_bytes < 1:
                raise ValueError("max_response_bytes must be positive")
            limits = replace(
                self._limits,
                max_response_bytes=min(
                    max_response_bytes,
                    self._limits.max_response_bytes,
                ),
            )
        target = await self._policy.validate(url)
        redirect_chain: list[str] = []
        while True:
            response = await self._fetch(target, limits)
            if _is_redirect(response.status):
                location = response.headers.get("location")
                if not location:
                    raise CollectionError(
                        CollectionErrorCode.REDIRECT_LOCATION_MISSING,
                        "source redirect did not include a location",
                        retryable=False,
                        http_status=response.status,
                    )
                redirect_chain.append(target.canonical_url)
                target = await self._policy.validate(
                    urljoin(target.canonical_url, location),
                    redirect_count=target.redirect_count + 1,
                )
                continue

            if response.status < 200 or response.status >= 300:
                raise CollectionError(
                    CollectionErrorCode.HTTP_STATUS_NOT_USABLE,
                    "source returned an unusable HTTP status",
                    retryable=response.status in _RETRYABLE_STATUS,
                    http_status=response.status,
                )
            encoding = response.headers.get("content-encoding", "").strip().casefold()
            if encoding and encoding != "identity":
                raise CollectionError(
                    CollectionErrorCode.CONTENT_ENCODING_NOT_ALLOWED,
                    "source ignored the identity encoding requirement",
                    retryable=False,
                    http_status=response.status,
                )
            if not response.body:
                raise CollectionError(
                    CollectionErrorCode.DOCUMENT_EMPTY,
                    "source returned an empty document",
                    retryable=False,
                    http_status=response.status,
                )
            return CollectedDocument(
                requested_url=url,
                final_url=target.canonical_url,
                redirect_chain=tuple(redirect_chain),
                status=response.status,
                headers=response.headers,
                content_type=_content_type(response.headers),
                body=response.body,
                sha256=hashlib.sha256(response.body).hexdigest(),
                retrieved_at=self._clock.now(),
            )

    async def _fetch(
        self,
        target: ValidatedUrl,
        limits: CollectionLimits,
    ) -> RawHttpResponse:
        if self._outbound_limiter is None:
            return await self._transport.fetch(target, limits)
        async with self._outbound_limiter.slot(target.host):
            return await self._transport.fetch(target, limits)


def _is_redirect(status: int) -> bool:
    return status in {301, 302, 303, 307, 308}


def _content_type(headers: dict[str, str]) -> str | None:
    value = headers.get("content-type")
    if value is None:
        return None
    media_type = value.partition(";")[0].strip().casefold()
    return media_type or None


_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
