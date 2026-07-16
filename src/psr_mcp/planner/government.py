"""Rule-based Government/Public Sector planner baseline."""

from __future__ import annotations

from datetime import date

from psr_mcp.planner.models import ResearchPlan, ResearchTrack, StopConditions


class GovernmentPlanner:
    profile = "government-v0"

    def plan(
        self,
        *,
        question: str,
        as_of_date: date,
        jurisdiction: str,
        max_sources: int,
        max_bytes: int,
        timeout_seconds: float,
    ) -> ResearchPlan:
        normalized = " ".join(question.split())
        if len(normalized) < 10 or len(normalized) > 4_000:
            raise ValueError("question must contain 10..4000 characters")
        if jurisdiction != "KR":
            raise ValueError("government-v0 currently supports jurisdiction KR only")

        tracks = list(_BASE_TRACKS)
        lowered = normalized.casefold()
        if any(keyword in lowered for keyword in _LOCK_IN_KEYWORDS):
            tracks.append(_VENDOR_LOCK_IN_TRACK)
        if any(keyword in lowered for keyword in _DATA_RIGHTS_KEYWORDS):
            tracks.append(_DATA_RIGHTS_TRACK)
        return ResearchPlan(
            question=normalized,
            as_of_date=as_of_date,
            jurisdiction=jurisdiction,
            profile=self.profile,
            tracks=tuple(_deduplicate(tracks)),
            completion_criteria=(
                "주요 사실에 공식 1차자료 citation을 연결한다.",
                "시행일·관할·적용대상과 공식 원문 미확보를 표시한다.",
                "상충 정보·부분실패·추론을 사실과 구분한다.",
            ),
            stop_conditions=StopConditions(
                max_sources=max_sources,
                max_bytes=max_bytes,
                timeout_seconds=timeout_seconds,
                require_official_primary=True,
            ),
        )


_BASE_TRACKS = (
    ResearchTrack(
        id="law-regulation",
        title="법령·규정",
        research_question="현행 법령과 하위 규정의 의무·권고·적용대상은 무엇인가?",
        evidence_types=("법령", "시행령", "고시"),
        source_tiers=("OFFICIAL_PRIMARY",),
        selection_terms=(
            "인공지능기본법",
            "의무",
            "적용대상",
            "시행일",
            "고영향 인공지능",
            "투명성",
            "사람의 관리 감독",
            "obligation",
            "high-impact AI",
            "transparency",
            "human oversight",
        ),
    ),
    ResearchTrack(
        id="government-policy",
        title="정부 정책·가이드",
        research_question="정부와 공공기관의 공식 정책·가이드는 어떤 원칙을 제시하는가?",
        evidence_types=("정부 가이드", "공공기관 지침"),
        source_tiers=("OFFICIAL_PRIMARY", "OFFICIAL_SECONDARY"),
        selection_terms=(
            "공공기관",
            "정부 가이드",
            "책임성",
            "거버넌스",
            "위험관리",
            "public sector",
            "government guidance",
            "accountability",
            "governance",
            "risk management",
        ),
    ),
    ResearchTrack(
        id="procurement",
        title="조달·계약",
        research_question="공공조달과 계약 요구사항에 반영할 통제는 무엇인가?",
        evidence_types=("조달 지침", "계약 기준", "감사 기준"),
        source_tiers=("OFFICIAL_PRIMARY",),
        selection_terms=(
            "조달",
            "계약",
            "발주",
            "평가기준",
            "계약조건",
            "데이터 소유권",
            "데이터 접근",
            "데이터 삭제",
            "procurement",
            "contract",
            "data ownership",
            "access to data",
            "data deletion",
        ),
    ),
    ResearchTrack(
        id="privacy",
        title="개인정보·데이터 보호",
        research_question="개인정보와 공공데이터 처리의 권리·책임·보호조치는 무엇인가?",
        evidence_types=("개인정보 법령", "개인정보 가이드"),
        source_tiers=("OFFICIAL_PRIMARY",),
        selection_terms=(
            "개인정보",
            "처리위탁",
            "보유기간",
            "파기",
            "학습 재사용",
            "옵트아웃",
            "privacy",
            "retention",
            "deletion",
            "training reuse",
            "opt-out",
        ),
    ),
    ResearchTrack(
        id="international-standards",
        title="국제기구·표준",
        research_question="비교 가능한 국제기구·표준기관의 공식 기준은 무엇인가?",
        evidence_types=("국제표준", "국제기구 가이드"),
        source_tiers=("OFFICIAL_PRIMARY",),
        selection_terms=(
            "위험관리",
            "신뢰성",
            "설명가능성",
            "사람의 개입",
            "제3자 데이터",
            "risk management",
            "trustworthy",
            "explainability",
            "human intervention",
            "third-party data",
        ),
    ),
)

_VENDOR_LOCK_IN_TRACK = ResearchTrack(
    id="vendor-lock-in",
    title="업체 종속·이전성",
    research_question="계약 종료 시 데이터·기록 반환, 이전지원과 상호운용 조건은 무엇인가?",
    evidence_types=("계약 기준", "데이터 이전 지침"),
    source_tiers=("OFFICIAL_PRIMARY", "OFFICIAL_SECONDARY"),
    selection_terms=(
        "업체 종속",
        "데이터 반환",
        "이전지원",
        "상호운용성",
        "개방형 표준",
        "vendor lock-in",
        "data return",
        "transition assistance",
        "interoperability",
        "open standards",
        "portability",
    ),
)

_DATA_RIGHTS_TRACK = ResearchTrack(
    id="data-rights",
    title="데이터 권리·학습 재사용",
    research_question="입력·산출물의 권리, 학습 재사용, 보존·삭제 조건은 무엇인가?",
    evidence_types=("개인정보 가이드", "AI 조달 가이드", "계약 기준"),
    source_tiers=("OFFICIAL_PRIMARY",),
    selection_terms=(
        "데이터 권리",
        "산출물 권리",
        "학습 재사용",
        "보유기간",
        "파기",
        "옵트아웃",
        "data ownership",
        "data access",
        "data deletion",
        "training reuse",
        "retention",
        "opt-out",
    ),
)

_LOCK_IN_KEYWORDS = (
    "업체 종속",
    "vendor lock",
    "lock-in",
    "이전성",
    "데이터 반환",
)
_DATA_RIGHTS_KEYWORDS = (
    "데이터 권리",
    "학습 재사용",
    "데이터 재사용",
    "산출물 권리",
    "구매",
    "조달",
)


def _deduplicate(tracks: list[ResearchTrack]) -> list[ResearchTrack]:
    seen: set[str] = set()
    result: list[ResearchTrack] = []
    for track in tracks:
        if track.id in seen:
            continue
        seen.add(track.id)
        result.append(track)
    return result
