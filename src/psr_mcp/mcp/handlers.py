"""Safe MCP-facing handlers around application services."""

from __future__ import annotations

import logging

from mcp.server.fastmcp.exceptions import ResourceError, ToolError

from psr_mcp.application.ports import IdGenerator
from psr_mcp.application.projects import ProjectService
from psr_mcp.application.research_runs import ResearchRunService
from psr_mcp.auth.providers import AuthContextProvider
from psr_mcp.domain.errors import DomainError, ErrorCode
from psr_mcp.mcp.schemas import (
    ProjectGetOutput,
    ProjectPageOutput,
    ProjectView,
    RunAcceptedOutput,
    RunCancelOutput,
    RunStatusOutput,
    RunView,
    ToolErrorPayload,
)

logger = logging.getLogger(__name__)


class McpHandlers:
    def __init__(
        self,
        auth_provider: AuthContextProvider,
        project_service: ProjectService,
        run_service: ResearchRunService,
        operation_ids: IdGenerator,
    ) -> None:
        self._auth_provider = auth_provider
        self._projects = project_service
        self._runs = run_service
        self._operation_ids = operation_ids

    def _new_operation_id(self) -> str:
        return self._operation_ids.new()

    async def project_list(self, *, cursor: str | None, limit: int) -> ProjectPageOutput:
        try:
            auth = await self._auth_provider.resolve()
            result = await self._projects.list_projects(auth, cursor=cursor, limit=limit)
            return ProjectPageOutput(
                operation_id=result.operation_id,
                items=[ProjectView.from_domain(project) for project in result.items],
                next_cursor=result.next_cursor,
            )
        except DomainError as error:
            raise self._tool_error(error) from None
        except Exception:
            logger.exception("unexpected project list failure")
            raise self._internal_tool_error() from None

    async def project_get(self, *, project_id: str) -> ProjectGetOutput:
        try:
            auth = await self._auth_provider.resolve()
            result = await self._projects.get_project(auth, project_id)
            return ProjectGetOutput(
                operation_id=result.operation_id,
                project=ProjectView.from_domain(result.project),
            )
        except DomainError as error:
            raise self._tool_error(error) from None
        except Exception:
            logger.exception("unexpected project get failure")
            raise self._internal_tool_error() from None

    async def run_start(self, *, approved_plan_id: str, idempotency_key: str) -> RunAcceptedOutput:
        try:
            auth = await self._auth_provider.resolve()
            result = await self._runs.start(
                auth,
                approved_plan_id=approved_plan_id,
                idempotency_key=idempotency_key,
            )
            return RunAcceptedOutput(
                operation_id=result.operation_id,
                run=RunView.from_domain(result.run),
                replayed=result.replayed,
            )
        except DomainError as error:
            raise self._tool_error(error) from None
        except Exception:
            logger.exception("unexpected run start failure")
            raise self._internal_tool_error() from None

    async def run_status(self, *, run_id: str) -> RunStatusOutput:
        try:
            auth = await self._auth_provider.resolve()
            result = await self._runs.status(auth, run_id)
            return RunStatusOutput(
                operation_id=result.operation_id,
                run=RunView.from_domain(result.run),
            )
        except DomainError as error:
            raise self._tool_error(error) from None
        except Exception:
            logger.exception("unexpected run status failure")
            raise self._internal_tool_error() from None

    async def run_cancel(
        self,
        *,
        run_id: str,
        reason: str,
        expected_version: int,
    ) -> RunCancelOutput:
        try:
            auth = await self._auth_provider.resolve()
            result = await self._runs.cancel(
                auth,
                run_id=run_id,
                reason=reason,
                expected_version=expected_version,
            )
            return RunCancelOutput(
                operation_id=result.operation_id,
                run=RunView.from_domain(result.run),
                cancellation_requested=result.cancellation_requested,
            )
        except DomainError as error:
            raise self._tool_error(error) from None
        except Exception:
            logger.exception("unexpected run cancel failure")
            raise self._internal_tool_error() from None

    async def project_resource(self, project_id: str) -> str:
        try:
            output = await self.project_get(project_id=project_id)
            return output.model_dump_json()
        except ToolError as error:
            raise ResourceError(str(error)) from None

    async def run_resource(self, project_id: str, run_id: str) -> str:
        try:
            output = await self.run_status(run_id=run_id)
            if output.run.project_id != project_id:
                raise DomainError(
                    ErrorCode.NOT_FOUND_OR_FORBIDDEN,
                    "the requested target was not found or is not accessible",
                )
            return output.model_dump_json()
        except DomainError as error:
            raise ResourceError(self._error_payload(error).model_dump_json()) from None
        except ToolError as error:
            raise ResourceError(str(error)) from None

    async def public_policy_prompt(self, *, project_id: str, question: str, as_of_date: str) -> str:
        try:
            auth = await self._auth_provider.resolve()
            result = await self._projects.get_project(auth, project_id)
            return (
                f"Project {result.project.id}에서 {as_of_date} 기준으로 다음 질문을 조사할 "
                f"계획을 작성하세요: {question}\n"
                "현재 Foundation 서버에는 Plan 생성 기능이 없으므로 실행을 시도하지 말고, "
                "관할·공식출처·완료조건·미확인 항목을 먼저 정리하세요."
            )
        except DomainError as error:
            raise ValueError(self._error_payload(error).model_dump_json()) from None
        except Exception:
            logger.exception("unexpected prompt failure")
            raise ValueError(str(self._internal_tool_error())) from None

    def _error_payload(self, error: DomainError) -> ToolErrorPayload:
        operation_id = self._new_operation_id()
        if error.code in {
            ErrorCode.AUTH_SCOPE_REQUIRED,
            ErrorCode.NOT_FOUND_OR_FORBIDDEN,
        }:
            logger.warning(
                "authorization or visibility check denied",
                extra={"operation_id": operation_id, "error_code": str(error.code)},
            )
        return ToolErrorPayload(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            operation_id=operation_id,
            details=error.details,
        )

    def _tool_error(self, error: DomainError) -> ToolError:
        return ToolError(self._error_payload(error).model_dump_json())

    def _internal_tool_error(self) -> ToolError:
        payload = ToolErrorPayload(
            code=ErrorCode.INTERNAL_ERROR,
            message="an internal error occurred",
            retryable=False,
            operation_id=self._new_operation_id(),
        )
        return ToolError(payload.model_dump_json())
