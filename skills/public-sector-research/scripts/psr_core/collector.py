"""Bounded, policy-aware collection for public official sources and local files."""

from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)
from urllib.robotparser import RobotFileParser

from psr_core.models import CollectedDocument

USER_AGENT = "PublicSectorResearchAgent/0.1"


class CollectionError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def collect(
    locator: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    respect_robots: bool = True,
) -> CollectedDocument:
    path = Path(locator).expanduser()
    if "://" not in locator:
        return collect_file(path, max_bytes=max_bytes)
    return collect_url(
        locator,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
        respect_robots=respect_robots,
    )


def collect_file(path: Path, *, max_bytes: int) -> CollectedDocument:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise CollectionError("FILE_NOT_FOUND", f"local source is not a file: {resolved}")
    size = resolved.stat().st_size
    if size > max_bytes:
        raise CollectionError("RESPONSE_TOO_LARGE", "local source exceeds byte limit")
    body = resolved.read_bytes()
    media_type, _ = mimetypes.guess_type(str(resolved))
    return CollectedDocument(
        requested_locator=str(resolved),
        final_locator=str(resolved),
        status=200,
        headers={},
        media_type=media_type,
        body=body,
        sha256=hashlib.sha256(body).hexdigest(),
        retrieved_at=_utc_now(),
        warnings=[],
    )


def collect_url(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    respect_robots: bool = True,
    retries: int = 2,
) -> CollectedDocument:
    canonical = validate_public_url(url)
    warnings: List[str] = []
    if respect_robots:
        robots = _robots_allowed(canonical, timeout_seconds=min(timeout_seconds, 10.0))
        if robots is False:
            raise CollectionError("ROBOTS_DISALLOWED", "robots.txt disallows this source")
        if robots is None:
            warnings.append("robots.txt could not be confirmed; collection proceeded")
    opener = build_opener(_SafeRedirectHandler())
    request = Request(
        canonical,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/pdf,application/json,text/plain;q=0.9,*/*;q=0.5",
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    last_error: Optional[CollectionError] = None
    for attempt in range(retries + 1):
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                final_url = validate_public_url(response.geturl())
                status = int(getattr(response, "status", 200))
                headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
                length = headers.get("content-length")
                if length and int(length) > max_bytes:
                    raise CollectionError(
                        "RESPONSE_TOO_LARGE",
                        "source content-length exceeds byte limit",
                    )
                body = _read_bounded(response, max_bytes)
                media_type = headers.get("content-type")
                return CollectedDocument(
                    requested_locator=canonical,
                    final_locator=final_url,
                    status=status,
                    headers=_safe_headers(headers),
                    media_type=media_type,
                    body=body,
                    sha256=hashlib.sha256(body).hexdigest(),
                    retrieved_at=_utc_now(),
                    warnings=warnings,
                )
        except HTTPError as error:
            retryable = error.code in {408, 425, 429, 500, 502, 503, 504}
            last_error = CollectionError(
                f"HTTP_{error.code}",
                f"source returned HTTP {error.code}",
                retryable=retryable,
            )
        except (URLError, TimeoutError, socket.timeout) as error:
            last_error = CollectionError(
                "NETWORK_ERROR",
                f"source request failed: {error}",
                retryable=True,
            )
        except ValueError as error:
            last_error = CollectionError("INVALID_RESPONSE", str(error), retryable=False)
        if last_error and last_error.retryable and attempt < retries:
            time.sleep(0.25 * (2**attempt))
            continue
        if last_error:
            raise last_error
    raise CollectionError("NETWORK_ERROR", "source request failed", retryable=True)


def validate_public_url(url: str) -> str:
    canonical = canonicalize_url(url)
    parsed = urlsplit(canonical)
    host = parsed.hostname or ""
    _assert_public_host(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    return canonical


def canonicalize_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise CollectionError("INVALID_URL", "source URL is invalid") from error
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise CollectionError("INVALID_SCHEME", "only http and https sources are allowed")
    if parsed.username or parsed.password:
        raise CollectionError("USERINFO_FORBIDDEN", "URL userinfo is not allowed")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise CollectionError("HOST_REQUIRED", "source URL requires a host")
    if host == "localhost" or host.endswith(".localhost"):
        raise CollectionError("PRIVATE_ADDRESS", "localhost sources are not allowed")
    try:
        port = parsed.port
    except ValueError as error:
        raise CollectionError("INVALID_PORT", "source URL port is invalid") from error
    if port is not None and port not in {80, 443}:
        raise CollectionError("NONSTANDARD_PORT", "only ports 80 and 443 are allowed")
    netloc_host = f"[{host}]" if ":" in host else host
    netloc = netloc_host
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{netloc_host}:{port}"
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


class _SafeRedirectHandler(HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Optional[Request]:
        target = validate_public_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, target)


def _assert_public_host(host: str, port: int) -> None:
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise CollectionError(
                "DNS_FAILED",
                f"could not resolve source host: {host}",
                True,
            ) from error
        addresses = []
        for record in records:
            try:
                addresses.append(ipaddress.ip_address(record[4][0]))
            except ValueError:
                continue
    if not addresses:
        raise CollectionError("DNS_FAILED", f"source host has no usable address: {host}", True)
    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise CollectionError("PRIVATE_ADDRESS", "source resolves to a non-public address")


def _robots_allowed(url: str, *, timeout_seconds: float) -> Optional[bool]:
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    parser = RobotFileParser()
    parser.set_url(robots_url)
    request = Request(
        robots_url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
    )
    try:
        opener = build_opener(_SafeRedirectHandler())
        with opener.open(request, timeout=timeout_seconds) as response:
            body = _read_bounded(response, 512 * 1024)
    except HTTPError as error:
        if error.code == 404:
            return True
        return None
    except (URLError, TimeoutError, socket.timeout, CollectionError):
        return None
    parser.parse(body.decode("utf-8", errors="replace").splitlines())
    return parser.can_fetch(USER_AGENT, url)


def _read_bounded(response: object, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise CollectionError("RESPONSE_TOO_LARGE", "source exceeds byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_headers(headers: Dict[str, str]) -> Dict[str, str]:
    allowed = {
        "content-type",
        "content-length",
        "etag",
        "last-modified",
        "content-language",
        "date",
    }
    return {key: value for key, value in headers.items() if key in allowed}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )
