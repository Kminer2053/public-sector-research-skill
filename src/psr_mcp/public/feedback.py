"""Content-free anonymous feedback token and aggregation service."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from typing import Protocol

from psr_mcp.application.ports import Clock

logger = logging.getLogger(__name__)


class FeedbackErrorCode(StrEnum):
    INVALID_OR_USED = "FEEDBACK_TOKEN_INVALID_OR_USED"


class FeedbackSubmissionError(Exception):
    def __init__(self, code: FeedbackErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False


@dataclass(frozen=True, slots=True)
class IssuedFeedbackToken:
    value: str
    expires_at: datetime


class FeedbackIssuer(Protocol):
    def issue(self) -> IssuedFeedbackToken: ...


@dataclass(frozen=True, slots=True)
class FeedbackMetricsSnapshot:
    submitted: int
    helpful_true: int
    save_feature_interest_true: int


class FeedbackTokenCodec:
    def __init__(
        self,
        *,
        signing_key: bytes,
        clock: Clock,
        ttl_seconds: int,
    ) -> None:
        if len(signing_key) < 32:
            raise ValueError("feedback signing key must contain at least 32 bytes")
        if ttl_seconds < 300 or ttl_seconds > 604_800:
            raise ValueError("feedback token TTL must be 300..604800 seconds")
        self._signing_key = signing_key
        self._clock = clock
        self._ttl_seconds = ttl_seconds

    def issue(self) -> IssuedFeedbackToken:
        expires_timestamp = int(
            (_utc(self._clock.now()) + timedelta(seconds=self._ttl_seconds)).timestamp()
        )
        expires_at = datetime.fromtimestamp(expires_timestamp, tz=UTC)
        payload = {
            "exp": expires_timestamp,
            "nonce": secrets.token_urlsafe(24),
            "v": 1,
        }
        body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = _encode(hmac.digest(self._signing_key, body.encode(), "sha256"))
        return IssuedFeedbackToken(value=f"{body}.{signature}", expires_at=expires_at)

    def validate(self, token: str) -> datetime:
        try:
            body, supplied_signature = token.split(".", 1)
            if "." in supplied_signature:
                raise ValueError("too many token segments")
            expected_signature = _encode(hmac.digest(self._signing_key, body.encode(), "sha256"))
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise ValueError("invalid signature")
            payload = json.loads(_decode(body))
            if (
                not isinstance(payload, dict)
                or set(payload) != {"exp", "nonce", "v"}
                or payload["v"] != 1
                or not isinstance(payload["exp"], int)
                or not isinstance(payload["nonce"], str)
                or len(payload["nonce"]) < 24
            ):
                raise ValueError("invalid token payload")
            expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
            if _utc(self._clock.now()) >= expires_at:
                raise ValueError("expired token")
            return expires_at
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise FeedbackSubmissionError(
                FeedbackErrorCode.INVALID_OR_USED,
                "feedback token is invalid, expired, or already used",
            ) from None


class ContentFreeFeedbackService:
    def __init__(self, *, codec: FeedbackTokenCodec, clock: Clock) -> None:
        self._codec = codec
        self._clock = clock
        self._consumed: dict[bytes, datetime] = {}
        self._submitted = 0
        self._helpful_true = 0
        self._save_feature_interest_true = 0
        self._lock = Lock()

    def issue(self) -> IssuedFeedbackToken:
        return self._codec.issue()

    def submit(
        self,
        *,
        token: str,
        helpful: bool,
        save_feature_interest: bool,
    ) -> None:
        expires_at = self._codec.validate(token)
        token_digest = hashlib.sha256(token.encode()).digest()
        now = _utc(self._clock.now())
        with self._lock:
            self._purge_expired(now)
            if token_digest in self._consumed:
                raise FeedbackSubmissionError(
                    FeedbackErrorCode.INVALID_OR_USED,
                    "feedback token is invalid, expired, or already used",
                )
            self._consumed[token_digest] = expires_at
            self._submitted += 1
            self._helpful_true += int(helpful)
            self._save_feature_interest_true += int(save_feature_interest)
            submitted = self._submitted
            helpful_true = self._helpful_true
            save_feature_interest_true = self._save_feature_interest_true
        logger.info(
            "public_feedback_aggregate submitted=%s helpful_true=%s save_feature_interest_true=%s",
            submitted,
            helpful_true,
            save_feature_interest_true,
        )

    def snapshot(self) -> FeedbackMetricsSnapshot:
        with self._lock:
            return FeedbackMetricsSnapshot(
                submitted=self._submitted,
                helpful_true=self._helpful_true,
                save_feature_interest_true=self._save_feature_interest_true,
            )

    def purge_expired(self) -> int:
        now = _utc(self._clock.now())
        with self._lock:
            return self._purge_expired(now)

    def _purge_expired(self, now: datetime) -> int:
        expired = [digest for digest, expires_at in self._consumed.items() if now >= expires_at]
        for digest in expired:
            del self._consumed[digest]
        return len(expired)


class FeedbackDigestSweeper:
    def __init__(
        self,
        service: ContentFreeFeedbackService,
        *,
        interval_seconds: int,
    ) -> None:
        if interval_seconds < 1:
            raise ValueError("feedback sweep interval must be at least 1 second")
        self._service = service
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> int:
        purged = self.run_once()
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="psr-feedback-digest-purge")
        return purged

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        self.run_once()

    def run_once(self) -> int:
        purged = self._service.purge_expired()
        if purged:
            logger.info("public_feedback_expired_digests_purged count=%s", purged)
        return purged

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            self.run_once()


def derive_feedback_signing_key(abuse_hmac_key: bytes) -> bytes:
    if len(abuse_hmac_key) < 32:
        raise ValueError("public abuse HMAC key must contain at least 32 bytes")
    return hmac.digest(abuse_hmac_key, b"psr-public-feedback-v1", "sha256")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("feedback timestamps must be timezone-aware")
    return value.astimezone(UTC)
