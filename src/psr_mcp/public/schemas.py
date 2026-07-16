"""MCP output schemas that contain no user research content."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ServicePolicyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    operation_id: str
    service_mode: str
    authentication_required: bool
    research_available: bool
    kill_switch_active: bool
    supported_profiles: list[str]
    limits: dict[str, int | float]
    retention: dict[str, int | bool]
