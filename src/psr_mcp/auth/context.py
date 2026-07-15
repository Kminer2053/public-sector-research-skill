"""Verified request context used by application services."""

from __future__ import annotations

from dataclasses import dataclass

from psr_mcp.domain.identity import ActorType, Role
from psr_mcp.domain.validation import require_text


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    organization_id: str
    subject_id: str
    roles: frozenset[Role]
    scopes: frozenset[str]
    project_ids: frozenset[str] | None
    actor_type: ActorType = ActorType.HUMAN
    token_id: str | None = None
    client_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "organization_id",
            require_text(self.organization_id, "organization_id", maximum=128),
        )
        object.__setattr__(
            self, "subject_id", require_text(self.subject_id, "subject_id", maximum=128)
        )
        object.__setattr__(
            self,
            "scopes",
            frozenset(require_text(scope, "scope", maximum=128) for scope in self.scopes),
        )
        if self.project_ids is not None:
            object.__setattr__(
                self,
                "project_ids",
                frozenset(
                    require_text(value, "project_id", maximum=128) for value in self.project_ids
                ),
            )

    @property
    def is_human(self) -> bool:
        return self.actor_type is ActorType.HUMAN
