"""Deterministic passage selection with explainable component scores."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from psr_mcp.evidence.models import (
    EvidenceCitation,
    EvidenceDocument,
    EvidencePack,
    EvidenceScore,
    ScoreComponent,
)
from psr_mcp.parsers.models import Passage
from psr_mcp.search.models import SourceTier


class EvidenceComposer:
    def __init__(
        self,
        *,
        max_citations: int = 12,
        max_per_document: int = 3,
        max_excerpt_chars: int = 500,
    ) -> None:
        if max_citations < 1 or max_citations > 100:
            raise ValueError("max_citations must be 1..100")
        if max_per_document < 1 or max_per_document > 20:
            raise ValueError("max_per_document must be 1..20")
        if max_excerpt_chars < 100 or max_excerpt_chars > 1_000:
            raise ValueError("max_excerpt_chars must be 100..1000")
        self._max_citations = max_citations
        self._max_per_document = max_per_document
        self._max_excerpt_chars = max_excerpt_chars

    def compose(
        self,
        *,
        question: str,
        as_of_date: date,
        documents: tuple[EvidenceDocument, ...],
    ) -> EvidencePack:
        if not documents:
            return EvidencePack(
                citations=(),
                gaps=("수집·파싱에 성공한 공식 문서가 없습니다.",),
                deduplicated_count=0,
            )
        terms = _terms(question)
        selections: list[_Selection] = []
        gaps: list[str] = []
        for document in documents:
            passages = self._select_document(document, terms)
            if not passages:
                gaps.append(f"{document.candidate.publisher}: 관련 Passage를 선택하지 못했습니다.")
                continue
            selections.extend(passages)

        ranked = sorted(
            selections,
            key=lambda selection: (
                selection.relevance,
                _authority_value(selection.document.candidate.source_tier),
                selection.passage.locator,
            ),
            reverse=True,
        )
        unique: dict[str, _Selection] = {}
        deduplicated = 0
        for selection in ranked:
            key = _text_key(selection.passage.text)
            existing = unique.get(key)
            if existing is None:
                unique[key] = selection
                continue
            deduplicated += 1
            if _authority_value(selection.document.candidate.source_tier) > _authority_value(
                existing.document.candidate.source_tier
            ):
                unique[key] = selection
        ranked_unique = sorted(
            unique.values(),
            key=lambda selection: (
                selection.relevance,
                _authority_value(selection.document.candidate.source_tier),
                selection.passage.locator,
            ),
            reverse=True,
        )
        final = _balance_tracks(ranked_unique, self._max_citations)
        citations = tuple(self._citation(selection, terms, as_of_date) for selection in final)
        return EvidencePack(
            citations=citations,
            gaps=tuple(gaps),
            deduplicated_count=deduplicated,
        )

    def _select_document(
        self,
        document: EvidenceDocument,
        terms: frozenset[str],
    ) -> list[_Selection]:
        scored = [
            _Selection(
                document=document,
                passage=passage,
                relevance=_relevance(passage, terms),
            )
            for passage in document.parsed.passages
        ]
        if not scored:
            return []
        relevant = [selection for selection in scored if selection.relevance > 0]
        pool = relevant or scored[:1]
        return sorted(
            pool,
            key=lambda selection: (selection.relevance, selection.passage.locator),
            reverse=True,
        )[: self._max_per_document]

    def _citation(
        self,
        selection: _Selection,
        terms: frozenset[str],
        as_of_date: date,
    ) -> EvidenceCitation:
        document = selection.document
        passage = selection.passage
        excerpt = passage.text[: self._max_excerpt_chars]
        citation_id = (
            "cit-"
            + hashlib.sha256(
                (
                    document.collected.final_url
                    + "\0"
                    + document.collected.sha256
                    + "\0"
                    + passage.locator
                ).encode("utf-8")
            ).hexdigest()[:16]
        )
        return EvidenceCitation(
            id=citation_id,
            track_id=document.candidate.track_id,
            title=document.candidate.title,
            publisher=document.candidate.publisher,
            url=document.collected.final_url,
            retrieved_at=document.collected.retrieved_at,
            locator=passage.locator,
            excerpt=excerpt,
            source_tier=document.candidate.source_tier,
            document_sha256=document.collected.sha256,
            score=_score(
                document=document,
                passage=passage,
                terms=terms,
                as_of_date=as_of_date,
                relevance=selection.relevance,
            ),
        )


@dataclass(frozen=True, slots=True)
class _Selection:
    document: EvidenceDocument
    passage: Passage
    relevance: float


def _score(
    *,
    document: EvidenceDocument,
    passage: Passage,
    terms: frozenset[str],
    as_of_date: date,
    relevance: float,
) -> EvidenceScore:
    tier = document.candidate.source_tier
    authority_value = _authority_value(tier)
    primary_value = _PRIMARY_VALUES[tier]
    direct_value = min(1.0, 0.2 + relevance / max(1, len(terms)))
    specificity_value = 1.0 if passage.locator else 0.2
    if document.candidate.published_at is None:
        freshness_value = 0.5
        freshness_explanation = "발행일 미확인; 수집시점만 확인됨"
    else:
        age_days = max(0, (as_of_date - document.candidate.published_at).days)
        freshness_value = max(0.2, 1.0 - age_days / 3_650)
        freshness_explanation = f"기준일 대비 {age_days}일 경과"
    components = {
        "authority": authority_value,
        "primary_source": primary_value,
        "direct_relevance": direct_value,
        "original_snapshot": 1.0,
        "specificity": specificity_value,
        "freshness": freshness_value,
        "independence": 0.5,
    }
    overall = round(
        components["authority"] * 0.25
        + components["primary_source"] * 0.15
        + components["direct_relevance"] * 0.2
        + components["original_snapshot"] * 0.15
        + components["specificity"] * 0.1
        + components["freshness"] * 0.1
        + components["independence"] * 0.05,
        4,
    )
    return EvidenceScore(
        overall=overall,
        authority=ScoreComponent(
            authority_value,
            f"source tier={tier.value}",
        ),
        primary_source=ScoreComponent(
            primary_value,
            "1차 또는 공식 원문" if primary_value == 1.0 else "공식 1차자료 아님",
        ),
        direct_relevance=ScoreComponent(
            direct_value,
            f"질문 핵심어 {int(relevance)}개 일치",
        ),
        original_snapshot=ScoreComponent(
            1.0,
            f"원문 snapshot hash={document.collected.sha256[:12]}",
        ),
        specificity=ScoreComponent(
            specificity_value,
            f"locator={passage.locator}",
        ),
        freshness=ScoreComponent(
            freshness_value,
            freshness_explanation,
        ),
        independence=ScoreComponent(
            0.5,
            "독립성은 provenance graph 전까지 미확정",
        ),
    )


def _relevance(passage: Passage, terms: frozenset[str]) -> float:
    haystack = f"{passage.heading or ''} {passage.text}".casefold()
    return float(sum(term in haystack for term in terms))


def _terms(question: str) -> frozenset[str]:
    return frozenset(
        token.casefold()
        for token in re.findall(r"[0-9A-Za-z가-힣_-]{2,}", question)
        if token.casefold() not in _STOP_TERMS
    )


def _text_key(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _balance_tracks(
    selections: list[_Selection],
    max_citations: int,
) -> list[_Selection]:
    representatives: list[_Selection] = []
    remaining: list[_Selection] = []
    represented_tracks: set[str] = set()
    for selection in selections:
        track_id = selection.document.candidate.track_id
        if track_id in represented_tracks:
            remaining.append(selection)
            continue
        represented_tracks.add(track_id)
        representatives.append(selection)
    return (representatives + remaining)[:max_citations]


def _authority_value(tier: SourceTier) -> float:
    return _AUTHORITY_VALUES[tier]


_PRIMARY_VALUES = {
    SourceTier.TEST_FIXTURE: 0.0,
    SourceTier.UNVERIFIED_WEB: 0.1,
    SourceTier.OFFICIAL_PRIMARY: 1.0,
    SourceTier.OFFICIAL_SECONDARY: 0.7,
    SourceTier.ACADEMIC_PRIMARY: 1.0,
    SourceTier.COMPANY_OFFICIAL: 1.0,
    SourceTier.REPUTABLE_MEDIA: 0.4,
    SourceTier.COMMUNITY: 0.2,
}
_AUTHORITY_VALUES = {
    SourceTier.TEST_FIXTURE: 0.0,
    SourceTier.UNVERIFIED_WEB: 0.1,
    SourceTier.OFFICIAL_PRIMARY: 1.0,
    SourceTier.OFFICIAL_SECONDARY: 0.8,
    SourceTier.ACADEMIC_PRIMARY: 0.9,
    SourceTier.COMPANY_OFFICIAL: 0.75,
    SourceTier.REPUTABLE_MEDIA: 0.5,
    SourceTier.COMMUNITY: 0.2,
}
_STOP_TERMS = frozenset(
    {
        "공공기관",
        "공식자료",
        "중심으로",
        "조사해줘",
        "알려줘",
        "원칙",
        "대한",
        "위한",
        "the",
        "and",
        "for",
    }
)
