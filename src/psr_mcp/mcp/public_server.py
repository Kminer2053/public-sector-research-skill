"""Anonymous Tool catalog for the zero-retention public service mode."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, HttpUrl

from psr_mcp.bootstrap import PublicContainer
from psr_mcp.config import Environment, SearchProviderMode
from psr_mcp.mcp.transport import transport_security
from psr_mcp.public.schemas import (
    ExternalServiceDisclosure,
    PublicToolErrorPayload,
    QuickResearchOutput,
    ServicePolicyOutput,
    SourceDiscoveryMode,
)
from psr_mcp.public.service import PublicResearchError


def create_public_server(container: PublicContainer) -> FastMCP:
    settings = container.settings
    server = FastMCP(
        name=(
            "Public Sector Research MCP [PUBLIC DEVELOPMENT]"
            if settings.environment is Environment.DEVELOPMENT
            else "Public Sector Research MCP"
        ),
        instructions=_server_instructions(settings.search_provider),
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
            source_discovery=_source_discovery(
                settings.search_provider,
                fixture_enabled=settings.public_fixture_research_enabled,
            ),
            authentication_required=False,
            research_available=container.quick_service.available,
            kill_switch_active=settings.public_kill_switch,
            supported_profiles=["government-v0"],
            limits={
                "request_bytes": settings.max_request_bytes,
                "request_timeout_seconds": settings.request_timeout_seconds,
                "quick_timeout_seconds": settings.quick_timeout_seconds,
                "max_active_quick": settings.public_max_active_quick,
                "requests_per_window": settings.rate_limit_requests,
                "rate_window_seconds": settings.rate_limit_window_seconds,
                "max_run_sources": settings.max_run_sources,
                "max_run_bytes": settings.max_run_bytes,
                "trusted_proxy_networks": len(settings.trusted_proxy_cidrs),
            },
            retention={
                "server_saved": False,
                "run_ttl_seconds": settings.run_ttl_seconds,
                "delivered_purge_seconds": settings.delivered_purge_seconds,
                "failed_content_ttl_seconds": settings.failed_content_ttl_seconds,
                "orphan_max_age_seconds": settings.orphan_max_age_seconds,
            },
            external_services=_external_services(settings.search_provider),
        )

    @server.tool(
        name="psr.research.quick",
        title="공식자료 우선 빠른 조사",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def research_quick(
        question: Annotated[str, Field(min_length=10, max_length=4_000)],
        as_of_date: date | None = None,
        jurisdiction: Literal["KR"] = "KR",
        profile: Literal["government-v0"] = "government-v0",
    ) -> QuickResearchOutput:
        """임시 workspace에서 조사하고 content를 삭제한 뒤 결과만 반환합니다."""
        try:
            return await container.quick_service.quick(
                question=question,
                as_of_date=as_of_date,
                jurisdiction=jurisdiction,
                profile=profile,
            )
        except PublicResearchError as error:
            raise ToolError(
                PublicToolErrorPayload(
                    code=error.code,
                    message=error.message,
                    retryable=error.retryable,
                    operation_id=container.ids.new(),
                ).model_dump_json()
            ) from None

    return server


def _external_services(
    provider: SearchProviderMode,
) -> list[ExternalServiceDisclosure]:
    if provider is not SearchProviderMode.BRAVE:
        return []
    return [
        ExternalServiceDisclosure(
            provider="Brave Search API",
            purpose="공식자료 후보 URL 검색",
            data_sent=["조사 질문에서 생성한 검색어"],
            provider_retention=(
                "표준 Search API는 검색 질의를 최대 90일 보관할 수 있음; Enterprise ZDR 계약은 별도"
            ),
            privacy_url=HttpUrl("https://api-dashboard.search.brave.com/privacy-policy"),
        )
    ]


def _source_discovery(
    provider: SearchProviderMode,
    *,
    fixture_enabled: bool,
) -> SourceDiscoveryMode:
    if fixture_enabled:
        return "development_fixture"
    if provider is SearchProviderMode.CURATED:
        return "curated_seed"
    if provider is SearchProviderMode.BRAVE:
        return "brave_live_search"
    return "disabled"


def _server_instructions(provider: SearchProviderMode) -> str:
    base = (
        "가입 없이 공공분야 공식자료를 조사하기 위한 Public Preview 서버입니다. "
        "현재 quick Tool은 개발 fixture 또는 명시적으로 구성된 backend만 사용하며, "
        "결과의 retention 상태와 조사 한계를 반드시 확인해야 합니다."
    )
    if provider is SearchProviderMode.DISABLED:
        return base
    if provider is SearchProviderMode.CURATED:
        return (
            f"{base} 현재 source discovery는 한국 공공부문 AI 조달 질문에 한정된 "
            "검토된 공식자료 seed catalog이며 실시간 웹 검색이 아닙니다."
        )
    return (
        f"{base} Brave Search API가 구성된 경우 질문에서 만든 검색어가 외부 provider로 "
        "전송되며, provider-side 보존정책은 PSR 서버의 무보관 정책과 별개입니다. "
        "호출 전에 psr.service.policy를 확인하세요."
    )
