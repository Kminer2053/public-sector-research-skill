"""Anonymous Tool catalog for the zero-retention public service mode."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from psr_mcp.bootstrap import PublicContainer
from psr_mcp.config import Environment
from psr_mcp.mcp.transport import transport_security
from psr_mcp.public.schemas import ServicePolicyOutput


def create_public_server(container: PublicContainer) -> FastMCP:
    settings = container.settings
    server = FastMCP(
        name=(
            "Public Sector Research MCP [PUBLIC DEVELOPMENT]"
            if settings.environment is Environment.DEVELOPMENT
            else "Public Sector Research MCP"
        ),
        instructions=(
            "가입 없이 공공분야 공식자료를 조사하기 위한 Public Preview 서버입니다. "
            "현재 increment는 서비스 정책과 무보관 실행경계를 제공합니다. "
            "실제 Research Tool은 PG1 검증 뒤 활성화됩니다."
        ),
        website_url=settings.public_url,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        json_response=True,
        stateless_http=True,
        transport_security=transport_security(settings),
    )

    @server.tool(
        name="psr.service.policy",
        title="공개 리서치 서비스 정책",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def service_policy() -> ServicePolicyOutput:
        """현재 공개 mode의 실제 한도와 content 보존정책을 반환합니다."""
        return ServicePolicyOutput(
            operation_id=container.ids.new(),
            service_mode=settings.service_mode,
            authentication_required=False,
            research_available=False,
            kill_switch_active=settings.public_kill_switch,
            supported_profiles=["government-v0"],
            limits={
                "request_bytes": settings.max_request_bytes,
                "request_timeout_seconds": settings.request_timeout_seconds,
                "requests_per_window": settings.rate_limit_requests,
                "rate_window_seconds": settings.rate_limit_window_seconds,
            },
            retention={
                "server_saved": False,
                "run_ttl_seconds": settings.run_ttl_seconds,
                "delivered_purge_seconds": settings.delivered_purge_seconds,
                "failed_content_ttl_seconds": settings.failed_content_ttl_seconds,
                "orphan_max_age_seconds": settings.orphan_max_age_seconds,
            },
        )

    return server
