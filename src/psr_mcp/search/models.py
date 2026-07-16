"""Search query, candidate, and failure values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class SourceTier(StrEnum):
    TEST_FIXTURE = "TEST_FIXTURE"
    UNVERIFIED_WEB = "UNVERIFIED_WEB"
    OFFICIAL_PRIMARY = "OFFICIAL_PRIMARY"
    OFFICIAL_SECONDARY = "OFFICIAL_SECONDARY"
    ACADEMIC_PRIMARY = "ACADEMIC_PRIMARY"
    COMPANY_OFFICIAL = "COMPANY_OFFICIAL"
    REPUTABLE_MEDIA = "REPUTABLE_MEDIA"
    COMMUNITY = "COMMUNITY"


@dataclass(frozen=True, slots=True)
class SearchQuery:
    id: str
    track_id: str
    research_question: str
    text: str
    preferred_domains: tuple[str, ...]
    max_results: int


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    id: str
    track_id: str
    url: str
    title: str
    publisher: str
    source_tier: SourceTier
    published_at: date | None = None


@dataclass(frozen=True, slots=True)
class SearchFailure:
    query_id: str
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class SearchResult:
    candidates: tuple[SourceCandidate, ...]
    failures: tuple[SearchFailure, ...] = ()
