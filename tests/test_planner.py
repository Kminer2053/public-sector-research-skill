from __future__ import annotations

import json
from copy import deepcopy
from datetime import date

import pytest
from psr_core.planner import build_plan
from psr_core.profiles import (
    GOVERNMENT_PROFILE,
    _validate_profile,
    list_profiles,
    load_profile,
)
from psr_core.storage import ProjectStore


def _legacy_government_profile() -> dict:
    return {
        key: value
        for key, value in GOVERNMENT_PROFILE.items()
        if key
        not in {
            "required_track_ids",
            "optional_track_rules",
            "broad_scope_keywords",
            "excluded_track_ids",
        }
    }


def test_government_plan_contains_base_tracks() -> None:
    plan = build_plan(
        question="공공기관 인공지능 정책 수립을 위한 공식자료 기준을 조사한다",
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=GOVERNMENT_PROFILE,
        max_sources=15,
        max_bytes=10_000_000,
        timeout_seconds=120,
    )

    assert plan.id.startswith("run-20260717-")
    assert [track.id for track in plan.tracks] == [
        "law-regulation",
        "government-policy",
        "procurement",
        "privacy",
        "international-standards",
    ]
    assert len(plan.search_queries) == 5
    assert "site:law.go.kr" in plan.search_queries[0]["query"]
    assert plan.stop_conditions.require_official_primary is True


def test_plan_adds_conditional_tracks() -> None:
    plan = build_plan(
        question="공공기관 AI 구매에서 데이터 권리와 업체 종속 방지 원칙을 조사한다",
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=GOVERNMENT_PROFILE,
        max_sources=20,
        max_bytes=10_000_000,
        timeout_seconds=120,
    )

    track_ids = {track.id for track in plan.tracks}
    assert "data-rights" in track_ids
    assert "vendor-lock-in" in track_ids


def test_narrow_question_uses_only_required_tracks() -> None:
    plan = build_plan(
        question="공공 디지털서비스 접근성 의무와 실무 점검사항을 조사한다",
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=GOVERNMENT_PROFILE,
        max_sources=15,
        max_bytes=10_000_000,
        timeout_seconds=120,
    )

    assert [track.id for track in plan.tracks] == [
        "law-regulation",
        "government-policy",
    ]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("공공기관 개인정보 처리위탁과 보유기간 기준을 조사한다", "privacy"),
        ("공공기관 서비스 구매 계약과 입찰 기준을 조사한다", "procurement"),
        ("국제표준과 해외 공공기관 기준을 비교 조사한다", "international-standards"),
    ],
)
def test_question_keywords_activate_optional_tracks(question: str, expected: str) -> None:
    plan = build_plan(
        question=question,
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=GOVERNMENT_PROFILE,
        max_sources=15,
        max_bytes=10_000_000,
        timeout_seconds=120,
    )

    assert expected in {track.id for track in plan.tracks}


def test_explicit_track_inclusion_and_exclusion_override_keyword_selection() -> None:
    base = build_plan(
        question="공공 디지털서비스 접근성 의무와 실무 점검사항을 조사한다",
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=GOVERNMENT_PROFILE,
        max_sources=15,
        max_bytes=10_000_000,
        timeout_seconds=120,
    )
    selected = build_plan(
        question="공공 디지털서비스 접근성 의무와 실무 점검사항을 조사한다",
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=GOVERNMENT_PROFILE,
        max_sources=15,
        max_bytes=10_000_000,
        timeout_seconds=120,
        include_tracks=["privacy"],
        exclude_tracks=["government-policy"],
    )

    assert [track.id for track in selected.tracks] == ["law-regulation", "privacy"]
    assert selected.id != base.id


def test_legacy_profile_keeps_every_base_track_required() -> None:
    legacy = _legacy_government_profile()

    plan = build_plan(
        question="공공 디지털서비스 접근성 의무와 실무 점검사항을 조사한다",
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=legacy,
        max_sources=15,
        max_bytes=10_000_000,
        timeout_seconds=120,
    )

    assert [track.id for track in plan.tracks[:5]] == [
        "law-regulation",
        "government-policy",
        "procurement",
        "privacy",
        "international-standards",
    ]


