"""Government profile source classification by authoritative domain."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from psr_mcp.search.models import SourceTier


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    publisher: str
    source_tier: SourceTier
    matched_domain: str | None


@dataclass(frozen=True, slots=True)
class SourceRule:
    domain: str
    publisher: str
    source_tier: SourceTier
    path_prefix: str | None = None


class GovernmentSourceRegistry:
    def __init__(self, rules: tuple[SourceRule, ...] | None = None) -> None:
        configured = rules or _DEFAULT_RULES
        self._rules = tuple(
            sorted(
                configured,
                key=lambda rule: (
                    len(rule.domain),
                    len(rule.path_prefix or ""),
                ),
                reverse=True,
            )
        )

    def classify(
        self,
        url: str,
        *,
        preferred_domains: tuple[str, ...],
    ) -> SourceIdentity:
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").casefold().rstrip(".")
            path = parsed.path or "/"
        except ValueError:
            host = ""
            path = "/"
        for rule in self._rules:
            if _matches(host, rule.domain) and (
                rule.path_prefix is None or path.startswith(rule.path_prefix)
            ):
                return SourceIdentity(
                    publisher=rule.publisher,
                    source_tier=rule.source_tier,
                    matched_domain=rule.domain,
                )
        for domain in preferred_domains:
            normalized = domain.casefold().rstrip(".")
            if _matches(host, normalized):
                return SourceIdentity(
                    publisher=host,
                    source_tier=SourceTier.OFFICIAL_SECONDARY,
                    matched_domain=normalized,
                )
        return SourceIdentity(
            publisher=host or "확인되지 않은 웹 출처",
            source_tier=SourceTier.UNVERIFIED_WEB,
            matched_domain=None,
        )


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


_DEFAULT_RULES = (
    SourceRule("law.go.kr", "국가법령정보센터", SourceTier.OFFICIAL_PRIMARY),
    SourceRule("moleg.go.kr", "법제처", SourceTier.OFFICIAL_PRIMARY),
    SourceRule("pps.go.kr", "조달청", SourceTier.OFFICIAL_PRIMARY),
    SourceRule("g2b.go.kr", "나라장터", SourceTier.OFFICIAL_PRIMARY),
    SourceRule("pipc.go.kr", "개인정보보호위원회", SourceTier.OFFICIAL_PRIMARY),
    SourceRule("privacy.go.kr", "개인정보 포털", SourceTier.OFFICIAL_SECONDARY),
    SourceRule("korea.kr", "대한민국 정책브리핑", SourceTier.OFFICIAL_SECONDARY),
    SourceRule("mois.go.kr", "행정안전부", SourceTier.OFFICIAL_PRIMARY),
    SourceRule("nia.or.kr", "한국지능정보사회진흥원", SourceTier.OFFICIAL_PRIMARY),
    SourceRule(
        "tsapps.nist.gov",
        "NIST",
        SourceTier.OFFICIAL_PRIMARY,
        "/publication/",
    ),
    SourceRule(
        "nist.gov",
        "NIST",
        SourceTier.OFFICIAL_PRIMARY,
        "/publications/",
    ),
    SourceRule(
        "nist.gov",
        "NIST 호스팅 자료(저자 미확인)",
        SourceTier.OFFICIAL_SECONDARY,
    ),
    SourceRule("oecd.org", "OECD", SourceTier.OFFICIAL_PRIMARY),
    SourceRule("iso.org", "ISO", SourceTier.OFFICIAL_PRIMARY),
    SourceRule("gov.uk", "UK Government", SourceTier.OFFICIAL_PRIMARY),
)
