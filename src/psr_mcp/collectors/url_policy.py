"""SSRF-resistant URL and DNS policy for public-source collection."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit

type IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UrlPolicyErrorCode(StrEnum):
    INVALID_URL = "INVALID_URL"
    URL_TOO_LONG = "URL_TOO_LONG"
    SCHEME_NOT_ALLOWED = "SCHEME_NOT_ALLOWED"
    CREDENTIALS_NOT_ALLOWED = "CREDENTIALS_NOT_ALLOWED"
    PORT_NOT_ALLOWED = "PORT_NOT_ALLOWED"
    HOST_NOT_ALLOWED = "HOST_NOT_ALLOWED"
    REDIRECT_LIMIT_EXCEEDED = "REDIRECT_LIMIT_EXCEEDED"
    DNS_RESOLUTION_FAILED = "DNS_RESOLUTION_FAILED"
    ADDRESS_NOT_PUBLIC = "ADDRESS_NOT_PUBLIC"


class UrlPolicyError(ValueError):
    def __init__(
        self,
        code: UrlPolicyErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class HostResolver(Protocol):
    async def resolve(self, host: str, port: int) -> tuple[IpAddress, ...]: ...


class SystemHostResolver:
    async def resolve(self, host: str, port: int) -> tuple[IpAddress, ...]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        addresses = {
            ipaddress.ip_address(record[4][0])
            for record in records
        }
        return tuple(sorted(addresses, key=_address_sort_key))


@dataclass(frozen=True, slots=True)
class ValidatedUrl:
    original_url: str
    canonical_url: str
    host: str
    port: int
    resolved_addresses: tuple[IpAddress, ...]
    redirect_count: int


class UrlPolicy:
    def __init__(
        self,
        resolver: HostResolver,
        *,
        max_url_length: int = 2_048,
        max_redirects: int = 5,
    ) -> None:
        if max_url_length < 256 or max_url_length > 16_384:
            raise ValueError("max_url_length must be 256..16384")
        if max_redirects < 0 or max_redirects > 10:
            raise ValueError("max_redirects must be 0..10")
        self._resolver = resolver
        self._max_url_length = max_url_length
        self._max_redirects = max_redirects

    async def validate(
        self,
        url: str,
        *,
        redirect_count: int = 0,
    ) -> ValidatedUrl:
        if not isinstance(url, str):
            raise UrlPolicyError(
                UrlPolicyErrorCode.INVALID_URL,
                "source URL must be a string",
            )
        if len(url) > self._max_url_length:
            raise UrlPolicyError(
                UrlPolicyErrorCode.URL_TOO_LONG,
                "source URL exceeds the configured length limit",
            )
        if not url or url != url.strip() or _contains_control_character(url):
            raise UrlPolicyError(
                UrlPolicyErrorCode.INVALID_URL,
                "source URL contains invalid whitespace or control characters",
            )
        if redirect_count < 0 or redirect_count > self._max_redirects:
            raise UrlPolicyError(
                UrlPolicyErrorCode.REDIRECT_LIMIT_EXCEEDED,
                "source redirect limit exceeded",
            )
        parsed = _parse(url)
        if not parsed.scheme:
            raise UrlPolicyError(
                UrlPolicyErrorCode.INVALID_URL,
                "source URL must be absolute",
            )
        if parsed.scheme.lower() != "https":
            raise UrlPolicyError(
                UrlPolicyErrorCode.SCHEME_NOT_ALLOWED,
                "only HTTPS public sources are allowed",
            )
        if not parsed.netloc or parsed.hostname is None:
            raise UrlPolicyError(
                UrlPolicyErrorCode.INVALID_URL,
                "source URL must contain a hostname",
            )
        if parsed.username is not None or parsed.password is not None:
            raise UrlPolicyError(
                UrlPolicyErrorCode.CREDENTIALS_NOT_ALLOWED,
                "source URL must not contain user information",
            )
        try:
            port = parsed.port or 443
        except ValueError:
            raise UrlPolicyError(
                UrlPolicyErrorCode.INVALID_URL,
                "source URL contains an invalid port",
            ) from None
        if port != 443:
            raise UrlPolicyError(
                UrlPolicyErrorCode.PORT_NOT_ALLOWED,
                "public source URL must use the standard HTTPS port",
            )
        host = _normalize_host(parsed.hostname)
        literal = _ip_literal(host)
        addresses: tuple[IpAddress, ...]
        if literal is not None:
            addresses = (literal,)
        else:
            _reject_internal_hostname(host)
            try:
                addresses = await self._resolver.resolve(host, port)
            except (OSError, UnicodeError):
                raise UrlPolicyError(
                    UrlPolicyErrorCode.DNS_RESOLUTION_FAILED,
                    "source hostname could not be resolved",
                    retryable=True,
                ) from None
        if not addresses:
            raise UrlPolicyError(
                UrlPolicyErrorCode.DNS_RESOLUTION_FAILED,
                "source hostname returned no usable address",
                retryable=True,
            )
        normalized_addresses = tuple(sorted(set(addresses), key=_address_sort_key))
        if any(not _is_public_address(address) for address in normalized_addresses):
            raise UrlPolicyError(
                UrlPolicyErrorCode.ADDRESS_NOT_PUBLIC,
                "source hostname resolves to a non-public address",
            )
        return ValidatedUrl(
            original_url=url,
            canonical_url=_canonical_url(parsed, host),
            host=host,
            port=port,
            resolved_addresses=normalized_addresses,
            redirect_count=redirect_count,
        )


def _parse(url: str) -> SplitResult:
    try:
        return urlsplit(url)
    except ValueError:
        raise UrlPolicyError(
            UrlPolicyErrorCode.INVALID_URL,
            "source URL is malformed",
        ) from None


def _normalize_host(host: str | None) -> str:
    if host is None:
        raise UrlPolicyError(
            UrlPolicyErrorCode.INVALID_URL,
            "source URL must contain a hostname",
        )
    normalized = host.rstrip(".").casefold()
    if not normalized:
        raise UrlPolicyError(
            UrlPolicyErrorCode.INVALID_URL,
            "source hostname is empty",
        )
    try:
        return normalized.encode("idna").decode("ascii")
    except UnicodeError:
        raise UrlPolicyError(
            UrlPolicyErrorCode.INVALID_URL,
            "source hostname is not valid IDNA",
        ) from None


def _ip_literal(host: str) -> IpAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _reject_internal_hostname(host: str) -> None:
    if "." not in host or any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in _NON_PUBLIC_SUFFIXES
    ):
        raise UrlPolicyError(
            UrlPolicyErrorCode.HOST_NOT_ALLOWED,
            "source hostname is not a public DNS name",
        )


def _canonical_url(parsed: SplitResult, host: str) -> str:
    netloc = f"[{host}]" if ":" in host else host
    path = parsed.path or "/"
    return urlunsplit(("https", netloc, path, parsed.query, ""))


def _contains_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _is_public_address(address: IpAddress) -> bool:
    return (
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def _address_sort_key(address: IpAddress) -> tuple[int, int]:
    return address.version, int(address)


_NON_PUBLIC_SUFFIXES = frozenset(
    {
        "example",
        "home.arpa",
        "internal",
        "invalid",
        "local",
        "localhost",
        "test",
    }
)
