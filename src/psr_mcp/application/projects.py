"""Tenant-aware Project queries."""

from __future__ import annotations

from dataclasses import dataclass

from psr_mcp.application.ports import CursorCodec, IdGenerator, UnitOfWorkFactory
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.auth.policy import PROJECT_READ_ROLES, AuthorizationPolicy
from psr_mcp.domain.errors import invalid
from psr_mcp.domain.projects import Project


@dataclass(frozen=True, slots=True)
class ProjectPage:
    items: tuple[Project, ...]
    next_cursor: str | None
    operation_id: str


@dataclass(frozen=True, slots=True)
class ProjectResult:
    project: Project
    operation_id: str


class ProjectService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        policy: AuthorizationPolicy,
        cursor_codec: CursorCodec,
        ids: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy
        self._cursor_codec = cursor_codec
        self._ids = ids

    async def list_projects(
        self,
        auth: AuthorizationContext,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ProjectPage:
        self._policy.require_scope(auth, "project:read")
        self._policy.require_roles(auth, PROJECT_READ_ROLES)
        if limit < 1 or limit > 100:
            raise invalid("limit must be 1..100", field="limit")
        after = self._cursor_codec.decode(cursor) if cursor else None
        async with self._uow_factory() as uow:
            projects = await uow.projects.list_page(
                auth.organization_id,
                project_ids=auth.project_ids,
                after=after,
                limit=limit + 1,
            )
        has_more = len(projects) > limit
        page = projects[:limit]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = self._cursor_codec.encode((last.created_at, last.id))
        return ProjectPage(tuple(page), next_cursor, self._ids.new())

    async def get_project(self, auth: AuthorizationContext, project_id: str) -> ProjectResult:
        async with self._uow_factory() as uow:
            candidate = await uow.projects.get(auth.organization_id, project_id)
            project = self._policy.require_project(
                auth,
                candidate,
                scope="project:read",
                allowed_roles=PROJECT_READ_ROLES,
            )
        return ProjectResult(project, self._ids.new())
