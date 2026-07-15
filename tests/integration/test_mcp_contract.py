from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import AnyUrl

from psr_mcp.bootstrap import build_container
from psr_mcp.config import Settings
from psr_mcp.mcp.server import create_server


@pytest.fixture
async def client_session() -> AsyncGenerator[ClientSession]:
    server = create_server(build_container(Settings.from_env({})))
    async with create_connected_server_and_client_session(
        server,
        raise_exceptions=False,
    ) as session:
        yield session


@pytest.mark.anyio
async def test_catalog_is_versioned_and_complete(client_session: ClientSession) -> None:
    tools = await client_session.list_tools()
    templates = await client_session.list_resource_templates()
    prompts = await client_session.list_prompts()

    assert [tool.name for tool in tools.tools] == [
        "psr.project.list",
        "psr.project.get",
        "psr.research.run.start",
        "psr.research.run.status",
        "psr.research.run.cancel",
    ]
    assert all(tool.outputSchema for tool in tools.tools)
    assert all(tool.annotations is not None for tool in tools.tools)
    assert {str(template.uriTemplate) for template in templates.resourceTemplates} == {
        "psr://projects/{project_id}",
        "psr://projects/{project_id}/runs/{run_id}",
    }
    assert [prompt.name for prompt in prompts.prompts] == ["public_policy_research"]

    canonical = json.dumps(
        [tool.model_dump(mode="json", exclude_none=True) for tool in tools.tools],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    # Intentional contract changes must update this reviewed canonical catalog digest.
    assert (
        hashlib.sha256(canonical).hexdigest()
        == "80ce6af8829f6210da6ecfe57e7df18996af4f0f03845a5f851f0d8fb6aaa84e"
    )


@pytest.mark.anyio
async def test_tool_resource_and_error_flow(client_session: ClientSession) -> None:
    projects = await client_session.call_tool("psr.project.list", {"limit": 20})
    assert projects.isError is False
    assert projects.structuredContent is not None
    assert projects.structuredContent["schema_version"] == "1.0"
    assert projects.structuredContent["items"][0]["id"] == "project-public-ai"
    assert projects.content
    assert "development-only-cursor-signing-key" not in projects.content[0].text  # type: ignore[union-attr]

    project = await client_session.call_tool("psr.project.get", {"project_id": "project-public-ai"})
    assert project.isError is False
    assert project.structuredContent is not None
    project_resource = await client_session.read_resource(
        project.structuredContent["project"]["resource_uri"]
    )
    assert "project-public-ai" in project_resource.contents[0].text  # type: ignore[union-attr]

    started = await client_session.call_tool(
        "psr.research.run.start",
        {
            "approved_plan_id": "plan-approved-public-ai",
            "idempotency_key": "mcp-request-0001",
        },
    )
    assert started.isError is False
    assert started.structuredContent is not None
    run = started.structuredContent["run"]
    assert run["status"] == "QUEUED"

    status = await client_session.call_tool("psr.research.run.status", {"run_id": run["id"]})
    assert status.isError is False
    assert status.structuredContent is not None
    assert status.structuredContent["run"]["id"] == run["id"]

    resource = await client_session.read_resource(run["resource_uri"])
    payload = json.loads(resource.contents[0].text)  # type: ignore[union-attr]
    assert payload["run"]["id"] == run["id"]

    cancelled = await client_session.call_tool(
        "psr.research.run.cancel",
        {
            "run_id": run["id"],
            "reason": "통합 테스트에서 사용자가 실행 취소를 요청합니다.",
            "expected_version": run["version"],
        },
    )
    assert cancelled.isError is False
    assert cancelled.structuredContent is not None
    assert cancelled.structuredContent["run"]["status"] == "CANCELLED"

    failed = await client_session.call_tool(
        "psr.research.run.start",
        {"approved_plan_id": "missing-plan", "idempotency_key": "mcp-request-0002"},
    )
    assert failed.isError is True
    error_text = failed.content[0].text  # type: ignore[union-attr]
    assert "NOT_FOUND_OR_FORBIDDEN" in error_text
    assert "missing-plan" not in error_text

    missing_project = await client_session.call_tool(
        "psr.project.get", {"project_id": "missing-project"}
    )
    assert missing_project.isError is True
    assert "NOT_FOUND_OR_FORBIDDEN" in missing_project.content[0].text  # type: ignore[union-attr]

    missing_status = await client_session.call_tool(
        "psr.research.run.status", {"run_id": "missing-run"}
    )
    assert missing_status.isError is True

    stale_cancel = await client_session.call_tool(
        "psr.research.run.cancel",
        {
            "run_id": run["id"],
            "reason": "이미 취소된 실행에 다시 취소 요청을 보냅니다.",
            "expected_version": 1,
        },
    )
    assert stale_cancel.isError is True
    assert "VERSION_CONFLICT" in stale_cancel.content[0].text  # type: ignore[union-attr]

    with pytest.raises(McpError):
        await client_session.read_resource(AnyUrl(f"psr://projects/wrong-project/runs/{run['id']}"))


@pytest.mark.anyio
async def test_prompt_is_user_controlled_template(client_session: ClientSession) -> None:
    prompt = await client_session.get_prompt(
        "public_policy_research",
        {
            "project_id": "project-public-ai",
            "question": "AI 구매 원칙",
            "as_of_date": "2026-07-16",
        },
    )
    assert "Plan 생성 기능이 없으므로" in prompt.messages[0].content.text  # type: ignore[union-attr]

    with pytest.raises(McpError):
        await client_session.get_prompt(
            "public_policy_research",
            {
                "project_id": "missing-project",
                "question": "AI 구매 원칙",
                "as_of_date": "2026-07-16",
            },
        )


@pytest.mark.anyio
async def test_malformed_json_is_a_protocol_error() -> None:
    server = create_server(build_container(Settings.from_env({})))
    app = server.streamable_http_app()
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client,
    ):
        response = await client.post(
            "/mcp",
            content="{not-json",
            headers={
                "accept": "application/json, text/event-stream",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["error"]["code"] == -32700
