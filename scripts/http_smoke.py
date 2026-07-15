"""Run a minimal official-SDK client smoke against a local PSR MCP endpoint."""

from __future__ import annotations

import argparse
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def smoke(endpoint: str) -> dict[str, object]:
    run_id: str
    async with (
        streamable_http_client(endpoint) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("psr.project.list", {"limit": 20})
        if result.isError or result.structuredContent is None:
            raise RuntimeError("project list smoke failed")
        items = result.structuredContent.get("items")
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            raise RuntimeError("project list response shape is invalid")
        started = await session.call_tool(
            "psr.research.run.start",
            {
                "approved_plan_id": "plan-approved-public-ai",
                "idempotency_key": "http-smoke-request-0001",
            },
        )
        if started.isError or started.structuredContent is None:
            raise RuntimeError("run start smoke failed")
        run = started.structuredContent.get("run")
        if not isinstance(run, dict) or not isinstance(run.get("id"), str):
            raise RuntimeError("run start response shape is invalid")
        run_id = run["id"]

    async with (
        streamable_http_client(endpoint) as (read, write, _),
        ClientSession(read, write) as reconnected_session,
    ):
        await reconnected_session.initialize()
        status = await reconnected_session.call_tool("psr.research.run.status", {"run_id": run_id})
        if status.isError or status.structuredContent is None:
            raise RuntimeError("run status after reconnect failed")
        status_run = status.structuredContent.get("run")
        if not isinstance(status_run, dict) or status_run.get("id") != run_id:
            raise RuntimeError("reconnected run status shape is invalid")
        return {
            "endpoint": endpoint,
            "project_id": items[0].get("id"),
            "reconnected_run_id": run_id,
            "tool_names": [tool.name for tool in tools.tools],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/mcp")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(smoke(args.endpoint)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
