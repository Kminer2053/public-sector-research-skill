from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError

import psr_core.collector as collector
import pytest
from psr_core.collector import (
    CollectionError,
    canonicalize_url,
    collect_file,
    validate_public_url,
)


def test_canonicalize_url_removes_fragment_and_default_port() -> None:
    assert (
        canonicalize_url("HTTPS://Example.COM:443/path?q=1#fragment")
        == "https://example.com/path?q=1"
    )


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("file:///etc/passwd", "INVALID_SCHEME"),
        ("https://user:password@example.com/", "USERINFO_FORBIDDEN"),
        ("https://example.com:8443/", "NONSTANDARD_PORT"),
        ("https://localhost/", "PRIVATE_ADDRESS"),
        ("http://127.0.0.1/", "PRIVATE_ADDRESS"),
        ("http://169.254.169.254/", "PRIVATE_ADDRESS"),
        ("http://10.0.0.1/", "PRIVATE_ADDRESS"),
    ],
)
def test_public_url_policy_blocks_unsafe_targets(url: str, code: str) -> None:
    with pytest.raises(CollectionError) as captured:
        validate_public_url(url)

    assert captured.value.code == code


def test_public_literal_ip_is_allowed_without_dns() -> None:
    assert validate_public_url("https://8.8.8.8/example") == "https://8.8.8.8/example"


def test_collect_file_records_hash_and_media_type(tmp_path: Path) -> None:
    source = tmp_path / "guide.json"
    source.write_text('{"title":"guide"}', encoding="utf-8")

    collected = collect_file(source, max_bytes=10_000)

    assert collected.status == 200
    assert collected.media_type == "application/json"
    assert len(collected.sha256) == 64
    assert collected.final_locator == str(source.resolve())


def test_collect_file_enforces_byte_limit(tmp_path: Path) -> None:
    source = tmp_path / "large.txt"
    source.write_text("x" * 100, encoding="utf-8")

    with pytest.raises(CollectionError) as captured:
        collect_file(source, max_bytes=10)

    assert captured.value.code == "RESPONSE_TOO_LARGE"


class _FakeResponse:
    def __init__(
        self,
        *,
        body: bytes,
        status: int = 200,
        headers: dict[str, str] | None = None,
        url: str = "https://8.8.8.8/document",
    ) -> None:
        self._body = body
        self._offset = 0
        self.status = status
        self.headers = headers or {"Content-Type": "text/plain", "Secret": "discard"}
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, size: int) -> bytes:
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class _FakeOpener:
    def __init__(self, responses):
        self._responses = iter(responses)

    def open(self, request, timeout):
        value = next(self._responses)
        if isinstance(value, Exception):
            raise value
        return value


def test_collect_url_success_filters_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(
        body=b"official evidence",
        headers={
            "Content-Type": "text/plain",
            "ETag": "abc",
            "Set-Cookie": "secret",
        },
    )
    monkeypatch.setattr(collector, "build_opener", lambda *args: _FakeOpener([response]))

    result = collector.collect_url(
        "https://8.8.8.8/document",
        max_bytes=1_000,
        timeout_seconds=1,
        respect_robots=False,
    )

    assert result.body == b"official evidence"
    assert result.headers == {"content-type": "text/plain", "etag": "abc"}
    assert result.status == 200


def test_collect_url_retries_retryable_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = HTTPError(
        "https://8.8.8.8/document",
        503,
        "unavailable",
        {},
        None,
    )
    response = _FakeResponse(body=b"recovered")
    opener = _FakeOpener([error, response])
    monkeypatch.setattr(collector, "build_opener", lambda *args: opener)
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)

    result = collector.collect_url(
        "https://8.8.8.8/document",
        max_bytes=1_000,
        timeout_seconds=1,
        respect_robots=False,
    )

    assert result.body == b"recovered"


def test_collect_url_rejects_declared_large_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(
        body=b"x",
        headers={"Content-Length": "1000"},
    )
    monkeypatch.setattr(collector, "build_opener", lambda *args: _FakeOpener([response]))

    with pytest.raises(CollectionError) as captured:
        collector.collect_url(
            "https://8.8.8.8/document",
            max_bytes=10,
            timeout_seconds=1,
            respect_robots=False,
            retries=0,
        )

    assert captured.value.code == "RESPONSE_TOO_LARGE"


def test_collect_url_reports_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from urllib.error import URLError

    monkeypatch.setattr(
        collector,
        "build_opener",
        lambda *args: _FakeOpener([URLError("offline")]),
    )

    with pytest.raises(CollectionError) as captured:
        collector.collect_url(
            "https://8.8.8.8/document",
            max_bytes=10,
            timeout_seconds=1,
            respect_robots=False,
            retries=0,
        )

    assert captured.value.code == "NETWORK_ERROR"
