"""Framework-independent values shared by the local research workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ResearchTrack:
    id: str
    title: str
    research_question: str
    evidence_types: List[str]
    source_tiers: List[str]
    preferred_domains: List[str]
    selection_terms: List[str]


@dataclass(frozen=True)
class StopConditions:
    max_sources: int
    max_bytes: int
    timeout_seconds: float
    require_official_primary: bool


@dataclass(frozen=True)
class ResearchPlan:
    id: str
    question: str
    as_of_date: str
    jurisdiction: str
    profile: str
    tracks: List[ResearchTrack]
    search_queries: List[Dict[str, Any]]
    completion_criteria: List[str]
    stop_conditions: StopConditions

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchPlan":
        return cls(
            id=str(payload["id"]),
            question=str(payload["question"]),
            as_of_date=str(payload["as_of_date"]),
            jurisdiction=str(payload["jurisdiction"]),
            profile=str(payload["profile"]),
            tracks=[ResearchTrack(**track) for track in payload["tracks"]],
            search_queries=list(payload["search_queries"]),
            completion_criteria=list(payload["completion_criteria"]),
            stop_conditions=StopConditions(**payload["stop_conditions"]),
        )


@dataclass(frozen=True)
class SourceInput:
    track_id: str
    url: Optional[str] = None
    path: Optional[str] = None
    title: Optional[str] = None
    publisher: Optional[str] = None
    source_tier: str = "UNVERIFIED_WEB"
    published_at: Optional[str] = None

    def __post_init__(self) -> None:
        if bool(self.url) == bool(self.path):
            raise ValueError("source must contain exactly one of url or path")
        if self.published_at is not None:
            date.fromisoformat(self.published_at)

    @property
    def locator(self) -> str:
        return self.url or self.path or ""


@dataclass(frozen=True)
class CollectedDocument:
    requested_locator: str
    final_locator: str
    status: int
    headers: Dict[str, str]
    media_type: Optional[str]
    body: bytes
    sha256: str
    retrieved_at: str
    warnings: List[str]


@dataclass(frozen=True)
class Passage:
    id: str
    text: str
    locator: str
    heading: Optional[str] = None


@dataclass(frozen=True)
class ParsedDocument:
    kind: str
    title: Optional[str]
    passages: List[Passage]
    warnings: List[str]


@dataclass(frozen=True)
class ScoreComponent:
    value: float
    explanation: str


@dataclass(frozen=True)
class EvidenceScore:
    overall: float
    authority: ScoreComponent
    primary_source: ScoreComponent
    direct_relevance: ScoreComponent
    original_snapshot: ScoreComponent
    specificity: ScoreComponent
    freshness: ScoreComponent
    independence: ScoreComponent

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Citation:
    id: str
    run_id: str
    track_id: str
    passage_id: str
    title: str
    publisher: str
    source_locator: str
    retrieved_at: str
    locator: str
    excerpt: str
    source_tier: str
    document_sha256: str
    score: EvidenceScore
    local_snapshot_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Failure:
    source_locator: str
    track_id: str
    code: str
    message: str
    retryable: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StoredDocument:
    source_id: str
    document_id: str
    snapshot_id: str
    title: str
    publisher: str
    source_tier: str
    source_locator: str
    published_at: Optional[str]
    collected: CollectedDocument
    parsed: ParsedDocument
    reused: bool = False


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    summary: str
    citations: List[Citation]
    gaps: List[str]
    failures: List[Failure]
    reused_sources: int
    collected_sources: int
    report_path: str
    result_path: str
    html_report_path: str = ""
    brief_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["citations"] = [citation.to_dict() for citation in self.citations]
        payload["failures"] = [failure.to_dict() for failure in self.failures]
        return payload


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    return date.fromisoformat(value)
