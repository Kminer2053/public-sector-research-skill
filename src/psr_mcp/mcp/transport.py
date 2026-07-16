"""Shared MCP transport security settings for all service modes."""

from __future__ import annotations

from urllib.parse import urlparse

from mcp.server.transport_security import TransportSecuritySettings

from psr_mcp.config import Settings


def transport_security(settings: Settings) -> TransportSecuritySettings:
    parsed = urlparse(settings.public_url)
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("public URL hostname is required")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    allowed_hosts = [hostname, f"{hostname}:*", "127.0.0.1:*", "localhost:*"]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(set(allowed_hosts)),
        allowed_origins=[origin],
    )
