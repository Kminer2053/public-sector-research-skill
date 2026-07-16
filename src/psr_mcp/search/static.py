"""Deterministic in-memory SearchProvider for tests and development fixtures."""

from __future__ import annotations

from collections.abc import Mapping

from psr_mcp.search.models import SearchQuery, SearchResult


class StaticSearchProvider:
    """Return predeclared candidates without performing network access."""

    def __init__(self, results_by_track: Mapping[str, SearchResult]) -> None:
        self._results_by_track = dict(results_by_track)

    async def search(self, query: SearchQuery) -> SearchResult:
        return self._results_by_track.get(query.track_id, SearchResult(candidates=()))
