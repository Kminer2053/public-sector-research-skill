"""Deterministic citation-constrained findings and procurement control candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from psr_mcp.evidence.models import (
    EvidenceCitation,
    EvidenceFinding,
    EvidenceRecommendationGap,
    EvidenceWriting,
)
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
        return self.analyze(citations).findings

    def analyze(
        self,
        citations: tuple[EvidenceCitation, ...],
    ) -> EvidenceWriting:
        recommendations: list[EvidenceFinding] = []
        gaps: list[EvidenceRecommendationGap] = []
        for rule in _CONTROL_RULES:
            track_citations = tuple(
                citation for citation in citations if citation.track_id == rule.track_id
            )
            recommendation, missing_anchors = self._recommendation(rule, track_citations)
            if recommendation is not None:
                recommendations.append(recommendation)
            elif track_citations:
                gaps.append(
                    EvidenceRecommendationGap(
                        track_id=rule.track_id,
                        missing_anchors=missing_anchors,
                    )
                )
        facts = tuple(self._fact(citation) for citation in citations)
        return EvidenceWriting(
            findings=(*recommendations, *facts),
            recommendation_gaps=tuple(gaps),
        )

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
    ) -> tuple[EvidenceFinding | None, tuple[str, ...]]:
        eligible = tuple(citation for citation in citations if citation.score.overall >= 0.55)
        if not eligible:
            return None, ("근거 점수 기준",)
        supporting: list[EvidenceCitation] = []
        missing_anchors: list[str] = []
        for group in rule.required_groups:
            group_matches = tuple(
                citation
                for citation in eligible
                if any(_contains(citation.excerpt, term) for term in group.terms)
            )
            if not group_matches:
                missing_anchors.append(group.label)
                continue
            for citation in group_matches:
                if citation not in supporting:
                    supporting.append(citation)
        if missing_anchors:
            return None, tuple(missing_anchors)
        selected = tuple(supporting[: self._max_supporting_citations])
        return (
            EvidenceFinding(
                claim=f"조달 원칙 검토안: {rule.claim}",
                kind="RECOMMENDATION",
                citation_ids=tuple(citation.id for citation in selected),
                confidence=_confidence(selected),
            ),
            (),
        )


@dataclass(frozen=True, slots=True)
class _AnchorGroup:
    label: str
    terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ControlRule:
    track_id: str
    required_groups: tuple[_AnchorGroup, ...]
    claim: str


def _contains(value: str, term: str) -> bool:
    normalized_value = _normalized(value)
    normalized_term = _normalized(term)
    return normalized_term in normalized_value or _compact(normalized_term) in _compact(
        normalized_value
    )


def _normalized(value: str) -> str:
    normalized = value.casefold().translate(_SEPARATOR_TRANSLATION)
    return " ".join(normalized.split())


def _compact(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


_SEPARATOR_TRANSLATION = str.maketrans(
    {
        "ㆍ": " ",
        "·": " ",
        "∙": " ",
        "・": " ",
    }
)


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
            _AnchorGroup(
                "사람의 관리·감독",
                (
                    "사람의 관리 감독",
                    "사람의 관리·감독",
                    "human oversight",
                    "human intervention",
                ),
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
            _AnchorGroup("생애주기", ("생애주기", "lifecycle")),
            _AnchorGroup(
                "안전성·위험관리",
                ("안전성", "안전조치", "risk management", "safety"),
            ),
        ),
        claim="AI 도입 전 과정에 생애주기별 법적 검토와 안전성 확인 절차를 둔다.",
    ),
    _ControlRule(
        track_id="procurement",
        required_groups=(
            _AnchorGroup(
                "데이터 소유권",
                ("data ownership", "데이터 소유권", "소유권"),
            ),
            _AnchorGroup(
                "데이터 접근권",
                ("access to data", "데이터 접근", "접근권"),
            ),
            _AnchorGroup(
                "데이터 삭제",
                ("data deletion", "deletion", "데이터 삭제", "삭제"),
            ),
        ),
        claim=(
            "계약서에 입력·산출 데이터의 소유권, 기관의 접근권과 계약 종료 시 "
            "삭제 의무를 구분해 명시한다."
        ),
    ),
    _ControlRule(
        track_id="privacy",
        required_groups=(
            _AnchorGroup(
                "보유기간",
                ("보유기간", "retention period", "retention"),
            ),
            _AnchorGroup(
                "파기·삭제",
                ("파기", "data deletion", "deletion"),
            ),
        ),
        claim="개인정보의 보유기간, 파기 시점과 검증 가능한 삭제 절차를 계약조건으로 둔다.",
    ),
    _ControlRule(
        track_id="international-standards",
        required_groups=(
            _AnchorGroup("운영 모니터링", ("monitoring", "모니터링")),
            _AnchorGroup(
                "사람의 개입·중단",
                ("human intervention", "human oversight", "shutdown", "중단"),
            ),
        ),
        claim="운영 중 모니터링과 사람의 개입·중단 기준을 위험관리 절차에 포함한다.",
    ),
    _ControlRule(
        track_id="vendor-lock-in",
        required_groups=(
            _AnchorGroup("상호운용성", ("interoperability", "상호운용성")),
            _AnchorGroup(
                "개방형 표준·라이선스·업체 종속",
                ("vendor lock-in", "open licensing", "open standards", "업체 종속"),
            ),
        ),
        claim=(
            "상호운용성, 개방형 표준 또는 라이선스 조건과 계약 종료 시 전환지원을 "
            "업체 종속 방지 조항으로 둔다."
        ),
    ),
    _ControlRule(
        track_id="data-rights",
        required_groups=(
            _AnchorGroup(
                "학습 재사용 선택권",
                ("학습 재사용", "training reuse", "opt-out", "옵트아웃"),
            ),
            _AnchorGroup(
                "보유기간·파기",
                ("보유기간", "retention", "파기", "deletion"),
            ),
        ),
        claim=(
            "개인정보 또는 이용자 입력데이터를 모델 학습에 이용하는지, 정보주체의 선택권과 "
            "보유기간·파기 조건을 계약 전에 확인·명시한다."
        ),
    ),
)
