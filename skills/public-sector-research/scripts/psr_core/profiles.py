"""Built-in profile and project-local profile loading."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

GOVERNMENT_PROFILE: Dict[str, Any] = {
    "schema_version": "1.0",
    "id": "government",
    "title": "Government and Public Sector",
    "jurisdictions": ["KR"],
    "source_tier_order": [
        "OFFICIAL_PRIMARY",
        "OFFICIAL_SECONDARY",
        "ACADEMIC_PRIMARY",
        "COMPANY_OFFICIAL",
        "REPUTABLE_MEDIA",
        "COMMUNITY",
        "UNVERIFIED_WEB",
    ],
    "completion_criteria": [
        "주요 사실에 공식 1차자료의 원문 구간을 연결한다.",
        "기준일·관할·적용대상과 공식 원문 미확보를 표시한다.",
        "상충 정보·부분실패·추론을 사실과 구분한다.",
        "각 핵심 조사 track에 최소 하나의 검토 가능한 근거 또는 명시적 gap을 남긴다.",
    ],
    "tracks": [
        {
            "id": "law-regulation",
            "title": "법령·규정",
            "research_question": "현행 법령과 하위 규정의 의무·권고·적용대상은 무엇인가?",
            "evidence_types": ["법령", "시행령", "고시"],
            "source_tiers": ["OFFICIAL_PRIMARY"],
            "preferred_domains": ["law.go.kr", "moleg.go.kr"],
            "selection_terms": [
                "의무",
                "적용대상",
                "시행일",
                "투명성",
                "사람의 관리 감독",
                "human oversight",
            ],
        },
        {
            "id": "government-policy",
            "title": "정부 정책·공공 가이드",
            "research_question": "정부와 공공기관의 공식 정책·가이드는 어떤 원칙을 제시하는가?",
            "evidence_types": ["정부 가이드", "공공기관 지침"],
            "source_tiers": ["OFFICIAL_PRIMARY", "OFFICIAL_SECONDARY"],
            "preferred_domains": ["korea.kr", "go.kr", "nia.or.kr", "mois.go.kr"],
            "selection_terms": [
                "공공기관",
                "책임성",
                "거버넌스",
                "위험관리",
                "government guidance",
            ],
        },
        {
            "id": "procurement",
            "title": "조달·계약",
            "research_question": "공공조달과 계약 요구사항에 반영할 통제는 무엇인가?",
            "evidence_types": ["조달 지침", "계약 기준", "감사 기준"],
            "source_tiers": ["OFFICIAL_PRIMARY", "OFFICIAL_SECONDARY"],
            "preferred_domains": ["pps.go.kr", "g2b.go.kr"],
            "selection_terms": [
                "조달",
                "계약조건",
                "데이터 소유권",
                "데이터 접근",
                "데이터 삭제",
                "procurement",
            ],
        },
        {
            "id": "privacy",
            "title": "개인정보·데이터 보호",
            "research_question": "개인정보와 공공데이터 처리의 권리·책임·보호조치는 무엇인가?",
            "evidence_types": ["개인정보 법령", "개인정보 가이드"],
            "source_tiers": ["OFFICIAL_PRIMARY"],
            "preferred_domains": ["pipc.go.kr", "privacy.go.kr", "law.go.kr"],
            "selection_terms": [
                "개인정보",
                "처리위탁",
                "보유기간",
                "파기",
                "학습 재사용",
                "privacy",
            ],
        },
        {
            "id": "international-standards",
            "title": "국제기구·표준",
            "research_question": "비교 가능한 국제기구·표준기관의 공식 기준은 무엇인가?",
            "evidence_types": ["국제표준", "국제기구 가이드"],
            "source_tiers": ["OFFICIAL_PRIMARY", "ACADEMIC_PRIMARY"],
            "preferred_domains": ["oecd.org", "nist.gov", "iso.org"],
            "selection_terms": [
                "위험관리",
                "신뢰성",
                "설명가능성",
                "사람의 개입",
                "risk management",
            ],
        },
    ],
    "conditional_tracks": [
        {
            "keywords": ["업체 종속", "vendor lock", "lock-in", "이전성", "데이터 반환"],
            "track": {
                "id": "vendor-lock-in",
                "title": "업체 종속·이전성",
                "research_question": "계약 종료 시 데이터·기록 반환과 이전지원 조건은 무엇인가?",
                "evidence_types": ["계약 기준", "데이터 이전 지침"],
                "source_tiers": ["OFFICIAL_PRIMARY", "OFFICIAL_SECONDARY"],
                "preferred_domains": ["pps.go.kr", "g2b.go.kr", "gov.uk"],
                "selection_terms": [
                    "업체 종속",
                    "데이터 반환",
                    "이전지원",
                    "상호운용성",
                    "vendor lock-in",
                ],
            },
        },
        {
            "keywords": [
                "데이터 권리",
                "학습 재사용",
                "데이터 재사용",
                "산출물 권리",
                "구매",
                "조달",
            ],
            "track": {
                "id": "data-rights",
                "title": "데이터 권리·학습 재사용",
                "research_question": "입력·산출물의 권리, 학습 재사용, 보존·삭제 조건은 무엇인가?",
                "evidence_types": ["개인정보 가이드", "AI 조달 가이드", "계약 기준"],
                "source_tiers": ["OFFICIAL_PRIMARY"],
                "preferred_domains": ["pipc.go.kr", "pps.go.kr", "nia.or.kr"],
                "selection_terms": [
                    "데이터 권리",
                    "산출물 권리",
                    "학습 재사용",
                    "보유기간",
                    "파기",
                    "opt-out",
                ],
            },
        },
    ],
}


def built_in_profiles() -> List[Dict[str, Any]]:
    return [deepcopy(GOVERNMENT_PROFILE)]


def install_builtin_profiles(profile_dir: Path) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / "government.json"
    if not path.exists():
        path.write_text(
            json.dumps(GOVERNMENT_PROFILE, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def load_profile(profile_dir: Path, profile_id: str) -> Dict[str, Any]:
    path = profile_dir / f"{profile_id}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif profile_id == "government":
        payload = deepcopy(GOVERNMENT_PROFILE)
    else:
        raise ValueError(f"unknown research profile: {profile_id}")
    _validate_profile(payload)
    return payload


def list_profiles(profile_dir: Path) -> List[Dict[str, str]]:
    discovered: Dict[str, Dict[str, str]] = {
        "government": {"id": "government", "title": "Government and Public Sector"}
    }
    if profile_dir.exists():
        for path in sorted(profile_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                _validate_profile(payload)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            discovered[str(payload["id"])] = {
                "id": str(payload["id"]),
                "title": str(payload["title"]),
            }
    return [discovered[key] for key in sorted(discovered)]


def _validate_profile(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("profile must be a JSON object")
    for key in ("id", "title", "tracks", "completion_criteria"):
        if key not in payload:
            raise ValueError(f"profile is missing {key}")
    if not isinstance(payload["tracks"], list) or not payload["tracks"]:
        raise ValueError("profile tracks must be a non-empty list")
    track_ids = set()
    for track in payload["tracks"]:
        _validate_track(track)
        track_id = str(track["id"])
        if track_id in track_ids:
            raise ValueError(f"duplicate track id: {track_id}")
        track_ids.add(track_id)
    for conditional in payload.get("conditional_tracks", []):
        if not isinstance(conditional.get("keywords"), list) or not conditional["keywords"]:
            raise ValueError("conditional track must contain keywords")
        _validate_track(conditional.get("track"))


def _validate_track(track: Any) -> None:
    if not isinstance(track, dict):
        raise ValueError("profile track must be an object")
    required = (
        "id",
        "title",
        "research_question",
        "evidence_types",
        "source_tiers",
        "preferred_domains",
        "selection_terms",
    )
    for key in required:
        if key not in track:
            raise ValueError(f"profile track is missing {key}")
