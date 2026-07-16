"""Local-only structural metrics and human review packet for public research output."""

from __future__ import annotations

import html
from dataclasses import dataclass

from psr_mcp.public.schemas import Finding, QuickResearchOutput
from psr_mcp.search.models import SourceTier


@dataclass(frozen=True, slots=True)
class StructuralReview:
    fact_citation_coverage: float
    recommendation_citation_coverage: float
    locator_completeness: float
    official_primary_document_ratio: float
    required_track_recall: float
    fact_count: int
    recommendation_count: int
    citation_count: int
    unique_document_count: int
    gap_count: int
    conflict_count: int
    failure_count: int
    issues: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


def evaluate_structural_review(output: QuickResearchOutput) -> StructuralReview:
    citation_ids = {citation.id for citation in output.citations}
    facts = [finding for finding in output.findings if finding.kind == "FACT"]
    recommendations = [finding for finding in output.findings if finding.kind == "RECOMMENDATION"]
    fact_coverage = _finding_citation_coverage(facts, citation_ids)
    recommendation_coverage = _finding_citation_coverage(recommendations, citation_ids)
    locator_completeness = _ratio(
        sum(bool(citation.locator.strip()) for citation in output.citations),
        len(output.citations),
    )
    documents: dict[str, set[str]] = {}
    for citation in output.citations:
        documents.setdefault(citation.document_sha256, set()).add(citation.source_tier)
    official_primary_ratio = _ratio(
        sum(
            SourceTier.OFFICIAL_PRIMARY.value in source_tiers for source_tiers in documents.values()
        ),
        len(documents),
    )
    required_tracks = set(output.scope.source_tracks)
    cited_tracks = {citation.track_id for citation in output.citations}
    track_recall = _ratio(len(required_tracks & cited_tracks), len(required_tracks))

    issues: list[str] = []
    if fact_coverage < 1.0:
        issues.append("FACT citation coverage is below 100%")
    if recommendation_coverage < 1.0:
        issues.append("RECOMMENDATION citation coverage is below 100%")
    if locator_completeness < 0.95:
        issues.append("citation locator completeness is below 95%")
    if official_primary_ratio < 0.70:
        issues.append("official primary document ratio is below 70%")
    if track_recall < 1.0:
        issues.append("required source track recall is below 100%")

    return StructuralReview(
        fact_citation_coverage=fact_coverage,
        recommendation_citation_coverage=recommendation_coverage,
        locator_completeness=locator_completeness,
        official_primary_document_ratio=official_primary_ratio,
        required_track_recall=track_recall,
        fact_count=len(facts),
        recommendation_count=len(recommendations),
        citation_count=len(output.citations),
        unique_document_count=len(documents),
        gap_count=len(output.gaps),
        conflict_count=len(output.conflicts),
        failure_count=len(output.failures),
        issues=tuple(issues),
    )


