"""Versioned MCP output schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from psr_mcp.domain.projects import Project
from psr_mcp.domain.research import ResearchRun


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    operation_id: str


class ProjectView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    profile: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    resource_uri: str

    @classmethod
    def from_domain(cls, project: Project) -> ProjectView:
        return cls(
            id=project.id,
            name=project.name,
            profile=project.profile,
            status=project.status,
            version=project.version,
            created_at=project.created_at,
            updated_at=project.updated_at,
            resource_uri=f"psr://projects/{project.id}",
        )


class ProjectPageOutput(OutputModel):
    items: list[ProjectView]
    next_cursor: str | None = None


class ProjectGetOutput(OutputModel):
    project: ProjectView


class RunView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    project_id: str
    plan_id: str
    plan_version: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    failure_code: str | None
    cancellation_requested: bool
    resource_uri: str

    @classmethod
    def from_domain(cls, run: ResearchRun) -> RunView:
        return cls(
            id=run.id,
            project_id=run.project_id,
            plan_id=run.plan_id,
            plan_version=run.plan_version,
            status=run.status,
            version=run.version,
            created_at=run.created_at,
            updated_at=run.updated_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            failure_code=run.failure_code,
            cancellation_requested=run.cancellation_requested_at is not None,
            resource_uri=f"psr://projects/{run.project_id}/runs/{run.id}",
        )


class RunAcceptedOutput(OutputModel):
    run: RunView
    replayed: bool


class RunStatusOutput(OutputModel):
    run: RunView


class RunCancelOutput(OutputModel):
    run: RunView
    cancellation_requested: bool


class ToolErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    retryable: bool
    operation_id: str
    details: dict[str, object] = Field(default_factory=dict)
