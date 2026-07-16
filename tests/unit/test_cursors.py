from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from psr_mcp.application.cursors import HmacCursorCodec
from psr_mcp.domain.errors import DomainError

SECRET = b"cursor-negative-test-signing-key-32-bytes"


def _signed(payload: object) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(SECRET, raw, hashlib.sha256).digest()
    encoded_payload = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{encoded_payload}.{encoded_signature}"


def test_cursor_rejects_short_secret_and_oversized_or_malformed_input() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        HmacCursorCodec(b"short")

    codec = HmacCursorCodec(SECRET)
    with pytest.raises(DomainError, match="too long"):
        codec.decode("x" * 1_025)
    with pytest.raises(DomainError, match="malformed"):
        codec.decode("not-a-signed-cursor")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"v": 2, "after_created_at": "2026-07-16T00:00:00Z", "after_id": "project-a"},
        {"v": 1, "after_created_at": 123, "after_id": "project-a"},
    ],
)
def test_cursor_rejects_signed_but_invalid_payload(payload: object) -> None:
    with pytest.raises(DomainError, match="payload is invalid"):
        HmacCursorCodec(SECRET).decode(_signed(payload))
