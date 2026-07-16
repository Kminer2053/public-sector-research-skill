from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from psr_mcp.public.feedback import (
    ContentFreeFeedbackService,
    FeedbackDigestSweeper,
    FeedbackErrorCode,
    FeedbackSubmissionError,
    FeedbackTokenCodec,
    derive_feedback_signing_key,
)

SIGNING_KEY = b"feedback-test-signing-key-32-bytes"


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 16, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value


def _service(clock: MutableClock) -> ContentFreeFeedbackService:
    return ContentFreeFeedbackService(
        codec=FeedbackTokenCodec(
            signing_key=SIGNING_KEY,
            clock=clock,
            ttl_seconds=300,
        ),
        clock=clock,
    )


def _payload(token: str) -> dict[str, object]:
    body = token.split(".", 1)[0]
    padding = "=" * (-len(body) % 4)
    decoded = base64.urlsafe_b64decode(body + padding)
    value = json.loads(decoded)
    assert isinstance(value, dict)
    return value


def _signed_token(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    body = base64.urlsafe_b64encode(encoded).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(hmac.digest(SIGNING_KEY, body.encode(), "sha256")).rstrip(
        b"="
    )
    return f"{body}.{signature.decode()}"


def test_feedback_token_contains_no_run_question_or_user_identifier() -> None:
    clock = MutableClock()
    issued = _service(clock).issue()

    assert set(_payload(issued.value)) == {"exp", "nonce", "v"}
    assert issued.expires_at == clock.value + timedelta(seconds=300)
    assert "question" not in issued.value
    assert "operation" not in issued.value
    assert "user" not in issued.value


def test_feedback_submission_is_one_time_and_logs_no_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = MutableClock()
    service = _service(clock)
    issued = service.issue()

    with caplog.at_level(logging.INFO):
        service.submit(
            token=issued.value,
            helpful=True,
            save_feature_interest=False,
        )
    with pytest.raises(FeedbackSubmissionError) as replay:
        service.submit(
            token=issued.value,
            helpful=False,
            save_feature_interest=True,
        )

    snapshot = service.snapshot()
    assert replay.value.code is FeedbackErrorCode.INVALID_OR_USED
    assert snapshot.submitted == 1
    assert snapshot.helpful_true == 1
    assert snapshot.save_feature_interest_true == 0
    assert issued.value not in caplog.text
    assert "submitted=1" in caplog.text
    assert "helpful_true=1" in caplog.text
    assert "save_feature_interest_true=0" in caplog.text


@pytest.mark.parametrize(
    "mutator",
    [
        lambda token: token + "tampered",
        lambda token: token + ".extra-segment",
        lambda token: token.split(".", 1)[0],
        lambda token: "not-base64.invalid-signature",
    ],
)
def test_feedback_token_rejects_malformed_or_tampered_value(
    mutator: Callable[[str], str],
) -> None:
    clock = MutableClock()
    service = _service(clock)
    token = service.issue().value

    with pytest.raises(FeedbackSubmissionError) as invalid:
        service.submit(
            token=mutator(token),
            helpful=True,
            save_feature_interest=True,
        )

    assert invalid.value.code is FeedbackErrorCode.INVALID_OR_USED
    assert service.snapshot().submitted == 0


def test_feedback_token_rejects_valid_signature_with_invalid_payload() -> None:
    clock = MutableClock()
    codec = FeedbackTokenCodec(
        signing_key=SIGNING_KEY,
        clock=clock,
        ttl_seconds=300,
    )
    invalid_payload = _signed_token(
        {
            "exp": int((clock.value + timedelta(seconds=300)).timestamp()),
            "v": 1,
        }
    )

    with pytest.raises(FeedbackSubmissionError) as invalid:
        codec.validate(invalid_payload)

    assert invalid.value.code is FeedbackErrorCode.INVALID_OR_USED


def test_feedback_token_expiry_and_consumed_digest_cleanup() -> None:
    clock = MutableClock()
    service = _service(clock)
    first = service.issue()
    service.submit(
        token=first.value,
        helpful=False,
        save_feature_interest=True,
    )
    clock.value += timedelta(seconds=301)

    with pytest.raises(FeedbackSubmissionError):
        service.submit(
            token=first.value,
            helpful=True,
            save_feature_interest=True,
        )
    second = service.issue()
    service.submit(
        token=second.value,
        helpful=True,
        save_feature_interest=True,
    )

    snapshot = service.snapshot()
    assert snapshot.submitted == 2
    assert snapshot.helpful_true == 1
    assert snapshot.save_feature_interest_true == 2


@pytest.mark.anyio
async def test_feedback_digest_sweeper_removes_expired_digests_and_is_idempotent() -> None:
    clock = MutableClock()
    service = _service(clock)
    issued = service.issue()
    service.submit(
        token=issued.value,
        helpful=True,
        save_feature_interest=True,
    )
    sweeper = FeedbackDigestSweeper(service, interval_seconds=1)

    assert await sweeper.start() == 0
    assert await sweeper.start() == 0
    clock.value += timedelta(seconds=301)
    assert sweeper.run_once() == 1
    assert sweeper.run_once() == 0
    await sweeper.stop()
    await sweeper.stop()


@pytest.mark.anyio
async def test_feedback_digest_sweeper_background_loop() -> None:
    clock = MutableClock()
    service = _service(clock)
    issued = service.issue()
    service.submit(
        token=issued.value,
        helpful=True,
        save_feature_interest=False,
    )
    sweeper = FeedbackDigestSweeper(service, interval_seconds=1)
    await sweeper.start()
    clock.value += timedelta(seconds=301)

    await asyncio.sleep(1.05)
    await sweeper.stop()

    assert service.purge_expired() == 0


def test_feedback_key_and_clock_guards() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        FeedbackTokenCodec(
            signing_key=b"short",
            clock=MutableClock(),
            ttl_seconds=300,
        )
    with pytest.raises(ValueError, match=r"300\.\.604800"):
        FeedbackTokenCodec(
            signing_key=SIGNING_KEY,
            clock=MutableClock(),
            ttl_seconds=299,
        )
    with pytest.raises(ValueError, match="32 bytes"):
        derive_feedback_signing_key(b"short")
    with pytest.raises(ValueError, match="at least 1 second"):
        FeedbackDigestSweeper(_service(MutableClock()), interval_seconds=0)

    class NaiveClock:
        def now(self) -> datetime:
            return datetime(2026, 7, 16)

    codec = FeedbackTokenCodec(
        signing_key=SIGNING_KEY,
        clock=NaiveClock(),
        ttl_seconds=300,
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        codec.issue()


def test_feedback_key_derivation_is_stable_and_domain_separated() -> None:
    abuse_key = b"public-abuse-hmac-key-at-least-32-bytes"

    first = derive_feedback_signing_key(abuse_key)
    second = derive_feedback_signing_key(abuse_key)

    assert first == second
    assert first != abuse_key
    assert len(first) == 32
