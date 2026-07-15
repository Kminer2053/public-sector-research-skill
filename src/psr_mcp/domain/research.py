"""Research plan, run, and worker job aggregates."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from psr_mcp.domain.errors import DomainError, ErrorCode, invalid
from psr_mcp.domain.validation import require_text, require_utc, require_version

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_RUN_STATUSES = frozenset(
    {RunStatus.PARTIAL, RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
)

ALLOWED_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.QUEUED,
            RunStatus.PARTIAL,
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.PARTIAL: frozenset(),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    id: str
    organization_id: str
    project_id: str
    version: int
    question: str
    status: PlanStatus
    approved_by: str | None
    approved_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_text(self.id, "plan_id", maximum=128))
        object.__setattr__(
            self,
            "organization_id",
            require_text(self.organization_id, "organization_id", maximum=128),
        )
        object.__setattr__(
            self, "project_id", require_text(self.project_id, "project_id", maximum=128)
        )
        require_version(self.version, "plan_version")
        object.__setattr__(self, "question", require_text(self.question, "question", maximum=4_000))
        if self.status is PlanStatus.APPROVED:
            if self.approved_by is None or self.approved_at is None:
                raise invalid("approved plan requires approver and approval time", field="status")
            object.__setattr__(
                self,
                "approved_by",
                require_text(self.approved_by, "approved_by", maximum=128),
            )
            require_utc(self.approved_at, "approved_at")
        elif self.approved_by is not None or self.approved_at is not None:
            raise invalid("unapproved plan cannot contain approval metadata", field="status")


@dataclass(frozen=True, slots=True)
class ResearchRun:
    id: str
    organization_id: str
    project_id: str
    plan_id: str
    plan_version: int
    initiated_by: str
    status: RunStatus
    version: int
    idempotency_key: str
    request_fingerprint: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failure_code: str | None = None
    cancellation_requested_at: datetime | None = None
    cancel_reason: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("id", "organization_id", "project_id", "plan_id", "initiated_by"):
            object.__setattr__(
                self,
                field_name,
                require_text(getattr(self, field_name), field_name, maximum=128),
            )
        require_version(self.plan_version, "plan_version")
        require_version(self.version)
        if not IDEMPOTENCY_KEY_PATTERN.fullmatch(self.idempotency_key):
            raise invalid(
                "idempotency_key must be 8..128 safe ASCII characters",
                field="idempotency_key",
            )
        if not re.fullmatch(r"[a-f0-9]{64}", self.request_fingerprint):
            raise invalid("request_fingerprint must be SHA-256 hex", field="request_fingerprint")
        for field_name in (
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
            "cancellation_requested_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                require_utc(value, field_name)
        if self.status in TERMINAL_RUN_STATUSES and self.finished_at is None:
            raise invalid("terminal run requires finished_at", field="finished_at")
        if self.cancel_reason is not None:
            object.__setattr__(
                self,
                "cancel_reason",
                require_text(self.cancel_reason, "cancel_reason", minimum=10, maximum=500),
            )

    def transition(
        self,
        target: RunStatus,
        now: datetime,
        *,
        failure_code: str | None = None,
    ) -> ResearchRun:
        require_utc(now, "now")
        if target not in ALLOWED_RUN_TRANSITIONS[self.status]:
            raise DomainError(
                ErrorCode.INVALID_STATE,
                f"run cannot transition from {self.status} to {target}",
                details={"current": self.status, "target": target},
            )
        return replace(
            self,
            status=target,
            version=self.version + 1,
            updated_at=now,
            started_at=now
            if target is RunStatus.RUNNING and self.started_at is None
            else self.started_at,
            finished_at=now if target in TERMINAL_RUN_STATUSES else None,
            failure_code=failure_code,
        )

    def request_cancellation(self, now: datetime, reason: str) -> ResearchRun:
        require_utc(now, "now")
        normalized_reason = require_text(reason, "reason", minimum=10, maximum=500)
        if self.status is RunStatus.QUEUED:
            return replace(
                self.transition(RunStatus.CANCELLED, now),
                cancellation_requested_at=now,
                cancel_reason=normalized_reason,
            )
        if self.status is RunStatus.RUNNING:
            return replace(
                self,
                version=self.version + 1,
                updated_at=now,
                cancellation_requested_at=now,
                cancel_reason=normalized_reason,
            )
        raise DomainError(
            ErrorCode.INVALID_STATE,
            f"run in {self.status} cannot be cancelled",
            details={"current": self.status},
        )


class JobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    organization_id: str
    project_id: str
    run_id: str
    state: JobState
    available_at: datetime
    created_at: datetime
    updated_at: datetime
    attempts: int = 0
    max_attempts: int = 3
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    cancel_requested_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("id", "organization_id", "project_id", "run_id"):
            object.__setattr__(
                self,
                field_name,
                require_text(getattr(self, field_name), field_name, maximum=128),
            )
        for field_name in (
            "available_at",
            "created_at",
            "updated_at",
            "lease_expires_at",
            "cancel_requested_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                require_utc(value, field_name)
        if self.attempts < 0 or self.max_attempts < 1:
            raise invalid("job attempts are invalid", field="attempts")
        if self.state is JobState.RUNNING and (
            self.lease_owner is None or self.lease_expires_at is None
        ):
            raise invalid("running job requires an active lease", field="lease_owner")

    def is_claimable(self, now: datetime) -> bool:
        require_utc(now, "now")
        return self.available_at <= now and (
            self.state is JobState.QUEUED
            or (
                self.state is JobState.RUNNING
                and self.lease_expires_at is not None
                and self.lease_expires_at <= now
            )
        )

    def claim(self, worker_id: str, now: datetime, lease_seconds: int) -> Job:
        worker_id = require_text(worker_id, "worker_id", maximum=128)
        require_utc(now, "now")
        if lease_seconds < 5 or lease_seconds > 3_600:
            raise invalid("lease_seconds must be 5..3600", field="lease_seconds")
        if not self.is_claimable(now):
            raise DomainError(ErrorCode.LEASE_CONFLICT, "job is not claimable", retryable=True)
        if self.attempts >= self.max_attempts:
            raise DomainError(ErrorCode.INVALID_STATE, "job retry attempts are exhausted")
        return replace(
            self,
            state=JobState.RUNNING,
            attempts=self.attempts + 1,
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )

    def heartbeat(self, worker_id: str, now: datetime, extend_seconds: int) -> Job:
        require_utc(now, "now")
        if (
            self.state is not JobState.RUNNING
            or self.lease_owner != worker_id
            or self.lease_expires_at is None
            or self.lease_expires_at <= now
        ):
            raise DomainError(ErrorCode.LEASE_CONFLICT, "worker does not hold an active lease")
        if extend_seconds < 5 or extend_seconds > 3_600:
            raise invalid("extend_seconds must be 5..3600", field="extend_seconds")
        return replace(
            self,
            lease_expires_at=now + timedelta(seconds=extend_seconds),
            updated_at=now,
        )

    def finish(self, worker_id: str, now: datetime, state: JobState) -> Job:
        require_utc(now, "now")
        if state not in {
            JobState.SUCCEEDED,
            JobState.PARTIAL,
            JobState.FAILED,
            JobState.CANCELLED,
        }:
            raise invalid("job finish state must be terminal", field="state")
        if (
            self.state is not JobState.RUNNING
            or self.lease_owner != worker_id
            or self.lease_expires_at is None
            or self.lease_expires_at <= now
        ):
            raise DomainError(ErrorCode.LEASE_CONFLICT, "worker does not hold an active lease")
        return replace(
            self,
            state=state,
            lease_owner=None,
            lease_expires_at=None,
            updated_at=now,
        )
