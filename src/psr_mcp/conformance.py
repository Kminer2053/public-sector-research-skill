"""Official MCP client conformance probes for Foundation and public endpoints."""

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

from psr_mcp.public.review import evaluate_structural_review
from psr_mcp.public.schemas import QuickResearchOutput

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
EXPECTED_PUBLIC_TOOLS = (
    "psr.service.policy",
    "psr.research.quick",
    "psr.feedback.submit",
)
PUBLIC_CONFORMANCE_QUESTION = (
    "공공기관 AI 구매 원칙의 개인정보, 데이터 권리, 사람의 감독과 "
    "업체 종속 조건을 공식자료로 조사해줘"
)


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
        _validate_remote_endpoint(
            endpoint=self.endpoint,
            timeout_seconds=self.timeout_seconds,
            ca_bundle=self.ca_bundle,
        )
        if len(self.idempotency_key) < 8 or len(self.idempotency_key) > 128:
            raise ValueError("conformance idempotency key must be 8..128 characters")


@dataclass(frozen=True, slots=True)
class PublicConformanceOptions:
    endpoint: str
    timeout_seconds: float = 30.0
    ca_bundle: str | None = None
    release_gate: bool = True
    verify_feedback_submission: bool = False

    def validate(self) -> None:
        _validate_remote_endpoint(
            endpoint=self.endpoint,
            timeout_seconds=self.timeout_seconds,
            ca_bundle=self.ca_bundle,
        )


async def run_conformance(options: ConformanceOptions) -> dict[str, object]:
    options.validate()
    headers = {"authorization": f"Bearer {options.bearer_token}"} if options.bearer_token else None
    timeout = httpx.Timeout(options.timeout_seconds)
    verify = _tls_verify(options.ca_bundle)
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


