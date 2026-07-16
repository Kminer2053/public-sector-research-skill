from __future__ import annotations

import asyncio
import ipaddress
from typing import Any, cast

import pytest

from psr_mcp.collectors.url_policy import (
    HostResolver,
    IpAddress,
    UrlPolicy,
    UrlPolicyError,
    UrlPolicyErrorCode,
    _normalize_host,
)


class Resolver:
    def __init__(
        self,
        records: dict[str, tuple[str, ...]] | None = None,
        *,
        failure: OSError | None = None,
    ) -> None:
        self.records = records or {}
        self.failure = failure
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, host: str, port: int) -> tuple[IpAddress, ...]:
        self.calls.append((host, port))
        if self.failure is not None:
            raise self.failure
        return tuple(ipaddress.ip_address(value) for value in self.records.get(host, ()))


@pytest.mark.anyio
async def test_public_https_url_is_canonicalized_and_resolved() -> None:
    resolver = Resolver({"xn--or3bn7q.go.kr": ("93.184.216.34", "2001:4860:4860::8888")})
    policy = UrlPolicy(resolver)

    result = await policy.validate(
        "https://정부.go.kr./policy?id=1#section",
        redirect_count=2,
    )

    assert result.canonical_url == "https://xn--or3bn7q.go.kr/policy?id=1"
    assert result.host == "xn--or3bn7q.go.kr"
    assert result.port == 443
    assert [str(address) for address in result.resolved_addresses] == [
        "93.184.216.34",
        "2001:4860:4860::8888",
    ]
    assert result.redirect_count == 2
    assert resolver.calls == [("xn--or3bn7q.go.kr", 443)]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url, code",
    [
        ("http://www.gov.kr", UrlPolicyErrorCode.SCHEME_NOT_ALLOWED),
        ("file:///etc/passwd", UrlPolicyErrorCode.SCHEME_NOT_ALLOWED),
        ("data:text/plain,secret", UrlPolicyErrorCode.SCHEME_NOT_ALLOWED),
        ("www.gov.kr", UrlPolicyErrorCode.INVALID_URL),
        (" https://www.gov.kr", UrlPolicyErrorCode.INVALID_URL),
        ("https://user:secret@www.gov.kr", UrlPolicyErrorCode.CREDENTIALS_NOT_ALLOWED),
        ("https://www.gov.kr:8443", UrlPolicyErrorCode.PORT_NOT_ALLOWED),
        ("https://localhost", UrlPolicyErrorCode.HOST_NOT_ALLOWED),
        ("https://service.internal", UrlPolicyErrorCode.HOST_NOT_ALLOWED),
        ("https://singlelabel", UrlPolicyErrorCode.HOST_NOT_ALLOWED),
    ],
)
async def test_unsafe_url_shapes_are_rejected_before_dns(
    url: str,
    code: UrlPolicyErrorCode,
) -> None:
    resolver = Resolver({"www.gov.kr": ("93.184.216.34",)})

    with pytest.raises(UrlPolicyError) as error:
        await UrlPolicy(resolver).validate(url)

    assert error.value.code is code
    assert resolver.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
async def test_non_public_dns_and_ip_literals_are_blocked(address: str) -> None:
    resolver = Resolver({"source.go.kr": (address,)})
    url = f"https://[{address}]/" if ":" in address else f"https://{address}/"
    policy = UrlPolicy(resolver)

    with pytest.raises(UrlPolicyError) as resolved:
        await policy.validate("https://source.go.kr/document")
    assert resolved.value.code is UrlPolicyErrorCode.ADDRESS_NOT_PUBLIC

    with pytest.raises(UrlPolicyError) as literal:
        await policy.validate(url)
    assert literal.value.code is UrlPolicyErrorCode.ADDRESS_NOT_PUBLIC


