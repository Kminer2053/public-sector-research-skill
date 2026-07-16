"""Safe public-source collection boundaries."""

from psr_mcp.collectors.access_policy import (
    AllowAllSourceAccessPolicy,
    RobotsSourceAccessPolicy,
    SourceAccessDecision,
    SourceAccessPolicy,
    SourceAccessStatus,
)
from psr_mcp.collectors.httpcore_transport import PinnedHttpcoreTransport
from psr_mcp.collectors.models import CollectedDocument, CollectionLimits
from psr_mcp.collectors.safe import CollectionError, CollectionErrorCode, SafeCollector
from psr_mcp.collectors.url_policy import (
    SystemHostResolver,
    UrlPolicy,
    UrlPolicyError,
    UrlPolicyErrorCode,
    ValidatedUrl,
)

__all__ = [
    "AllowAllSourceAccessPolicy",
    "CollectedDocument",
    "CollectionError",
    "CollectionErrorCode",
    "CollectionLimits",
    "PinnedHttpcoreTransport",
    "RobotsSourceAccessPolicy",
    "SafeCollector",
    "SourceAccessDecision",
    "SourceAccessPolicy",
    "SourceAccessStatus",
    "SystemHostResolver",
    "UrlPolicy",
    "UrlPolicyError",
    "UrlPolicyErrorCode",
    "ValidatedUrl",
]
