"""Provider-neutral official-first search contracts."""

from psr_mcp.search.brave import BraveSearchProvider
from psr_mcp.search.curated import CuratedOfficialSourceProvider, CuratedSourceSeed
from psr_mcp.search.government import GovernmentQueryBuilder
from psr_mcp.search.models import (
    SearchFailure,
    SearchQuery,
    SearchResult,
    SourceCandidate,
    SourceTier,
)
from psr_mcp.search.ports import SearchProvider
from psr_mcp.search.registry import (
    GovernmentSourceRegistry,
    SourceIdentity,
    SourceRule,
)
from psr_mcp.search.static import StaticSearchProvider

__all__ = [
    "BraveSearchProvider",
    "CuratedOfficialSourceProvider",
    "CuratedSourceSeed",
    "GovernmentQueryBuilder",
    "GovernmentSourceRegistry",
    "SearchFailure",
    "SearchProvider",
    "SearchQuery",
    "SearchResult",
    "SourceCandidate",
    "SourceIdentity",
    "SourceRule",
    "SourceTier",
    "StaticSearchProvider",
]
