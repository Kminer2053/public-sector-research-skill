"""Official MCP client conformance probe for a deployed Foundation endpoint."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import AnyUrl

EXPECTED_TOOLS = (
    "psr.project.list",
    "psr.project.get",
    "psr.research.run.start",
    "psr.research.run.status",
    "psr.research.run.cancel",
)
EXPECTED_RESOURCE_TEMPLATES = (
    "psr://projects/{project_id}",
    "psr://projects/{project_id}/runs/{run_id}",
)
EXPECTED_PROMPTS = ("public_policy_research",)


class ConformanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ConformanceOptions:
    endpoint: str
    bearer_token: str | None = None
    project_id: str | None = None
    approved_plan_id: str | None = None
    idempotency_key: str = "conformance-request-0001"
    timeout_seconds: float = 30.0
    ca_bundle: str | None = None

    def validate(self) -> None:
        parsed = urlparse(self.endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("conformance endpoint must be a safe absolute HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("non-loopback conformance endpoint must use HTTPS")
        if self.timeout_seconds < 1 or self.timeout_seconds > 300:
            raise ValueError("conformance timeout must be 1..300 seconds")
        if len(self.idempotency_key) < 8 or len(self.idempotency_key) > 128:
            raise ValueError("conformance idempotency key must be 8..128 characters")
        if self.ca_bundle is not None:
            ca_path = Path(self.ca_bundle)
            if not ca_path.is_file():
                raise ValueError("conformance CA bundle must be a readable file")
            if parsed.scheme != "https":
                raise ValueError("conformance CA bundle is valid only for HTTPS")


async def run_conformance(options: ConformanceOptions) -> dict[str, object]:
    options.validate()
    headers = {"authorization": f"Bearer {options.bearer_token}"} if options.bearer_token else None
    timeout = httpx.Timeout(options.timeout_seconds)
    verify: bool | ssl.SSLContext = True
    if options.ca_bundle is not None:
        verify = ssl.create_default_context(cafile=options.ca_bundle)
    run_id: str | None = None
    selected_project_id: str
    try:
        async with (
            httpx.AsyncClient(
                headers=headers,
                timeout=timeout,
                follow_redirects=False,
                verify=verify,
            ) as http_client,
            streamable_http_client(
                options.endpoint,
                http_client=http_client,
            ) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            initialized = await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resource_templates()
            prompts = await session.list_prompts()
            tool_names = tuple(tool.name for tool in tools.tools)
            resource_templates = tuple(
                str(resource.uriTemplate) for resource in resources.resourceTemplates
            )
            prompt_names = tuple(prompt.name for prompt in prompts.prompts)
            _require_equal("tool catalog", tool_names, EXPECTED_TOOLS)
            _require_equal(
                "resource template catalog",
                tuple(sorted(resource_templates)),
                tuple(sorted(EXPECTED_RESOURCE_TEMPLATES)),
            )
            _require_equal("prompt catalog", prompt_names, EXPECTED_PROMPTS)

            project_page = await session.call_tool("psr.project.list", {"limit": 20})
            page_content = _structured(project_page, "project list")
            items = page_content.get("items")
            if not isinstance(items, list) or not items or not isinstance(items[0], dict):
                raise ConformanceError("project list did not contain a project")
            selected_project_id = options.project_id or _required_string(items[0], "id")
            project = await session.call_tool(
                "psr.project.get", {"project_id": selected_project_id}
            )
            _structured(project, "project get")
            project_resource = await session.read_resource(
                AnyUrl(f"psr://projects/{selected_project_id}")
            )
            if not project_resource.contents:
                raise ConformanceError("project Resource was empty")
            prompt = await session.get_prompt(
                "public_policy_research",
                {
                    "project_id": selected_project_id,
                    "question": "공공정책 조사 conformance",
                    "as_of_date": date.today().isoformat(),
                },
            )
            if not prompt.messages:
                raise ConformanceError("Prompt response was empty")

            if options.approved_plan_id is not None:
                started = await session.call_tool(
                    "psr.research.run.start",
                    {
                        "approved_plan_id": options.approved_plan_id,
                        "idempotency_key": options.idempotency_key,
                    },
                )
                run = _structured(started, "run start").get("run")
                if not isinstance(run, dict):
                    raise ConformanceError("run start result was missing run")
                run_id = _required_string(run, "id")

            initialized_payload = initialized.model_dump(mode="json", by_alias=True)

        reconnect_verified = False
        if run_id is not None:
            async with (
                httpx.AsyncClient(
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=False,
                    verify=verify,
                ) as reconnect_client,
                streamable_http_client(
                    options.endpoint,
                    http_client=reconnect_client,
                ) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                status = await session.call_tool("psr.research.run.status", {"run_id": run_id})
                status_run = _structured(status, "run status after reconnect").get("run")
                if not isinstance(status_run, dict) or status_run.get("id") != run_id:
                    raise ConformanceError("run identity changed after reconnect")
                resource = await session.read_resource(
                    AnyUrl(f"psr://projects/{selected_project_id}/runs/{run_id}")
                )
                reconnect_verified = bool(resource.contents)

        server_info = initialized_payload.get("serverInfo")
        if not isinstance(server_info, dict):
            raise ConformanceError("initialize response omitted serverInfo")
        return {
            "status": "PASS",
            "endpoint": options.endpoint,
            "protocol_version": initialized_payload.get("protocolVersion"),
            "server_name": server_info.get("name"),
            "tool_names": list(tool_names),
            "resource_templates": list(resource_templates),
            "prompt_names": list(prompt_names),
            "project_id": selected_project_id,
            "run_id": run_id,
            "reconnect_verified": reconnect_verified,
            "bearer_token_used": options.bearer_token is not None,
        }
    except ConformanceError:
        raise
    except Exception as error:
        raise ConformanceError("remote MCP conformance request failed") from error


def _structured(result: object, name: str) -> dict[str, object]:
    is_error = getattr(result, "isError", True)
    structured = getattr(result, "structuredContent", None)
    content = getattr(result, "content", None)
    if is_error or not isinstance(structured, dict):
        raise ConformanceError(f"{name} did not return structured success output")
    if not isinstance(content, list) or not content:
        raise ConformanceError(f"{name} omitted text compatibility output")
    return structured


def _required_string(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ConformanceError(f"required field is missing: {key}")
    return value


def _require_equal(name: str, observed: tuple[str, ...], expected: tuple[str, ...]) -> None:
    if observed != expected:
        raise ConformanceError(f"{name} does not match the reviewed contract")