@pytest.mark.anyio
async def test_mixed_public_and_private_dns_answer_is_rejected() -> None:
    resolver = Resolver({"source.go.kr": ("93.184.216.34", "127.0.0.1")})

    with pytest.raises(UrlPolicyError) as error:
        await UrlPolicy(resolver).validate("https://source.go.kr")

    assert error.value.code is UrlPolicyErrorCode.ADDRESS_NOT_PUBLIC


@pytest.mark.anyio
async def test_dns_failure_empty_answer_redirect_and_length_limits_are_typed() -> None:
    with pytest.raises(UrlPolicyError) as failed:
        await UrlPolicy(Resolver(failure=OSError("dns down"))).validate(
            "https://source.go.kr"
        )
    assert failed.value.code is UrlPolicyErrorCode.DNS_RESOLUTION_FAILED
    assert failed.value.retryable is True

    with pytest.raises(UrlPolicyError) as empty:
        await UrlPolicy(Resolver()).validate("https://source.go.kr")
    assert empty.value.code is UrlPolicyErrorCode.DNS_RESOLUTION_FAILED

    with pytest.raises(UrlPolicyError) as redirected:
        await UrlPolicy(Resolver(), max_redirects=1).validate(
            "https://source.go.kr",
            redirect_count=2,
        )
    assert redirected.value.code is UrlPolicyErrorCode.REDIRECT_LIMIT_EXCEEDED

    with pytest.raises(UrlPolicyError) as too_long:
        await UrlPolicy(Resolver(), max_url_length=256).validate(
            "https://source.go.kr/" + ("a" * 300)
        )
    assert too_long.value.code is UrlPolicyErrorCode.URL_TOO_LONG


def test_url_policy_configuration_is_bounded() -> None:
    resolver: HostResolver = Resolver()

    with pytest.raises(ValueError, match="max_url_length"):
        UrlPolicy(resolver, max_url_length=255)
    with pytest.raises(ValueError, match="max_redirects"):
        UrlPolicy(resolver, max_redirects=11)


@pytest.mark.anyio
async def test_url_policy_rejects_non_string_bad_port_and_malformed_ipv6() -> None:
    policy = UrlPolicy(Resolver())

    with pytest.raises(UrlPolicyError) as non_string:
        await policy.validate(cast(Any, 123))
    assert non_string.value.code is UrlPolicyErrorCode.INVALID_URL

    with pytest.raises(UrlPolicyError) as bad_port:
        await policy.validate("https://source.go.kr:not-a-port")
    assert bad_port.value.code is UrlPolicyErrorCode.INVALID_URL

    with pytest.raises(UrlPolicyError) as malformed:
        await policy.validate("https://[::1")
    assert malformed.value.code is UrlPolicyErrorCode.INVALID_URL

    with pytest.raises(UrlPolicyError) as missing_host:
        await policy.validate("https:///document")
    assert missing_host.value.code is UrlPolicyErrorCode.INVALID_URL


@pytest.mark.parametrize("host", [None, ".", "\ud800"])
def test_host_normalization_rejects_impossible_or_invalid_values(host: str | None) -> None:
    with pytest.raises(UrlPolicyError) as error:
        _normalize_host(host)

    assert error.value.code is UrlPolicyErrorCode.INVALID_URL


@pytest.mark.anyio
async def test_system_resolver_normalizes_and_deduplicates_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from psr_mcp.collectors.url_policy import SystemHostResolver

    class Loop:
        async def getaddrinfo(
            self,
            host: str,
            port: int,
            **kwargs: object,
        ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            del host, port, kwargs
            return [
                (2, 1, 6, "", ("93.184.216.34", 443)),
                (2, 1, 6, "", ("93.184.216.34", 443)),
                (10, 1, 6, "", ("2001:4860:4860::8888", 443)),
            ]

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: Loop())

    addresses = await SystemHostResolver().resolve("source.go.kr", 443)

    assert [str(address) for address in addresses] == [
        "93.184.216.34",
        "2001:4860:4860::8888",
    ]
