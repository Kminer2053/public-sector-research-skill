"""Structured, citation-safe briefing data for human-facing reports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from psr_core.models import Citation, ResearchPlan

BRIEF_SCHEMA_VERSION = "1.0"
ALLOWED_KINDS = {"FACT", "INFERENCE", "RECOMMENDATION"}


class BriefValidationError(ValueError):
    """Raised when a brief could produce an untraceable report."""


def build_default_brief(
    *,
    plan: ResearchPlan,
    citations: Sequence[Citation],
    gaps: Sequence[str],
) -> Dict[str, Any]:
    """Build a conservative extractive brief without inventing conclusions."""

    track_titles = {track.id: track.title for track in plan.tracks}
    highlights = []
    findings = []
    represented = set()
    for citation in citations:
        item = {
            "kind": "FACT",
            "text": _shorten(citation.excerpt, 220),
            "citation_ids": [citation.id],
        }
        if len(highlights) < 3:
            highlights.append(item)
        if citation.track_id not in represented and len(findings) < 8:
            represented.add(citation.track_id)
            findings.append(
                {
                    "id": f"finding-{len(findings) + 1}",
                    "title": track_titles.get(citation.track_id, citation.track_id),
                    "kind": "FACT",
                    "text": _shorten(citation.excerpt, 420),
                    "citation_ids": [citation.id],
                    "track_id": citation.track_id,
                }
            )
    return {
        "schema_version": BRIEF_SCHEMA_VERSION,
        "title": plan.question,
        "subtitle": "공식자료의 확인 가능한 원문 구간을 정리한 공공업무 조사 브리프",
        "executive_summary": highlights,
        "key_findings": findings,
        "implications": [],
        "recommendations": [],
        "open_questions": [str(value) for value in gaps],
    }


def load_brief(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BriefValidationError("brief file must contain one JSON object")
    return payload


def validate_brief(
    payload: Dict[str, Any],
    *,
    citation_ids: Iterable[str],
) -> Dict[str, Any]:
    """Validate and normalize a brief while preserving deterministic ordering."""

    known = set(citation_ids)
    schema_version = _text(payload.get("schema_version"), "schema_version", 20)
    if schema_version != BRIEF_SCHEMA_VERSION:
        raise BriefValidationError(
            f"unsupported brief schema_version: {schema_version}; expected {BRIEF_SCHEMA_VERSION}"
        )
    normalized: Dict[str, Any] = {
        "schema_version": schema_version,
        "title": _text(payload.get("title"), "title", 300),
        "subtitle": _optional_text(payload.get("subtitle"), "subtitle", 500),
    }
    normalized["executive_summary"] = _items(
        payload.get("executive_summary", []),
        field="executive_summary",
        known=known,
        require_id=False,
        max_items=5,
    )
    normalized["key_findings"] = _items(
        payload.get("key_findings", []),
        field="key_findings",
        known=known,
        require_id=True,
        max_items=20,
    )
    normalized["implications"] = _items(
        payload.get("implications", []),
        field="implications",
        known=known,
        require_id=False,
        max_items=20,
    )
    normalized["recommendations"] = _items(
        payload.get("recommendations", []),
        field="recommendations",
        known=known,
        require_id=False,
        max_items=20,
    )
    open_questions = payload.get("open_questions", [])
    if not isinstance(open_questions, list):
        raise BriefValidationError("open_questions must be an array")
    normalized["open_questions"] = [
        _text(value, f"open_questions[{index}]", 1_000)
        for index, value in enumerate(open_questions)
    ][:50]
    return normalized


def _items(
    value: Any,
    *,
    field: str,
    known: set[str],
    require_id: bool,
    max_items: int,
) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise BriefValidationError(f"{field} must be an array")
    if len(value) > max_items:
        raise BriefValidationError(f"{field} must contain at most {max_items} items")
    result = []
    seen_ids = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise BriefValidationError(f"{field}[{index}] must be an object")
        item_path = f"{field}[{index}]"
        kind = _text(raw.get("kind"), f"{item_path}.kind", 30).upper()
        if kind not in ALLOWED_KINDS:
            raise BriefValidationError(
                f"{item_path}.kind must be FACT, INFERENCE, or RECOMMENDATION"
            )
        citation_values = raw.get("citation_ids", [])
        if not isinstance(citation_values, list):
            raise BriefValidationError(f"{item_path}.citation_ids must be an array")
        citation_list = [
            _text(citation_id, f"{item_path}.citation_ids", 100)
            for citation_id in citation_values
        ]
        unknown = sorted(set(citation_list) - known)
        if unknown:
            raise BriefValidationError(
                f"{item_path} references unknown citation IDs: {', '.join(unknown)}"
            )
        if kind in {"FACT", "INFERENCE"} and not citation_list:
            raise BriefValidationError(f"{item_path} kind={kind} requires citation_ids")
        item: Dict[str, Any] = {
            "kind": kind,
            "text": _text(raw.get("text"), f"{item_path}.text", 4_000),
            "citation_ids": list(dict.fromkeys(citation_list)),
        }
        title = _optional_text(raw.get("title"), f"{item_path}.title", 300)
        if title:
            item["title"] = title
        track_id = _optional_text(raw.get("track_id"), f"{item_path}.track_id", 100)
        if track_id:
            item["track_id"] = track_id
        if require_id:
            item_id = _text(raw.get("id"), f"{item_path}.id", 100)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", item_id):
                raise BriefValidationError(
                    f"{item_path}.id must use letters, numbers, hyphen, or underscore"
                )
            if item_id in seen_ids:
                raise BriefValidationError(f"duplicate key_findings id: {item_id}")
            seen_ids.add(item_id)
            item["id"] = item_id
        result.append(item)
    return result


def _text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise BriefValidationError(f"{field} must be a string")
    normalized = " ".join(value.split())
    if not normalized:
        raise BriefValidationError(f"{field} must not be empty")
    if len(normalized) > limit:
        raise BriefValidationError(f"{field} exceeds {limit} characters")
    return normalized


def _optional_text(value: Any, field: str, limit: int) -> str:
    if value is None:
        return ""
    return _text(value, field, limit)


def _shorten(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"
