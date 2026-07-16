"""Framework-independent evidence values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from psr_mcp.collectors.models import CollectedDocument
from psr_mcp.parsers.models import ParsedDocument
from psr_mcp.search.models import SourceCandidate, SourceTier


@dataclass(frozen=True, slots=True)
class EvidenceDocument:
    candidate: SourceCandidate
    collected: CollectedDocument
    parsed: ParsedDocument


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    value: float
    explanation: str


@dataclass(frozen=True, slots=True)
class EvidenceScore:
    overall: float
    authority: ScoreComponent
    primary_source: ScoreComponent
    direct_relevance: ScoreComponent
    original_snapshot: ScoreComponent
    specificity: ScoreComponent
    freshness: ScoreComponent
    independence: ScoreComponent


@dataclass(frozen=True, slots=True)
class EvidenceCitation:
    id: str
    track_id: str
    title: str
    publisher: str
    url: str
    retrieved_at: datetime
    locator: str
    excerpt: str
    source_tier: SourceTier
    document_sha256: str
    score: EvidenceScore


@dataclass(frozen=True, slots=True)
class EvidencePack:
    citations: tuple[EvidenceCitation, ...]
    gaps: tuple[str, ...]
    deduplicated_count: int


@dataclass(frozen=True, slots=True)
class EvidenceFinding:
    claim: str
    kind: Literal["FACT", "INFERENCE", "RECOMMENDATION"]
    citation_ids: tuple[str, ...]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True, slots=True)
class EvidenceRecommendationGap:
    track_id: str
    missing_anchors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceWriting:
    findings: tuple[EvidenceFinding, ...]
    recommendation_gaps: tuple[EvidenceRecommendationGap, ...]
