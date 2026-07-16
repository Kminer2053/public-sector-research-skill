"""Deterministic citation-constrained findings and procurement control candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from psr_mcp.evidence.models import EvidenceCitation, EvidenceFinding
from psr_mcp.search.models import SourceTier


class CitationConstrainedWriter:
    """Create extractive facts and only pre-reviewed, anchor-backed recommendations."""

    def __init__(
        self,
        *,
        max_fact_chars: int = 220,
        max_supporting_citations: int = 3,
    ) -> None:
        if max_fact_chars < 100 or max_fact_chars > 500:
            raise ValueError("max_fact_chars must be 100..500")
        if max_supporting_citations < 1 or max_supporting_citations > 10:
            raise ValueError("max_supporting_citations must be 1..10")
        self._max_fact_chars = max_fact_chars
        self._max_supporting_citations = max_supporting_citations

    def write(
        self,
        citations: tuple[EvidenceCitation, ...],
    ) -> tuple[EvidenceFinding, ...]:
        recommendations = tuple(
            finding
            for rule in _CONTROL_RULES
            if (
                finding := self._recommendation(
                    rule,
                    tuple(citation for citation in citations if citation.track_id == rule.track_id),
                )
            )
            is not None
        )
        facts = tuple(self._fact(citation) for citation in citations)
        return (*recommendations, *facts)

    def _fact(self, citation: EvidenceCitation) -> EvidenceFinding:
        excerpt = " ".join(citation.excerpt.split())
        if len(excerpt) > self._max_fact_chars:
            excerpt = f"{excerpt[: self._max_fact_chars - 1]}…"
        return EvidenceFinding(
            claim=(
                f"{citation.publisher}의 「{citation.title}」 "
                f"{citation.locator} 관련 원문: {excerpt}"
            ),
            kind="FACT",
            citation_ids=(citation.id,),
            confidence=_confidence((citation,)),
        )

    def _recommendation(
        self,
        rule: _ControlRule,
        citations: tuple[EvidenceCitation, ...],
    ) -> EvidenceFinding | None:
        eligible = tuple(citation for citation in citations if citation.score.overall >= 0.55)
        if not eligible:
            return None
        supporting: list[EvidenceCitation] = []
        for group in rule.required_groups:
            group_matches = tuple(
                citation
                for citation in eligible
                if any(_contains(citation.excerpt, term) for term in group)
            )
            if not group_matches:
                return None
            for citation in group_matches:
                if citation not in supporting:
                    supporting.append(citation)
        selected = tuple(supporting[: self._max_supporting_citations])
        return EvidenceFinding(
            claim=f"조달 원칙 검토안: {rule.claim}",
            kind="RECOMMENDATION",
            citation_ids=tuple(citation.id for citation in selected),
            confidence=_confidence(selected),
        )


@dataclass(frozen=True, slots=True)
class _ControlRule:
    track_id: str
    required_groups: tuple[tuple[str, ...], ...]
    claim: str


def _contains(value: str, term: str) -> bool:
    normalized_value = _normalized(value)
    normalized_term = _normalized(term)
    return normalized_term in normalized_value or _compact(normalized_term) in _compact(
        normalized_value
    )


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _compact(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def _confidence(
    citations: tuple[EvidenceCitation, ...],
) -> Literal["HIGH", "MEDIUM", "LOW"]:
    if not citations:
        return "LOW"
    average = sum(citation.score.overall for citation in citations) / len(citations)
    all_primary = all(citation.source_tier is SourceTier.OFFICIAL_PRIMARY for citation in citations)
    if average >= 0.8 and all_primary:
        return "HIGH"
    if average >= 0.6:
        return "MEDIUM"
    return "LOW"


_CONTROL_RULES = (
    _ControlRule(
        track_id="law-regulation",
        required_groups=(
            (
                "사람의 관리 감독",
                "사람의 관리·감독",
                "human oversight",
                "human intervention",
            ),
        ),
        claim=(
            "고영향 AI 또는 관련 제품·서비스에는 사람의 관리·감독 책임과 "
            "필요 시 개입 절차를 명시한다."
        ),
    ),
    _ControlRule(
        track_id="government-policy",
        required_groups=(
            ("생애주기", "lifecycle"),
            ("안전성", "안전조치", "risk management", "safety"),
        ),
        claim="AI 도입 전 과정에 생애주기별 법적 검토와 안전성 확인 절차를 둔다.",
    ),
    _ControlRule(
        track_id="procurement",
        required_groups=(
            ("data ownership", "데이터 소유권", "소유권"),
            ("access to data", "데이터 접근", "접근권"),
            ("data deletion", "데이터 삭제", "삭제"),
        ),
        claim=(
            "계약서에 입력·산출 데이터의 소유권, 기관의 접근권과 계약 종료 시 "
            "삭제 의무를 구분해 명시한다."
        ),
    ),
    _ControlRule(
        track_id="privacy",
        required_groups=(
            ("보유기간", "retention period", "retention"),
            ("파기", "data deletion", "deletion"),
        ),
        claim="개인정보의 보유기간, 파기 시점과 검증 가능한 삭제 절차를 계약조건으로 둔다.",
    ),
    _ControlRule(
        track_id="international-standards",
        required_groups=(
            ("monitoring", "모니터링"),
            ("human intervention", "human oversight", "shutdown", "중단"),
        ),
        claim="운영 중 모니터링과 사람의 개입·중단 기준을 위험관리 절차에 포함한다.",
    ),
    _ControlRule(
        track_id="vendor-lock-in",
        required_groups=(
            ("interoperability", "상호운용성"),
            ("vendor lock-in", "open licensing", "open standards", "업체 종속"),
        ),
        claim=(
            "상호운용성, 개방형 표준 또는 라이선스 조건과 계약 종료 시 전환지원을 "
            "업체 종속 방지 조항으로 둔다."
        ),
    ),
    _ControlRule(
        track_id="data-rights",
        required_groups=(
            ("학습 재사용", "training reuse", "opt-out", "옵트아웃"),
            ("보유기간", "retention", "파기", "deletion"),
        ),
        claim=(
            "기관 데이터의 모델 학습 재사용 여부와 선택권, 보유기간·파기 조건을 계약 전에 확정한다."
        ),
    ),
)
