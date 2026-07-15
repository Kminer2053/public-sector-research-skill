"""Append-only audit values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from psr_mcp.domain.errors import invalid
from psr_mcp.domain.identity import ActorType
from psr_mcp.domain.validation import require_text, require_utc


class AuditOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DENIED = "DENIED"
    FAILED = "FAILED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    organization_id: str
    occurred_at: datetime
    actor_subject_id: str
    actor_type: ActorType
    operation: str
    target_type: str
    outcome: AuditOutcome
    operation_id: str
    project_id: str | None = None
    target_id: str | None = None
    reason_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "id",
            "organization_id",
            "actor_subject_id",
            "operation",
            "target_type",
            "operation_id",
        ):
            object.__setattr__(
                self,
                field_name,
                require_text(getattr(self, field_name), field_name, maximum=128),
            )
        for field_name in ("project_id", "target_id", "reason_code"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, require_text(value, field_name, maximum=128))
        require_utc(self.occurred_at, "occurred_at")
        allowed_metadata = {"plan_version", "run_status", "replayed"}
        if not set(self.metadata).issubset(allowed_metadata):
            raise invalid("audit metadata contains a non-allowlisted key", field="metadata")
