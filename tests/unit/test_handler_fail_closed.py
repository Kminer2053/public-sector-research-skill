from __future__ import annotations

import logging

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from psr_mcp.application.projects import ProjectService
from psr_mcp.application.research_runs import ResearchRunService
from psr_mcp.auth.context import AuthorizationContext
from psr_mcp.mcp.handlers import McpHandlers


class Ids:
    def new(self) -> str:
        return "handler-operation-id"


class BrokenAuthProvider:
    async def resolve(self) -> AuthorizationContext:
        raise RuntimeError("sensitive-internal-detail")


@pytest.mark.anyio
async def test_unexpected_failure_is_mapped_without_internal_detail(
    project_service: ProjectService,
    run_service: ResearchRunService,
) -> None:
    handlers = McpHandlers(BrokenAuthProvider(), project_service, run_service, Ids())

    with pytest.raises(ToolError) as caught:
        await handlers.project_list(cursor=None, limit=20)
    assert "INTERNAL_ERROR" in str(caught.value)
    assert "sensitive-internal-detail" not in str(caught.value)


@pytest.mark.anyio
async def test_denial_log_contains_operation_code_but_not_target(
    project_service: ProjectService,
    run_service: ResearchRunService,
    auth_a_wide: AuthorizationContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class StaticProvider:
        async def resolve(self) -> AuthorizationContext:
            return auth_a_wide

    handlers = McpHandlers(StaticProvider(), project_service, run_service, Ids())
    with caplog.at_level(logging.WARNING), pytest.raises(ToolError):
        await handlers.project_get(project_id="private-project-b")

    assert "private-project-b" not in caplog.text
    assert caplog.records[-1].error_code == "NOT_FOUND_OR_FORBIDDEN"  # type: ignore[attr-defined]
    assert caplog.records[-1].operation_id == "handler-operation-id"  # type: ignore[attr-defined]