async def run_public_conformance(
    options: PublicConformanceOptions,
) -> dict[str, object]:
    options.validate()
    timeout = httpx.Timeout(options.timeout_seconds)
    verify = _tls_verify(options.ca_bundle)
    try:
        async with (
            httpx.AsyncClient(
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
            _require_equal("public tool catalog", tool_names, EXPECTED_PUBLIC_TOOLS)
            if resources.resourceTemplates:
                raise ConformanceError("public server exposed Resource templates")
            if prompts.prompts:
                raise ConformanceError("public server exposed Prompts")

            policy_result = await session.call_tool("psr.service.policy", {})
            policy = _structured(policy_result, "public service policy")
            _require_public_policy(policy)

            quick_result = await session.call_tool(
                "psr.research.quick",
                {"question": PUBLIC_CONFORMANCE_QUESTION},
            )
            quick_payload = _structured(quick_result, "public quick research")
            try:
                quick = QuickResearchOutput.model_validate(quick_payload)
            except ValueError as error:
                raise ConformanceError(
                    "public quick result did not match reviewed schema"
                ) from error
            _require_public_result(policy, quick)
            review = evaluate_structural_review(quick)
            source_discovery = _required_string(policy, "source_discovery")
            if options.release_gate:
                if source_discovery in {"disabled", "development_fixture", "test_static"}:
                    raise ConformanceError("public release conformance requires a real source mode")
                if not review.passed:
                    raise ConformanceError("public release research quality gate failed")

            feedback_submission_verified = False
            if options.verify_feedback_submission:
                feedback_result = await session.call_tool(
                    "psr.feedback.submit",
                    {
                        "feedback_token": quick.feedback_token,
                        "helpful": False,
                        "save_feature_interest": False,
                    },
                )
                feedback = _structured(feedback_result, "public feedback submission")
                if (
                    feedback.get("accepted") is not True
                    or feedback.get("content_linked") is not False
                ):
                    raise ConformanceError("public feedback result violated content-free contract")
                feedback_submission_verified = True

            initialized_payload = initialized.model_dump(mode="json", by_alias=True)

        async with (
            httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                verify=verify,
            ) as reconnect_client,
            streamable_http_client(
                options.endpoint,
                http_client=reconnect_client,
            ) as (read, write, _),
            ClientSession(read, write) as reconnect_session,
        ):
            await reconnect_session.initialize()
            reconnect_policy = _structured(
                await reconnect_session.call_tool("psr.service.policy", {}),
                "public service policy after reconnect",
            )
            reconnect_verified = (
                reconnect_policy.get("service_mode") == policy.get("service_mode")
                and reconnect_policy.get("source_discovery") == source_discovery
            )
            if not reconnect_verified:
                raise ConformanceError("public policy changed across reconnect")

        server_info = initialized_payload.get("serverInfo")
        if not isinstance(server_info, dict):
            raise ConformanceError("initialize response omitted serverInfo")
        return {
            "status": "PASS",
            "endpoint": options.endpoint,
            "protocol_version": initialized_payload.get("protocolVersion"),
            "server_name": server_info.get("name"),
            "tool_names": list(tool_names),
            "resource_templates": [],
            "prompt_names": [],
            "authentication_required": False,
            "source_discovery": source_discovery,
            "research_status": quick.status,
            "citation_count": review.citation_count,
            "unique_document_count": review.unique_document_count,
            "fact_citation_coverage": review.fact_citation_coverage,
            "recommendation_citation_coverage": review.recommendation_citation_coverage,
            "locator_completeness": review.locator_completeness,
            "official_primary_document_ratio": review.official_primary_document_ratio,
            "required_track_recall": review.required_track_recall,
            "purge_verified": True,
            "feedback_token_present": bool(quick.feedback_token),
            "feedback_submission_verified": feedback_submission_verified,
            "release_gate_checked": options.release_gate,
            "reconnect_verified": reconnect_verified,
        }
    except ConformanceError:
        raise
    except Exception as error:
        raise ConformanceError("public MCP conformance request failed") from error


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


def _require_public_policy(policy: dict[str, object]) -> None:
    if policy.get("service_mode") != "public_ephemeral":
        raise ConformanceError("public service policy reported the wrong mode")
    if policy.get("authentication_required") is not False:
        raise ConformanceError("public service unexpectedly requires authentication")
    if policy.get("research_available") is not True:
        raise ConformanceError("public research is not accepting new work")
    if policy.get("kill_switch_active") is not False:
        raise ConformanceError("public research is paused")
    retention = policy.get("retention")
    if not isinstance(retention, dict):
        raise ConformanceError("public policy omitted retention")
    if retention.get("server_saved") is not False:
        raise ConformanceError("public policy reported persistent server content")
    if retention.get("feedback_content_linked") is not False:
        raise ConformanceError("public policy linked feedback to research content")
    supported_profiles = policy.get("supported_profiles")
    if not isinstance(supported_profiles, list) or "government-v0" not in supported_profiles:
        raise ConformanceError("public policy omitted the reviewed profile")


def _require_public_result(
    policy: dict[str, object],
    quick: QuickResearchOutput,
) -> None:
    if quick.scope.source_discovery != policy.get("source_discovery"):
        raise ConformanceError("public policy and quick source modes differ")
    if not quick.citations:
        raise ConformanceError("public quick result contained no citations")
    if len(quick.feedback_token) < 40:
        raise ConformanceError("public quick result omitted a usable feedback capability")
    if quick.feedback_expires_at <= quick.retention.purged_at:
        raise ConformanceError("public feedback capability did not expire after purge")


def _validate_remote_endpoint(
    *,
    endpoint: str,
    timeout_seconds: float,
    ca_bundle: str | None,
) -> None:
    parsed = urlparse(endpoint)
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
    if timeout_seconds < 1 or timeout_seconds > 300:
        raise ValueError("conformance timeout must be 1..300 seconds")
    if ca_bundle is not None:
        ca_path = Path(ca_bundle)
        if not ca_path.is_file():
            raise ValueError("conformance CA bundle must be a readable file")
        if parsed.scheme != "https":
            raise ValueError("conformance CA bundle is valid only for HTTPS")


def _tls_verify(ca_bundle: str | None) -> bool | ssl.SSLContext:
    if ca_bundle is None:
        return True
    return ssl.create_default_context(cafile=ca_bundle)
