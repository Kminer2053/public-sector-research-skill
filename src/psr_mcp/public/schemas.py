"""MCP output schemas that contain no user research content."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


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


class AppliedScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of_date: date
    jurisdiction: str
    profile: str
    source_tracks: list[str]
    completion_criteria: list[str]
    stop_conditions: dict[str, int | float | bool]


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: str
    kind: Literal["FACT", "INFERENCE", "RECOMMENDATION"]
    citation_ids: list[str]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    publisher: str
    url: HttpUrl
    retrieved_at: datetime
    locator: str
    excerpt: str = Field(max_length=500)
    source_tier: str


class ResearchFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    retryable: bool


class RetentionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server_saved: Literal[False] = False
    purge_state: Literal["PURGED"]
    purged_at: datetime


class QuickResearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    operation_id: str
    status: Literal["PARTIAL", "SUCCEEDED"]
    summary: str
    scope: AppliedScope
    findings: list[Finding]
    citations: list[Citation]
    gaps: list[str]
    conflicts: list[str]
    failures: list[ResearchFailure]
    markdown: str
    retention: RetentionStatus


class PublicToolErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    retryable: bool
    operation_id: str
