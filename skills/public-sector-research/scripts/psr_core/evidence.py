"""Explainable passage selection, scoring, and citation composition."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Sequence, Tuple

from psr_core.models import (
    Citation,
    EvidenceScore,
    Passage,
    ResearchPlan,
    ScoreComponent,
    SourceInput,
    StoredDocument,
    parse_date,
)


@dataclass(frozen=True)
class EvidenceSelection:
    source: SourceInput
    document: StoredDocument
    passage: Passage
    relevance: float
    terms: Sequence[str]


def compose_citations(
    *,
    run_id: str,
    plan: ResearchPlan,
    documents: Sequence[Tuple[SourceInput, StoredDocument]],
    max_citations: int = 20,
    max_per_document: int = 3,
) -> Tuple[List[Citation], List[str], int]:
    track_map = {track.id: track for track in plan.tracks}
    question_terms = _terms(plan.question)
    selections: List[EvidenceSelection] = []
    for source, document in documents:
        track = track_map[source.track_id]
        terms = sorted(set(question_terms + [_normalize(value) for value in track.selection_terms]))
        scored = [
            EvidenceSelection(
                source=source,
                document=document,
                passage=passage,
                relevance=_relevance(passage, terms),
                terms=terms,
            )
            for passage in document.parsed.passages
        ]
        relevant = [selection for selection in scored if selection.relevance > 0]
        pool = relevant or scored[:1]
        selections.extend(
            sorted(
                pool,
                key=lambda value: (value.relevance, value.passage.locator),
                reverse=True,
            )[:max_per_document]
        )

    ranked = sorted(
        selections,
        key=lambda value: (
            value.relevance,
            _authority(value.document.source_tier),
            value.passage.locator,
        ),
        reverse=True,
    )
    unique: Dict[Tuple[str, str], EvidenceSelection] = {}
    deduplicated = 0
    for selection in ranked:
        key = (
            selection.source.track_id,
            hashlib.sha256(_normalize(selection.passage.text).encode("utf-8")).hexdigest(),
        )
        existing = unique.get(key)
        if existing is None:
            unique[key] = selection
            continue
        deduplicated += 1
        if _authority(selection.document.source_tier) > _authority(
            existing.document.source_tier
        ):
            unique[key] = selection
    balanced = _balance_tracks(list(unique.values()), max_citations)
    citations = [_citation(run_id, plan, selection) for selection in balanced]
    represented = {citation.track_id for citation in citations}
    gaps = [
        f"{track.title}({track.id}) track에 인용 가능한 원문 구간이 없습니다."
        for track in plan.tracks
        if track.id not in represented
    ]
    return citations, gaps, deduplicated


def _citation(
    run_id: str,
    plan: ResearchPlan,
    selection: EvidenceSelection,
) -> Citation:
    document = selection.document
    passage = selection.passage
    citation_id = (
        "cit-"
        + hashlib.sha256(
            f"{run_id}\0{selection.source.track_id}\0{passage.id}".encode("utf-8")
        ).hexdigest()[:20]
    )
    return Citation(
        id=citation_id,
        run_id=run_id,
        track_id=selection.source.track_id,
        passage_id=passage.id,
        title=document.title,
        publisher=document.publisher,
        source_locator=document.source_locator,
        retrieved_at=document.collected.retrieved_at,
        locator=passage.locator,
        excerpt=_excerpt(passage.text, selection.terms, 500),
        source_tier=document.source_tier,
        document_sha256=document.collected.sha256,
        score=_score(plan, selection),
    )


def _score(plan: ResearchPlan, selection: EvidenceSelection) -> EvidenceScore:
    tier = selection.document.source_tier
    authority = _authority(tier)
    primary = _primary(tier)
    direct = round(min(1.0, 0.2 + selection.relevance * 0.15), 4)
    specificity = 1.0 if selection.passage.locator else 0.2
    published_at = parse_date(selection.document.published_at)
    if published_at is None:
        freshness = 0.5
        freshness_explanation = "발행일 미확인; 수집시점만 확인됨"
    else:
        age_days = max(0, (date.fromisoformat(plan.as_of_date) - published_at).days)
        freshness = max(0.2, 1.0 - age_days / 3_650)
        freshness_explanation = f"기준일 대비 {age_days}일 경과"
    original_snapshot = 1.0
    independence = 0.5
    overall = round(
        authority * 0.25
        + primary * 0.15
        + direct * 0.20
        + original_snapshot * 0.15
        + specificity * 0.10
        + freshness * 0.10
        + independence * 0.05,
        4,
    )
    return EvidenceScore(
        overall=overall,
        authority=ScoreComponent(authority, f"source tier={tier}"),
        primary_source=ScoreComponent(
            primary,
            "1차 또는 공식 원문" if primary >= 0.95 else "공식 1차자료 여부가 제한적임",
        ),
        direct_relevance=ScoreComponent(
            direct,
            f"질문·track 핵심어 {int(selection.relevance)}개 일치",
        ),
        original_snapshot=ScoreComponent(
            original_snapshot,
            f"원문 snapshot hash={selection.document.collected.sha256[:12]}",
        ),
        specificity=ScoreComponent(
            specificity,
            f"locator={selection.passage.locator}",
        ),
        freshness=ScoreComponent(freshness, freshness_explanation),
        independence=ScoreComponent(
            independence,
            "재인용·계보 그래프 도입 전까지 독립성은 미확정",
        ),
    )


def _balance_tracks(
    selections: List[EvidenceSelection],
    max_citations: int,
) -> List[EvidenceSelection]:
    selections.sort(
        key=lambda value: (
            value.relevance,
            _authority(value.document.source_tier),
            value.passage.locator,
        ),
        reverse=True,
    )
    representatives: List[EvidenceSelection] = []
    remaining: List[EvidenceSelection] = []
    represented = set()
    for selection in selections:
        track_id = selection.source.track_id
        if track_id in represented:
            remaining.append(selection)
        else:
            represented.add(track_id)
            representatives.append(selection)
    return (representatives + remaining)[:max_citations]


def _relevance(passage: Passage, terms: Sequence[str]) -> float:
    haystack = _normalize(f"{passage.heading or ''} {passage.text}")
    compact = _compact(haystack)
    return float(
        sum(term in haystack or _compact(term) in compact for term in terms if term)
    )


def _terms(value: str) -> List[str]:
    return [
        token.casefold()
        for token in re.findall(r"[0-9A-Za-z가-힣_-]{2,}", value)
        if token.casefold() not in _STOP_TERMS
    ]


def _excerpt(text: str, terms: Sequence[str], limit: int) -> str:
    cleaned = " ".join(text.split())
    lowered = cleaned.casefold()
    if len(cleaned) <= limit:
        return cleaned
    positions = [position for term in terms if (position := lowered.find(term)) >= 0]
    if not positions:
        return cleaned[: limit - 1] + "…"
    center = min(positions)
    start = max(0, center - limit // 3)
    end = min(len(cleaned), start + limit)
    start = max(0, end - limit)
    excerpt = cleaned[start:end]
    if start:
        excerpt = "…" + excerpt[1:]
    if end < len(cleaned):
        excerpt = excerpt[:-1] + "…"
    return excerpt


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _compact(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def _authority(tier: str) -> float:
    return {
        "OFFICIAL_PRIMARY": 1.0,
        "OFFICIAL_SECONDARY": 0.8,
        "ACADEMIC_PRIMARY": 0.9,
        "COMPANY_OFFICIAL": 0.75,
        "REPUTABLE_MEDIA": 0.5,
        "COMMUNITY": 0.2,
        "UNVERIFIED_WEB": 0.1,
        "LOCAL_FILE": 0.4,
    }.get(tier, 0.1)


def _primary(tier: str) -> float:
    return {
        "OFFICIAL_PRIMARY": 1.0,
        "OFFICIAL_SECONDARY": 0.7,
        "ACADEMIC_PRIMARY": 1.0,
        "COMPANY_OFFICIAL": 1.0,
        "REPUTABLE_MEDIA": 0.4,
        "COMMUNITY": 0.2,
        "UNVERIFIED_WEB": 0.1,
        "LOCAL_FILE": 0.5,
    }.get(tier, 0.1)


_STOP_TERMS = {
    "그리고",
    "대한",
    "위한",
    "관련",
    "무엇",
    "어떻게",
    "있는",
    "한다",
    "the",
    "and",
    "for",
    "with",
}
