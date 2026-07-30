from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from psr_core.briefing import (
    BriefValidationError,
    build_default_brief,
    validate_brief,
)
from psr_core.models import SourceInput
from psr_core.planner import build_plan
from psr_core.profiles import load_profile
from psr_core.storage import ProjectStore
from psr_core.workflow import execute_run, rebuild_report


def _completed_run(tmp_path: Path):
    store = ProjectStore.initialize(tmp_path / "project", name="report")
    plan = build_plan(
        question="공공서비스 민원 대기시간 개선 근거를 조사한다",
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=load_profile(store.profile_dir, "government"),
        max_sources=10,
        max_bytes=1_000_000,
        timeout_seconds=30,
    )
    store.save_plan(plan)
    source = tmp_path / "policy.html"
    source.write_text(
        "<html><main><p>공공기관 정책은 민원 서비스의 대기시간과 처리 결과를 "
        "측정하고 개선계획을 기록하도록 권고한다.</p></main></html>",
        encoding="utf-8",
    )
    result = execute_run(
        store=store,
        plan=plan,
        sources=[
            SourceInput(
                track_id="government-policy",
                path=str(source),
                title="민원 서비스 개선 지침",
                publisher="테스트 공공기관",
                source_tier="OFFICIAL_PRIMARY",
                published_at="2026-01-01",
            )
        ],
        refresh=False,
        reuse_max_age_days=7,
    )
    return store, plan, result


def test_brief_requires_citations_for_fact_and_inference(tmp_path: Path) -> None:
    store, plan, result = _completed_run(tmp_path)
    default = build_default_brief(
        plan=plan,
        citations=result.citations,
        gaps=result.gaps,
    )
    default["executive_summary"][0]["citation_ids"] = []

    with pytest.raises(BriefValidationError, match="requires citation_ids"):
        validate_brief(default, citation_ids=[item.id for item in result.citations])

    assert store.db_path.exists()


def test_brief_rejects_unknown_citation_id(tmp_path: Path) -> None:
    _, plan, result = _completed_run(tmp_path)
    default = build_default_brief(
        plan=plan,
        citations=result.citations,
        gaps=result.gaps,
    )
    default["executive_summary"][0]["citation_ids"] = ["cit-does-not-exist"]

    with pytest.raises(BriefValidationError, match="unknown citation IDs"):
        validate_brief(default, citation_ids=[item.id for item in result.citations])


def test_curated_brief_renders_both_formats_and_escapes_html(tmp_path: Path) -> None:
    store, plan, result = _completed_run(tmp_path)
    citation_id = result.citations[0].id
    brief_file = tmp_path / "brief.json"
    brief_file.write_text(
        """{
          "schema_version": "1.0",
          "title": "민원 대기시간 개선 <script>alert(1)</script>",
          "subtitle": "공식자료 검토 결과",
          "executive_summary": [
            {"kind":"FACT","text":"대기시간을 측정해야 한다.","citation_ids":["%s"]}
          ],
          "key_findings": [
            {"id":"wait-time","title":"측정 기준","kind":"FACT",
             "text":"처리 결과와 개선계획도 함께 기록한다.",
             "citation_ids":["%s"],"track_id":"government-policy"}
          ],
          "implications": [
            {"kind":"INFERENCE","text":"현황 측정 없이 개선 우선순위를 정하기 어렵다.",
             "citation_ids":["%s"]}
          ],
          "recommendations": [
            {"kind":"RECOMMENDATION","text":"기관 여건에 맞는 지표를 승인한다.",
             "citation_ids":[]}
          ],
          "open_questions": []
        }"""
        % (citation_id, citation_id, citation_id),
        encoding="utf-8",
    )

    paths = rebuild_report(
        store,
        plan.id,
        output_format="all",
        brief_file=str(brief_file),
    )
    html = Path(paths["report_html_path"]).read_text(encoding="utf-8")
    markdown = Path(paths["report_markdown_path"]).read_text(encoding="utf-8")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "민원 대기시간 개선 &lt;script&gt;alert(1)&lt;/script&gt;" in markdown
    assert "<script>alert(1)</script>" not in markdown
    assert f'data-citation-id="{citation_id}"' in html
    assert "업무 시사점" in html
    assert "검토 권고" in html
    assert "수집 당시 원문 보기" in html
    assert "https://cdn" not in html
    assert "--content-max:1600px" in html
    assert "grid-template-columns:180px minmax(0,1fr)" in html
    assert "@media(max-width:1040px)" in html
    assert "body{margin:0;font-size:17px;font-weight:500" in html
    assert ".hero h1{white-space:nowrap}" in html
    assert 'font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo"' in html
    assert "font-synthesis:none" not in html


def test_html_only_rebuild_returns_only_html_report_path(tmp_path: Path) -> None:
    store, plan, _ = _completed_run(tmp_path)

    paths = rebuild_report(store, plan.id, output_format="html")

    assert "report_html_path" in paths
    assert "report_markdown_path" not in paths
