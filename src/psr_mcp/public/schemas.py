"""MCP output schemas that contain no user research content."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

SourceDiscoveryMode = Literal[
    "disabled",
    "development_fixture",
    "test_static",
    "curated_seed",
    "brave_live_search",
]


class ExternalServiceDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    purpose: str
    data_sent: list[str]
    provider_retention: str
    privacy_url: HttpUrl


class ServicePolicyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    operation_id: str
    service_mode: str
    source_discovery: SourceDiscoveryMode
    authentication_required: bool
    research_available: bool
    kill_switch_active: bool
    supported_profiles: list[str]
    limits: dict[str, int | float]
    retention: dict[str, int | bool]
    external_services: list[ExternalServiceDisclosure]


class AppliedScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of_date: date
    jurisdiction: str
    profile: str
    source_discovery: SourceDiscoveryMode
    source_tracks: list[str]
    completion_criteria: list[str]
    stop_conditions: dict[str, int | float | bool]


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: str
    kind: Literal["FACT", "INFERENCE", "RECOMMENDATION"]
    citation_ids: list[str]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class ScoreComponentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1, max_length=500)


class EvidenceScoreOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    overall: float = Field(ge=0.0, le=1.0)
    authority: ScoreComponentOutput
    primary_source: ScoreComponentOutput
    direct_relevance: ScoreComponentOutput
    original_snapshot: ScoreComponentOutput
    specificity: ScoreComponentOutput
    freshness: ScoreComponentOutput
    independence: ScoreComponentOutput


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    track_id: str
    title: str
    publisher: str
    url: HttpUrl
    retrieved_at: datetime
    locator: str
    excerpt: str = Field(max_length=500)
    source_tier: str
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    score: EvidenceScoreOutput


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
