"""Organization and membership values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from psr_mcp.domain.errors import invalid
from psr_mcp.domain.validation import require_text, require_utc


class Role(StrEnum):
    RESEARCHER = "researcher"
    RESEARCH_MANAGER = "research_manager"
    REVIEWER = "reviewer"
    ORGANIZATION_ADMIN = "organization_admin"
    AUDIT_VIEWER = "audit_viewer"


class ActorType(StrEnum):
    HUMAN = "human"
    SERVICE = "service"


class OrganizationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class Organization:
    id: str
    name: str
    status: OrganizationStatus
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_text(self.id, "organization_id", maximum=128))
        object.__setattr__(self, "name", require_text(self.name, "organization_name"))
        require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Membership:
    organization_id: str
    subject_id: str
    roles: frozenset[Role]
    project_ids: frozenset[str] | None
    status: MembershipStatus = MembershipStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "organization_id",
            require_text(self.organization_id, "organization_id", maximum=128),
        )
        object.__setattr__(
            self, "subject_id", require_text(self.subject_id, "subject_id", maximum=128)
        )
        if not self.roles:
            raise invalid("membership must have at least one role", field="roles")
        if self.project_ids is not None:
            normalized = frozenset(
                require_text(value, "project_id", maximum=128) for value in self.project_ids
            )
            object.__setattr__(self, "project_ids", normalized)
