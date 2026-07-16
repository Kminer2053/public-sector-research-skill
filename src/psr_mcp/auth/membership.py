"""Internal membership resolution contract for verified external identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from psr_mcp.domain.identity import ActorType, MembershipStatus, Role
from psr_mcp.domain.validation import require_text


@dataclass(frozen=True, slots=True)
class ResolvedMembership:
    organization_id: str
    subject_id: str
    roles: frozenset[Role]
    project_ids: frozenset[str] | None
    actor_type: ActorType
    status: MembershipStatus = MembershipStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "organization_id",
            require_text(self.organization_id, "organization_id", maximum=128),
        )
        object.__setattr__(
            self,
            "subject_id",
            require_text(self.subject_id, "subject_id", maximum=128),
        )
        if not self.roles:
            raise ValueError("resolved membership must have at least one role")
        if self.project_ids is not None:
            object.__setattr__(
                self,
                "project_ids",
                frozenset(
                    require_text(project_id, "project_id", maximum=128)
                    for project_id in self.project_ids
                ),
            )


class MembershipResolver(Protocol):
    async def resolve(
        self,
        *,
        issuer: str,
        external_subject: str,
        requested_organization_id: str,
    ) -> ResolvedMembership | None: ...