@pytest.mark.parametrize(
    ("include_tracks", "exclude_tracks", "message"),
    [
        (["missing"], [], "unknown track IDs"),
        ([" "], [], "non-empty track ID"),
        (["privacy"], ["privacy"], "both included and excluded"),
        ([], ["law-regulation", "government-policy"], "removed every research track"),
    ],
)
def test_explicit_track_selection_rejects_invalid_requests(
    include_tracks: list[str],
    exclude_tracks: list[str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_plan(
            question="공공 디지털서비스 접근성 의무와 실무 점검사항을 조사한다",
            as_of_date=date(2026, 7, 17),
            jurisdiction="KR",
            profile=GOVERNMENT_PROFILE,
            max_sources=15,
            max_bytes=10_000_000,
            timeout_seconds=120,
            include_tracks=include_tracks,
            exclude_tracks=exclude_tracks,
        )


def test_profile_exclusion_cannot_be_overridden_by_plan() -> None:
    profile = deepcopy(GOVERNMENT_PROFILE)
    profile["excluded_track_ids"] = ["privacy"]

    with pytest.raises(ValueError, match="disabled by the profile"):
        build_plan(
            question="공공기관 개인정보 처리위탁 기준을 조사한다",
            as_of_date=date(2026, 7, 17),
            jurisdiction="KR",
            profile=profile,
            max_sources=15,
            max_bytes=10_000_000,
            timeout_seconds=120,
            include_tracks=["privacy"],
        )


def test_profile_activation_schema_rejects_ambiguous_rules() -> None:
    cases = []

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload["required_track_ids"] = []
    cases.append((payload, "required_track_ids must not be empty"))

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload["required_track_ids"].append("missing")
    cases.append((payload, "unknown IDs"))

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload["required_track_ids"].append("privacy")
    cases.append((payload, "required and optional"))

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload["optional_track_rules"].append(
        deepcopy(payload["optional_track_rules"][0])
    )
    cases.append((payload, "duplicate optional track rule"))

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload["optional_track_rules"][0]["keywords"] = []
    cases.append((payload, "keywords must not be empty"))

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload["optional_track_rules"].pop()
    cases.append((payload, "classify every base track"))

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload.pop("required_track_ids")
    cases.append((payload, "optional_track_rules requires"))

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload.pop("required_track_ids")
    payload["optional_track_rules"] = []
    cases.append((payload, "broad_scope_keywords requires"))

    payload = deepcopy(GOVERNMENT_PROFILE)
    payload["conditional_tracks"][0]["track"]["id"] = "law-regulation"
    cases.append((payload, "duplicate conditional track id"))

    for payload, message in cases:
        with pytest.raises(ValueError, match=message):
            _validate_profile(payload)


@pytest.mark.parametrize(
    ("question", "jurisdiction", "max_sources"),
    [
        ("짧음", "KR", 10),
        ("공공기관 정책 관련 공식자료를 조사한다", "US", 10),
        ("공공기관 정책 관련 공식자료를 조사한다", "KR", 0),
    ],
)
def test_plan_rejects_invalid_scope(
    question: str,
    jurisdiction: str,
    max_sources: int,
) -> None:
    with pytest.raises(ValueError):
        build_plan(
            question=question,
            as_of_date=date(2026, 7, 17),
            jurisdiction=jurisdiction,
            profile=GOVERNMENT_PROFILE,
            max_sources=max_sources,
            max_bytes=10_000,
            timeout_seconds=30,
        )


def test_project_installs_extensible_profile(tmp_path) -> None:
    store = ProjectStore.initialize(tmp_path, name="profile-test")

    profile = load_profile(store.profile_dir, "government")
    profiles = list_profiles(store.profile_dir)

    assert profile["id"] == "government"
    assert profiles == [{"id": "government", "title": "Government and Public Sector"}]
    assert (store.profile_dir / "government.json").exists()


def test_loading_upgrades_only_untouched_legacy_government_profile(tmp_path) -> None:
    store = ProjectStore.initialize(tmp_path, name="profile-upgrade")
    profile_path = store.profile_dir / "government.json"
    profile_path.write_text(
        json.dumps(_legacy_government_profile(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    loaded = load_profile(store.profile_dir, "government")

    upgraded = json.loads(profile_path.read_text(encoding="utf-8"))
    assert loaded["required_track_ids"] == ["law-regulation", "government-policy"]
    assert upgraded["required_track_ids"] == ["law-regulation", "government-policy"]


def test_project_preserves_custom_legacy_government_profile(tmp_path) -> None:
    store = ProjectStore.initialize(tmp_path, name="profile-custom")
    profile_path = store.profile_dir / "government.json"
    custom = _legacy_government_profile()
    custom["title"] = "기관 맞춤 프로필"
    profile_path.write_text(
        json.dumps(custom, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ProjectStore.initialize(tmp_path, name="profile-custom")

    preserved = json.loads(profile_path.read_text(encoding="utf-8"))
    assert preserved["title"] == "기관 맞춤 프로필"
    assert "required_track_ids" not in preserved


def test_unknown_profile_is_rejected(tmp_path) -> None:
    store = ProjectStore.initialize(tmp_path, name="profile-test")

    with pytest.raises(ValueError, match="unknown research profile"):
        load_profile(store.profile_dir, "missing")
