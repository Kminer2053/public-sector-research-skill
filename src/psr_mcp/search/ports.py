"""Search provider port; vendor adapters remain outside planning logic."""

from __future__ import annotations

from typing import Protocol

from psr_mcp.search.models import SearchQuery, SearchResult


class SearchProvider(Protocol):
    async def search(self, query: SearchQuery) -> SearchResult: ...
