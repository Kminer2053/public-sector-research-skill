"""Deterministic public-sector research planning."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Dict, List

from psr_core.models import ResearchPlan, ResearchTrack, StopConditions


def build_plan(
    *,
    question: str,
    as_of_date: date,
    jurisdiction: str,
    profile: Dict[str, Any],
    max_sources: int,
    max_bytes: int,
    timeout_seconds: float,
) -> ResearchPlan:
    normalized = " ".join(question.split())
    if len(normalized) < 10 or len(normalized) > 4_000:
        raise ValueError("question must contain 10..4000 characters")
    jurisdictions = profile.get("jurisdictions", [])
    if jurisdictions and jurisdiction not in jurisdictions:
        raise ValueError(
            f"profile {profile['id']} does not declare jurisdiction {jurisdiction}"
        )
    if max_sources < 1 or max_sources > 100:
        raise ValueError("max_sources must be 1..100")
    if max_bytes < 1_024 or max_bytes > 500 * 1024 * 1024:
        raise ValueError("max_bytes must be 1024..524288000")
    if timeout_seconds < 1 or timeout_seconds > 3_600:
        raise ValueError("timeout_seconds must be 1..3600")

    tracks = list(profile["tracks"])
    lowered = normalized.casefold()
    for conditional in profile.get("conditional_tracks", []):
        if any(str(keyword).casefold() in lowered for keyword in conditional["keywords"]):
            tracks.append(conditional["track"])
    tracks = _deduplicate_tracks(tracks)
    research_tracks = [_track(track) for track in tracks]
    queries = [_query(normalized, as_of_date, track) for track in research_tracks]
    digest = hashlib.sha256(
        (
            str(profile["id"])
            + "\0"
            + jurisdiction
            + "\0"
            + as_of_date.isoformat()
            + "\0"
            + normalized
        ).encode("utf-8")
    ).hexdigest()[:16]
    return ResearchPlan(
        id=f"run-{as_of_date.strftime('%Y%m%d')}-{digest}",
        question=normalized,
        as_of_date=as_of_date.isoformat(),
        jurisdiction=jurisdiction,
        profile=str(profile["id"]),
        tracks=research_tracks,
        search_queries=queries,
        completion_criteria=[str(value) for value in profile["completion_criteria"]],
        stop_conditions=StopConditions(
            max_sources=max_sources,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
            require_official_primary=True,
        ),
    )


def _track(payload: Dict[str, Any]) -> ResearchTrack:
    return ResearchTrack(
        id=str(payload["id"]),
        title=str(payload["title"]),
        research_question=str(payload["research_question"]),
        evidence_types=[str(value) for value in payload["evidence_types"]],
        source_tiers=[str(value) for value in payload["source_tiers"]],
        preferred_domains=[str(value) for value in payload["preferred_domains"]],
        selection_terms=[str(value) for value in payload["selection_terms"]],
    )


def _query(question: str, as_of_date: date, track: ResearchTrack) -> Dict[str, Any]:
    domain_terms = " OR ".join(f"site:{domain}" for domain in track.preferred_domains)
    evidence_terms = " ".join(track.evidence_types)
    text = (
        f"{question} {track.title} {evidence_terms} "
        f"기준일 {as_of_date.isoformat()} ({domain_terms})"
    )
    return {
        "track_id": track.id,
        "research_question": track.research_question,
        "query": text[:800],
        "preferred_domains": track.preferred_domains,
        "preferred_source_tiers": track.source_tiers,
    }


def _deduplicate_tracks(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for track in tracks:
        track_id = str(track["id"])
        if track_id in seen:
            continue
        seen.add(track_id)
        result.append(track)
    return result