def render_human_review_packet(
    *,
    question: str,
    output: QuickResearchOutput,
) -> str:
    review = evaluate_structural_review(output)
    escaped_question = "\n".join(
        f"> {html.escape(line, quote=False)}" for line in question.splitlines() or [question]
    )
    issue_lines = (
        "\n".join(f"- {issue}" for issue in review.issues)
        if review.issues
        else "- 자동 구조 검사는 모두 기준을 충족함"
    )
    return "\n".join(
        [
            "# Public Research Human Review Packet",
            "",
            "> 이 문서는 로컬 QA용이며 질문과 조사 결과를 포함합니다. "
            "Public MCP 서버는 이 문서를 저장하지 않습니다.",
            "",
            "## 조사 질문",
            "",
            escaped_question,
            "",
            "## 자동 구조 검사",
            "",
            "| 항목 | 관찰값 | 기준 | 판정 |",
            "|---|---:|---:|---|",
            _metric_row(
                "FACT citation coverage",
                review.fact_citation_coverage,
                1.0,
                review.fact_citation_coverage >= 1.0,
            ),
            _metric_row(
                "RECOMMENDATION citation coverage",
                review.recommendation_citation_coverage,
                1.0,
                review.recommendation_citation_coverage >= 1.0,
            ),
            _metric_row(
                "Citation locator completeness",
                review.locator_completeness,
                0.95,
                review.locator_completeness >= 0.95,
            ),
            _metric_row(
                "Official primary document ratio",
                review.official_primary_document_ratio,
                0.70,
                review.official_primary_document_ratio >= 0.70,
            ),
            _metric_row(
                "Required track recall",
                review.required_track_recall,
                1.0,
                review.required_track_recall >= 1.0,
            ),
            "",
            f"- 구조 검사 종합: **{'PASS' if review.passed else 'REVIEW_REQUIRED'}**",
            f"- Findings: FACT {review.fact_count}, RECOMMENDATION {review.recommendation_count}",
            f"- Citations: {review.citation_count}, "
            f"unique documents {review.unique_document_count}",
            f"- Gaps {review.gap_count}, conflicts {review.conflict_count}, "
            f"failures {review.failure_count}",
            f"- Retention: `{output.retention.purge_state}`, "
            f"`server_saved={str(output.retention.server_saved).lower()}`",
            "",
            "### 자동 검사 이슈",
            "",
            issue_lines,
            "",
            "## 조사 결과",
            "",
            output.markdown,
            "",
            "## 사람 검토표",
            "",
            "자동 구조 검사가 PASS여도 아래 항목은 사람이 직접 확인해야 합니다.",
            "",
            "| 검토 항목 | 1~5점 | 확인 기준 |",
            "|---|---:|---|",
            "| 업무 적합성 |  | 실제 업무 질문과 의사결정에 직접 도움이 되는가 |",
            "| 근거 직접성 |  | 인용 구간이 각 주장과 권고를 실제로 지지하는가 |",
            "| 공식성·현행성 |  | 원문 기관, 기준일, 시행일과 적용대상이 적절한가 |",
            "| 누락 통제 |  | 중요한 누락이 gap으로 드러나며 숨겨진 공백이 없는가 |",
            "| 과잉해석 통제 |  | 법적 의무·권고·사례를 혼동하거나 원문보다 넓게 말하지 않는가 |",
            "| 상충정보 처리 |  | 상충하는 근거가 누락되거나 임의로 단정되지 않았는가 |",
            "| 한국어 품질 |  | 원문의 의미를 훼손하지 않고 담당자가 바로 이해할 수 있는가 |",
            "| 실행 가능성 |  | 초안·체크리스트·후속 조사로 전환하기 쉬운가 |",
            "",
            "### 최종 판정",
            "",
            "- [ ] 그대로 참고 가능",
            "- [ ] 보완 후 참고 가능",
            "- [ ] 업무 사용 부적합",
            "",
            "### 필수 확인",
            "",
            "- [ ] unsupported legal conclusion 0건",
            "- [ ] critical factual contradiction 0건",
            "- [ ] 인용 원문 표본을 직접 열어 locator와 문맥 확인",
            "- [ ] 확인하지 못한 요구사항이 gap에 명시됨",
            "- [ ] 결과가 법률자문이나 기관의 최종 판단으로 오인되지 않음",
            "",
            "### Public Preview 피드백 매핑",
            "",
            "- `helpful=true`: 그대로 또는 보완 후 실제 업무에 참고할 가치가 있음",
            "- `save_feature_interest=true`: 이 조사와 근거를 저장·재사용하고 싶음",
            "",
        ]
    )


def _finding_citation_coverage(findings: list[Finding], citation_ids: set[str]) -> float:
    if not findings:
        return 1.0
    supported = 0
    for finding in findings:
        ids = finding.citation_ids
        if ids and set(ids).issubset(citation_ids):
            supported += 1
    return _ratio(supported, len(findings))


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _metric_row(label: str, value: float, target: float, passed: bool) -> str:
    return f"| {label} | {value:.1%} | ≥ {target:.0%} | {'PASS' if passed else 'REVIEW'} |"
