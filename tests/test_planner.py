from __future__ import annotations

from datetime import date

import pytest
from psr_core.planner import build_plan
from psr_core.profiles import GOVERNMENT_PROFILE, list_profiles, load_profile
from psr_core.storage import ProjectStore


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


def test_unknown_profile_is_rejected(tmp_path) -> None:
    store = ProjectStore.initialize(tmp_path, name="profile-test")

    with pytest.raises(ValueError, match="unknown research profile"):
        load_profile(store.profile_dir, "missing")
