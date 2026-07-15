"""Central authorization policy for application services and MCP resources."""

from __future__ import annotations

from collections.abc import Collection

from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.domain.identity import Role
from psr_mcp.domain.projects import Project

PROJECT_READ_ROLES = frozenset(
    {Role.RESEARCHER, Role.RESEARCH_MANAGER, Role.REVIEWER, Role.ORGANIZATION_ADMIN}
)
RESEARCH_RUN_ROLES = frozenset({Role.RESEARCHER, Role.RESEARCH_MANAGER, Role.ORGANIZATION_ADMIN})


class AuthorizationPolicy:
    def require_scope(self, auth: AuthorizationContext, scope: str) -> None:
        if scope not in auth.scopes:
            raise DomainError(
                ErrorCode.AUTH_SCOPE_REQUIRED,
                f"required scope is missing: {scope}",
                details={"scope": scope},
            )

    def require_roles(self, auth: AuthorizationContext, allowed_roles: Collection[Role]) -> None:
        if not auth.roles.intersection(allowed_roles):
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the requested target was not found or is not accessible",
            )

    def require_project(
        self,
        auth: AuthorizationContext,
        project: Project | None,
        *,
        scope: str,
        allowed_roles: Collection[Role],
    ) -> Project:
        self.require_scope(auth, scope)
        if (
            project is None
            or project.organization_id != auth.organization_id
            or (auth.project_ids is not None and project.id not in auth.project_ids)
            or not auth.roles.intersection(allowed_roles)
        ):
            raise DomainError(
                ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                "the requested target was not found or is not accessible",
            )
        return project
