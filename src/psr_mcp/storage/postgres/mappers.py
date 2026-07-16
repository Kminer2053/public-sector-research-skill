"""Explicit PostgreSQL row to domain mappings."""

from __future__ import annotations

from typing import Any

from psycopg.rows import DictRow

from psr_mcp.domain.audit import AuditEvent, AuditOutcome
from psr_mcp.domain.identity import ActorType
from psr_mcp.domain.projects import Project, ProjectStatus
from psr_mcp.domain.research import (
    Job,
    JobState,
    PlanStatus,
    ResearchPlan,
    ResearchRun,
    RunStatus,
)


def project_from_row(row: DictRow) -> Project:
    return Project(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        name=_str(row, "name"),
        profile=_str(row, "profile"),
        status=ProjectStatus(_str(row, "status")),
        version=_int(row, "version"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def plan_from_row(row: DictRow) -> ResearchPlan:
    approved_by = row["approved_by"]
    return ResearchPlan(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
        version=_int(row, "version"),
        question=_str(row, "question"),
        status=PlanStatus(_str(row, "status")),
        approved_by=str(approved_by) if approved_by is not None else None,
        approved_at=row["approved_at"],
    )


def run_from_row(row: DictRow) -> ResearchRun:
    return ResearchRun(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
        plan_id=str(row["plan_id"]),
        plan_version=_int(row, "plan_version"),
        initiated_by=str(row["initiated_by"]),
        status=RunStatus(_str(row, "status")),
        version=_int(row, "version"),
        idempotency_key=_str(row, "idempotency_key"),
        request_fingerprint=_str(row, "request_fingerprint"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        failure_code=_optional_str(row["failure_code"]),
        cancellation_requested_at=row["cancellation_requested_at"],
        cancel_reason=_optional_str(row["cancel_reason"]),
    )


def job_from_row(row: DictRow) -> Job:
    return Job(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        state=JobState(_str(row, "state")),
        available_at=row["available_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        attempts=_int(row, "attempts"),
        max_attempts=_int(row, "max_attempts"),
        lease_owner=_optional_str(row["lease_owner"]),
        lease_expires_at=row["lease_expires_at"],
        cancel_requested_at=row["cancel_requested_at"],
    )


def audit_from_row(row: DictRow) -> AuditEvent:
    metadata = row["metadata_json"]
    if not isinstance(metadata, dict):
        raise TypeError("metadata_json must be an object")
    return AuditEvent(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        project_id=_optional_str(row["project_id"]),
        occurred_at=row["occurred_at"],
        actor_subject_id=_str(row, "actor_subject_id"),
        actor_type=ActorType(_str(row, "actor_type")),
        operation=_str(row, "operation"),
        target_type=_str(row, "target_type"),
        target_id=_optional_str(row["target_id"]),
        outcome=AuditOutcome(_str(row, "outcome")),
        operation_id=_str(row, "operation_id"),
        reason_code=_optional_str(row["reason_code"]),
        metadata=metadata,
    )


def _str(row: DictRow, key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _int(row: DictRow, key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value
