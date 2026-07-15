"""Signed, versioned keyset cursor codec."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from psr_mcp.domain.errors import invalid
from psr_mcp.domain.validation import require_text, require_utc


class HmacCursorCodec:
    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("cursor signing secret must contain at least 32 bytes")
        self._secret = secret

    def encode(self, position: tuple[datetime, str]) -> str:
        created_at, project_id = position
        require_utc(created_at, "created_at")
        project_id = require_text(project_id, "project_id", maximum=128)
        payload = json.dumps(
            {
                "after_created_at": created_at.isoformat().replace("+00:00", "Z"),
                "after_id": project_id,
                "v": 1,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return f"{_b64(payload)}.{_b64(signature)}"

    def decode(self, cursor: str) -> tuple[datetime, str]:
        if len(cursor) > 1_024:
            raise invalid("cursor is too long", field="cursor")
        try:
            payload_part, signature_part = cursor.split(".", maxsplit=1)
            payload = _unb64(payload_part)
            signature = _unb64(signature_part)
        except (ValueError, UnicodeError) as error:
            raise invalid("cursor is malformed", field="cursor") from error
        expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise invalid("cursor signature is invalid", field="cursor")
        try:
            parsed: Any = json.loads(payload)
            if not isinstance(parsed, dict) or parsed.get("v") != 1:
                raise ValueError
            raw_created_at = parsed["after_created_at"]
            raw_project_id = parsed["after_id"]
            if not isinstance(raw_created_at, str) or not isinstance(raw_project_id, str):
                raise ValueError
            created_at = datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise invalid("cursor payload is invalid", field="cursor") from error
        return require_utc(created_at.astimezone(UTC), "created_at"), require_text(
            raw_project_id, "project_id", maximum=128
        )


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
