"""Framework-independent research plan values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ResearchTrack:
    id: str
    title: str
    research_question: str
    evidence_types: tuple[str, ...]
    source_tiers: tuple[str, ...]
    selection_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StopConditions:
    max_sources: int
    max_bytes: int
    timeout_seconds: float
    require_official_primary: bool


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    question: str
    as_of_date: date
    jurisdiction: str
    profile: str
    tracks: tuple[ResearchTrack, ...]
    completion_criteria: tuple[str, ...]
    stop_conditions: StopConditions
