"""Project aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from psr_mcp.domain.validation import require_text, require_utc, require_version


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    organization_id: str
    name: str
    profile: str
    status: ProjectStatus
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_text(self.id, "project_id", maximum=128))
        object.__setattr__(
            self,
            "organization_id",
            require_text(self.organization_id, "organization_id", maximum=128),
        )
        object.__setattr__(self, "name", require_text(self.name, "project_name"))
        object.__setattr__(self, "profile", require_text(self.profile, "profile", maximum=64))
        require_version(self.version)
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
