"""Official MCP SDK v1 server registration."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.routing import Mount

from psr_mcp.bootstrap import ApplicationContainer, PublicContainer
from psr_mcp.config import AuthMode, Environment
from psr_mcp.mcp.handlers import McpHandlers
from psr_mcp.mcp.http_policy import compose_http_policy
from psr_mcp.mcp.public_server import create_public_server
from psr_mcp.mcp.schemas import (
    ProjectGetOutput,
    ProjectPageOutput,
    RunAcceptedOutput,
    RunCancelOutput,
    RunStatusOutput,
)
from psr_mcp.mcp.transport import transport_security


def create_server(
    container: ApplicationContainer,
    *,
    token_verifier: TokenVerifier | None = None,
) -> FastMCP:
    if isinstance(container, PublicContainer):
        if token_verifier is not None:
            raise RuntimeError("public mode does not accept an OAuth token verifier")
        return create_public_server(container)
    settings = container.settings
    effective_verifier = token_verifier or container.token_verifier
    if token_verifier is not None and container.token_verifier is not None:
        raise RuntimeError("token verifier is configured twice")
    auth_settings: AuthSettings | None = None
    if settings.auth_mode is AuthMode.OAUTH:
        if effective_verifier is None or settings.issuer_url is None:
            raise RuntimeError("OAuth mode requires a configured token verifier")
        auth_settings = AuthSettings(
            issuer_url=AnyHttpUrl(settings.issuer_url),
            resource_server_url=AnyHttpUrl(settings.resource_server_url),
            required_scopes=list(settings.required_mcp_scopes),
        )
    elif effective_verifier is not None:
        raise RuntimeError("a token verifier cannot be used while authentication is static")
    handlers = McpHandlers(
        container.auth_provider,
        container.project_service,
        container.run_service,
        container.ids,
    )
    server = FastMCP(
        name=(
            "Public Sector Research MCP [DEVELOPMENT]"
            if settings.environment is Environment.DEVELOPMENT
            else "Public Sector Research MCP"
        ),
        instructions=(
            "공공분야 공식자료 조사를 위한 Evidence-First MCP Foundation 서버입니다. "
            "현재 계약은 Project와 승인된 ResearchRun의 최소 수명주기를 제공합니다."
        ),
        website_url=settings.public_url,
        token_verifier=effective_verifier,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        json_response=True,
        stateless_http=True,
        auth=auth_settings,
        transport_security=transport_security(settings),
    )

    @server.tool(
        name="psr.project.list",
        title="접근 가능한 조사 프로젝트 목록",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def project_list(cursor: str | None = None, limit: int = 20) -> ProjectPageOutput:
        """현재 인증 주체가 접근할 수 있는 Project를 안정적인 cursor로 조회합니다."""
        return await handlers.project_list(cursor=cursor, limit=limit)

    @server.tool(
        name="psr.project.get",
        title="조사 프로젝트 조회",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def project_get(project_id: str) -> ProjectGetOutput:
        """권한이 있는 Project의 profile과 상태를 조회합니다."""
        return await handlers.project_get(project_id=project_id)

    @server.tool(
        name="psr.research.run.start",
        title="승인된 조사 실행 시작",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def run_start(approved_plan_id: str, idempotency_key: str) -> RunAcceptedOutput:
        """승인된 Plan에서 durable ResearchRun을 idempotent하게 생성합니다."""
        return await handlers.run_start(
            approved_plan_id=approved_plan_id,
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="psr.research.run.status",
        title="조사 실행 상태 조회",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def run_status(run_id: str) -> RunStatusOutput:
        """ResearchRun의 사용자 공개 상태를 조회합니다."""
        return await handlers.run_status(run_id=run_id)

    @server.tool(
        name="psr.research.run.cancel",
        title="조사 실행 취소",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def run_cancel(run_id: str, reason: str, expected_version: int) -> RunCancelOutput:
        """현재 version을 확인해 queued run을 취소하거나 running run에 취소를 요청합니다."""
        return await handlers.run_cancel(
            run_id=run_id,
            reason=reason,
            expected_version=expected_version,
        )

    @server.resource(
        "psr://projects/{project_id}",
        name="project",
        title="조사 프로젝트",
        description="권한이 있는 Project의 JSON 표현",
        mime_type="application/json",
    )
    async def project_resource(project_id: str) -> str:
        return await handlers.project_resource(project_id)

    @server.resource(
        "psr://projects/{project_id}/runs/{run_id}",
        name="research-run",
        title="조사 실행",
        description="권한이 있는 ResearchRun 상태의 JSON 표현",
        mime_type="application/json",
    )
    async def run_resource(project_id: str, run_id: str) -> str:
        return await handlers.run_resource(project_id, run_id)

    @server.prompt(name="public_policy_research", title="공공정책 조사 시작")
    async def public_policy_research(project_id: str, question: str, as_of_date: str) -> str:
        """공공정책 조사계획 작성을 시작하는 사용자 선택형 workflow template입니다."""
        return await handlers.public_policy_prompt(
            project_id=project_id,
            question=question,
            as_of_date=as_of_date,
        )

    return server


def create_http_app(
    container: ApplicationContainer,
    *,
    token_verifier: TokenVerifier | None = None,
) -> Starlette:
    """Compose process-wide adapter lifecycle around the SDK Streamable HTTP app."""
    inner = create_server(container, token_verifier=token_verifier).streamable_http_app()
    protected = compose_http_policy(
        inner,
        request_id_factory=container.ids.new,
        max_request_bytes=container.settings.max_request_bytes,
        request_timeout_seconds=container.settings.request_timeout_seconds,
        rate_limit_requests=container.settings.rate_limit_requests,
        rate_limit_window_seconds=container.settings.rate_limit_window_seconds,
        rate_limit_hmac_key=(
            container.abuse_hmac_key
            if isinstance(container, PublicContainer)
            else container.settings.cursor_signing_key.encode()
        ),
        trusted_proxy_cidrs=container.settings.trusted_proxy_cidrs,
    )

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        await container.open()
        try:
            async with inner.router.lifespan_context(inner):
                yield None
        finally:
            await container.close()

    return Starlette(
        debug=False,
        routes=[Mount("/", app=protected)],
        lifespan=lifespan,
    )
