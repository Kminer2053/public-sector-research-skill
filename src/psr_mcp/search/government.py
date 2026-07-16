"""Deterministic Government Profile query generation."""

from __future__ import annotations

import hashlib

from psr_mcp.planner.models import ResearchPlan, ResearchTrack
from psr_mcp.search.models import SearchQuery


class GovernmentQueryBuilder:
    def __init__(
        self,
        *,
        max_query_chars: int = 400,
        max_query_words: int = 50,
        max_results_per_track: int = 5,
    ) -> None:
        if max_query_chars < 64 or max_query_chars > 2_048:
            raise ValueError("max_query_chars must be 64..2048")
        if max_query_words < 10 or max_query_words > 100:
            raise ValueError("max_query_words must be 10..100")
        if max_results_per_track < 1 or max_results_per_track > 20:
            raise ValueError("max_results_per_track must be 1..20")
        self._max_query_chars = max_query_chars
        self._max_query_words = max_query_words
        self._max_results_per_track = max_results_per_track

    def build(self, plan: ResearchPlan) -> tuple[SearchQuery, ...]:
        if plan.profile != "government-v0":
            raise ValueError("GovernmentQueryBuilder requires government-v0")
        return tuple(self._query(plan, track) for track in plan.tracks)

    def _query(self, plan: ResearchPlan, track: ResearchTrack) -> SearchQuery:
        domains = _TRACK_DOMAINS.get(track.id, _DEFAULT_DOMAINS)
        evidence_terms = " ".join(track.evidence_types)
        domain_terms = " OR ".join(f"site:{domain}" for domain in domains)
        suffix = (
            f" {track.title} {evidence_terms} 기준일 {plan.as_of_date.isoformat()} ({domain_terms})"
        )
        suffix_words = suffix.split()
        question_word_limit = self._max_query_words - len(suffix_words)
        if question_word_limit < 1:
            raise ValueError("official-domain query suffix exceeds max_query_words")
        question = " ".join(plan.question.split()[:question_word_limit])
        question_limit = max(1, self._max_query_chars - len(suffix))
        text = f"{question[:question_limit].rstrip()}{suffix}"
        if len(text) > self._max_query_chars:
            raise ValueError("official-domain query suffix exceeds max_query_chars")
        digest = hashlib.sha256(f"{track.id}\0{text}".encode()).hexdigest()[:16]
        return SearchQuery(
            id=f"qry-{digest}",
            track_id=track.id,
            research_question=plan.question,
            text=text,
            preferred_domains=domains,
            max_results=self._max_results_per_track,
        )


_DEFAULT_DOMAINS = ("korea.kr", "go.kr")
_TRACK_DOMAINS: dict[str, tuple[str, ...]] = {
    "law-regulation": ("law.go.kr", "moleg.go.kr"),
    "government-policy": ("korea.kr", "mois.go.kr", "nia.or.kr"),
    "procurement": ("pps.go.kr", "g2b.go.kr"),
    "privacy": ("pipc.go.kr", "privacy.go.kr"),
    "international-standards": ("oecd.org", "nist.gov", "iso.org"),
    "vendor-lock-in": ("pps.go.kr", "g2b.go.kr", "gov.uk"),
    "data-rights": ("pipc.go.kr", "pps.go.kr", "nia.or.kr"),
}
