"""robots.txt access policy evaluated before candidate document collection."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from weakref import WeakValueDictionary

from psr_mcp.collectors.models import CollectedDocument
from psr_mcp.collectors.safe import CollectionError, CollectionErrorCode
from psr_mcp.collectors.url_policy import UrlPolicyError


class SourceAccessStatus(StrEnum):
    ALLOWED = "ALLOWED"
    DISALLOWED = "DISALLOWED"
    UNAVAILABLE = "UNAVAILABLE"
    URL_NOT_ALLOWED = "URL_NOT_ALLOWED"


@dataclass(frozen=True, slots=True)
class SourceAccessDecision:
    status: SourceAccessStatus
    explanation: str
    retryable: bool
    bytes_consumed: int = 0

    @property
    def allowed(self) -> bool:
        return self.status is SourceAccessStatus.ALLOWED


class SourceAccessPolicy(Protocol):
    async def evaluate(
        self,
        url: str,
        *,
        max_response_bytes: int,
    ) -> SourceAccessDecision: ...


class RobotsCollector(Protocol):
    async def collect(
        self,
        url: str,
        *,
        max_response_bytes: int | None = None,
    ) -> CollectedDocument: ...


class AllowAllSourceAccessPolicy:
    """Explicit test/development policy; production composition must not use it."""

    async def evaluate(
        self,
        url: str,
        *,
        max_response_bytes: int,
    ) -> SourceAccessDecision:
        del url, max_response_bytes
        return SourceAccessDecision(
            SourceAccessStatus.ALLOWED,
            "development fixture access policy",
            retryable=False,
        )


class RobotsSourceAccessPolicy:
    def __init__(
        self,
        collector: RobotsCollector,
        *,
        user_agent: str = "public-sector-research-mcp",
        cache_ttl_seconds: float = 3_600,
        max_cache_entries: int = 1_024,
        max_robots_bytes: int = 65_536,
    ) -> None:
        if not user_agent.strip() or len(user_agent) > 200:
            raise ValueError("robots user_agent must contain 1..200 characters")
        if cache_ttl_seconds < 1 or cache_ttl_seconds > 86_400:
            raise ValueError("robots cache_ttl_seconds must be 1..86400")
        if max_cache_entries < 1 or max_cache_entries > 10_000:
            raise ValueError("robots max_cache_entries must be 1..10000")
        if max_robots_bytes < 1_024 or max_robots_bytes > 1_048_576:
            raise ValueError("robots max_robots_bytes must be 1024..1048576")
        self._collector = collector
        self._user_agent = user_agent
        self._cache_ttl_seconds = cache_ttl_seconds
        self._max_cache_entries = max_cache_entries
        self._max_robots_bytes = max_robots_bytes
        self._cache: OrderedDict[str, _CachedRules] = OrderedDict()
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self._locks_guard = asyncio.Lock()

    async def evaluate(
        self,
        url: str,
        *,
        max_response_bytes: int,
    ) -> SourceAccessDecision:
        robots_url = _robots_url(url)
        if robots_url is None:
            return SourceAccessDecision(
                SourceAccessStatus.URL_NOT_ALLOWED,
                "candidate URL could not be normalized for robots policy",
                retryable=False,
            )
        origin = _origin(robots_url)
        cached = self._cached(origin)
        if cached is not None:
            return cached.decision(url, self._user_agent, bytes_consumed=0)
        lock = await self._lock(origin)
        async with lock:
            cached = self._cached(origin)
            if cached is not None:
                return cached.decision(url, self._user_agent, bytes_consumed=0)
            budget = min(max_response_bytes, self._max_robots_bytes)
            if budget < 1:
                return SourceAccessDecision(
                    SourceAccessStatus.UNAVAILABLE,
                    "run byte budget did not allow robots policy retrieval",
                    retryable=False,
                )
            rules, consumed = await self._load(robots_url, budget)
            self._store(origin, rules)
            return rules.decision(
                url,
                self._user_agent,
                bytes_consumed=consumed,
            )

    async def _load(
        self,
        robots_url: str,
        budget: int,
    ) -> tuple[_CachedRules, int]:
        try:
            document = await self._collector.collect(
                robots_url,
                max_response_bytes=budget,
            )
        except UrlPolicyError:
            return (
                _CachedRules(
                    status=SourceAccessStatus.URL_NOT_ALLOWED,
                    explanation="robots URL failed the public URL policy",
                    retryable=False,
                    parser=None,
                    expires_at=_expiry(self._cache_ttl_seconds),
                ),
                0,
            )
        except CollectionError as error:
            if error.code is CollectionErrorCode.HTTP_STATUS_NOT_USABLE and error.http_status in {
                404,
                410,
            }:
                return (
                    _CachedRules(
                        status=SourceAccessStatus.ALLOWED,
                        explanation="site does not publish a robots.txt file",
                        retryable=False,
                        parser=None,
                        expires_at=_expiry(self._cache_ttl_seconds),
                    ),
                    0,
                )
            if error.code is CollectionErrorCode.HTTP_STATUS_NOT_USABLE and error.http_status in {
                401,
                403,
            }:
                return (
                    _CachedRules(
                        status=SourceAccessStatus.DISALLOWED,
                        explanation="robots policy endpoint is access-restricted",
                        retryable=False,
                        parser=None,
                        expires_at=_expiry(self._cache_ttl_seconds),
                    ),
                    0,
                )
            return (
                _CachedRules(
                    status=SourceAccessStatus.UNAVAILABLE,
                    explanation="robots policy could not be retrieved safely",
                    retryable=error.retryable,
                    parser=None,
                    expires_at=_expiry(min(self._cache_ttl_seconds, 60)),
                ),
                0,
            )
        except Exception:
            return (
                _CachedRules(
                    status=SourceAccessStatus.UNAVAILABLE,
                    explanation="robots policy evaluation failed safely",
                    retryable=True,
                    parser=None,
                    expires_at=_expiry(min(self._cache_ttl_seconds, 60)),
                ),
                0,
            )
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(document.body.decode("utf-8", errors="replace").splitlines())
        return (
            _CachedRules(
                status=SourceAccessStatus.ALLOWED,
                explanation="robots.txt was retrieved and evaluated",
                retryable=False,
                parser=parser,
                expires_at=_expiry(self._cache_ttl_seconds),
            ),
            len(document.body),
        )

    def _cached(self, origin: str) -> _CachedRules | None:
        rules = self._cache.get(origin)
        if rules is None:
            return None
        if rules.expires_at <= time.monotonic():
            del self._cache[origin]
            return None
        self._cache.move_to_end(origin)
        return rules

    def _store(self, origin: str, rules: _CachedRules) -> None:
        self._cache[origin] = rules
        self._cache.move_to_end(origin)
        while len(self._cache) > self._max_cache_entries:
            self._cache.popitem(last=False)

    async def _lock(self, origin: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(origin)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[origin] = lock
            return lock


@dataclass(frozen=True, slots=True)
class _CachedRules:
    status: SourceAccessStatus
    explanation: str
    retryable: bool
    parser: RobotFileParser | None
    expires_at: float

    def decision(
        self,
        url: str,
        user_agent: str,
        *,
        bytes_consumed: int,
    ) -> SourceAccessDecision:
        if self.status is not SourceAccessStatus.ALLOWED:
            return SourceAccessDecision(
                self.status,
                self.explanation,
                self.retryable,
                bytes_consumed,
            )
        if self.parser is not None and not self.parser.can_fetch(user_agent, url):
            return SourceAccessDecision(
                SourceAccessStatus.DISALLOWED,
                "robots.txt disallows collection of the candidate path",
                retryable=False,
                bytes_consumed=bytes_consumed,
            )
        return SourceAccessDecision(
            SourceAccessStatus.ALLOWED,
            self.explanation,
            retryable=False,
            bytes_consumed=bytes_consumed,
        )


def _robots_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return None
    host = parsed.hostname.casefold().rstrip(".")
    if not host:
        return None
    netloc = f"[{host}]" if ":" in host else host
    return urlunsplit(("https", netloc, "/robots.txt", "", ""))


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _expiry(ttl_seconds: float) -> float:
    return time.monotonic() + ttl_seconds
