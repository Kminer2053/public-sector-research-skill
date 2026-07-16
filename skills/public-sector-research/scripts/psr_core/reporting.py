"""Human-reviewable Markdown and JSON result rendering."""

from __future__ import annotations

from typing import Any, Dict, List

from psr_core.models import Citation, Failure, ResearchPlan


def build_result_payload(
    *,
    plan: ResearchPlan,
    status: str,
    citations: List[Citation],
    gaps: List[str],
    failures: List[Failure],
    reused_sources: int,
    collected_sources: int,
    deduplicated_count: int,
) -> Dict[str, Any]:
    official_primary = sum(
        citation.source_tier == "OFFICIAL_PRIMARY" for citation in citations
    )
    summary = (
        f"검토 가능한 원문 구간 {len(citations)}건을 확보했습니다. "
        f"공식 1차자료 인용은 {official_primary}건이며, "
        f"새로 수집한 출처 {collected_sources}건과 "
        f"재사용한 출처 {reused_sources}건을 반영했습니다. "
        "자동 결과는 법률·감사·조달의 최종 판단이 아니라 사람이 검토할 근거 패키지입니다."
    )
    return {
        "schema_version": "1.0",
        "run_id": plan.id,
        "status": status,
        "summary": summary,
        "scope": {
            "question": plan.question,
            "as_of_date": plan.as_of_date,
            "jurisdiction": plan.jurisdiction,
            "profile": plan.profile,
            "tracks": [track.id for track in plan.tracks],
            "completion_criteria": plan.completion_criteria,
            "stop_conditions": {
                "max_sources": plan.stop_conditions.max_sources,
                "max_bytes": plan.stop_conditions.max_bytes,
                "timeout_seconds": plan.stop_conditions.timeout_seconds,
                "require_official_primary": plan.stop_conditions.require_official_primary,
            },
        },
        "metrics": {
            "citation_count": len(citations),
            "official_primary_count": official_primary,
            "reused_source_count": reused_sources,
            "collected_source_count": collected_sources,
            "deduplicated_passage_count": deduplicated_count,
        },
        "citations": [citation.to_dict() for citation in citations],
        "gaps": gaps,
        "failures": [failure.to_dict() for failure in failures],
        "review": {
            "required": True,
            "facts_are_extractive": True,
            "inference_generated": False,
            "recommendation_generated": False,
            "notice": "원문의 적용범위·현행성·상충 여부를 업무담당자가 확인해야 합니다.",
        },
    }


def render_markdown(
    *,
    plan: ResearchPlan,
    payload: Dict[str, Any],
    citations: List[Citation],
    gaps: List[str],
    failures: List[Failure],
) -> str:
    track_titles = {track.id: track.title for track in plan.tracks}
    lines = [
        f"# Evidence Research Report — {plan.id}",
        "",
        f"- 상태: **{payload['status']}**",
        f"- 질문: {plan.question}",
        f"- 기준일: {plan.as_of_date}",
        f"- 관할: {plan.jurisdiction}",
        f"- 프로필: {plan.profile}",
        "",
        "## 요약",
        "",
        payload["summary"],
        "",
        "## 조사 범위",
        "",
    ]
    for track in plan.tracks:
        lines.append(
            f"- **{track.title}** (`{track.id}`): {track.research_question}"
        )
    lines.extend(["", "## 확인된 원문 근거", ""])
    if not citations:
        lines.append("인용 가능한 원문 구간을 확보하지 못했습니다.")
    for citation in citations:
        score = citation.score
        lines.extend(
            [
                f"### [{citation.id}] {track_titles.get(citation.track_id, citation.track_id)}",
                "",
                f"- 문서: {citation.publisher}, 「{citation.title}」",
                f"- 원문: {citation.source_locator}",
                f"- 구간: `{citation.locator}`",
                f"- 수집시점: {citation.retrieved_at}",
                f"- 출처등급: `{citation.source_tier}`",
                f"- 문서 SHA-256: `{citation.document_sha256}`",
                (
                    "- Evidence Score: "
                    f"**{score.overall:.2f}** "
                    f"(권위 {score.authority.value:.2f}, "
                    f"1차성 {score.primary_source.value:.2f}, "
                    f"직접성 {score.direct_relevance.value:.2f}, "
                    f"최신성 {score.freshness.value:.2f})"
                ),
                "",
                f"> {citation.excerpt}",
                "",
            ]
        )
    lines.extend(["## 확인 필요사항", ""])
    if not gaps:
        lines.append("- 자동 검사에서 추가 gap을 발견하지 못했습니다.")
    else:
        lines.extend(f"- {gap}" for gap in gaps)
    lines.extend(["", "## 부분 실패", ""])
    if not failures:
        lines.append("- 기록된 수집·파싱 실패가 없습니다.")
    else:
        for failure in failures:
            retry = "재시도 가능" if failure.retryable else "재시도 비권장"
            lines.append(
                f"- `{failure.code}` · {failure.track_id} · {failure.source_locator}: "
                f"{failure.message} ({retry})"
            )
    lines.extend(
        [
            "",
            "## 사람 검토 체크",
            "",
            "- [ ] 각 출처가 기준일 현재 공식 원문인지 확인",
            "- [ ] 인용 구간이 질문의 적용대상과 관할에 직접 적용되는지 확인",
            "- [ ] 의무·권고·사례·해석을 구분",
            "- [ ] 상충하거나 더 최신인 공식자료가 없는지 확인",
            "- [ ] 보고서 문장에 없는 추론을 추가할 경우 `INFERENCE`로 표시",
            "",
            "---",
            "",
            "이 문서는 로컬 Evidence Index에서 생성됐으며 자동 법률·감사·조달 판단이 아닙니다.",
            "",
        ]
    )
    return "\n".join(lines)
