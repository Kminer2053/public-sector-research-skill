from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from psr_core.models import SourceInput
from psr_core.planner import build_plan
from psr_core.profiles import load_profile
from psr_core.storage import ProjectStore
from psr_core.workflow import execute_run, rebuild_report


def _plan(store: ProjectStore):
    return build_plan(
        question="공공기관 인공지능 정책 종합 검토를 위한 공식자료 기준을 조사한다",
        as_of_date=date(2026, 7, 17),
        jurisdiction="KR",
        profile=load_profile(store.profile_dir, "government"),
        max_sources=15,
        max_bytes=5_000_000,
        timeout_seconds=60,
    )


def _source_files(tmp_path: Path) -> list[SourceInput]:
    contents = {
        "law-regulation": "현행 법령은 적용대상과 시행일, 의무 및 사람의 관리 감독을 정한다.",
        "government-policy": "공공기관 정부 가이드는 책임성, 거버넌스, 위험관리를 요구한다.",
        "procurement": "공공조달 계약조건에 데이터 소유권, 데이터 접근, 데이터 삭제를 명시한다.",
        "privacy": "개인정보 처리위탁은 보유기간, 파기, 학습 재사용을 검토한다.",
        "international-standards": (
            "NIST risk management guidance requires trustworthy systems and human intervention."
        ),
    }
    sources = []
    for track_id, text in contents.items():
        path = tmp_path / f"{track_id}.html"
        path.write_text(
            f"<html><title>{track_id}</title><h1>{track_id}</h1><p>{text}</p></html>",
            encoding="utf-8",
        )
        sources.append(
            SourceInput(
                track_id=track_id,
                path=str(path),
                title=f"{track_id} 공식자료",
                publisher="테스트 공공기관",
                source_tier="OFFICIAL_PRIMARY",
                published_at="2026-01-01",
            )
        )
    return sources


def test_end_to_end_run_stores_evidence_and_reuses_snapshots(tmp_path: Path) -> None:
    project = tmp_path / "project"
    store = ProjectStore.initialize(project, name="e2e")
    plan = _plan(store)
    store.save_plan(plan)
    sources = _source_files(tmp_path)

    first = execute_run(
        store=store,
        plan=plan,
        sources=sources,
        refresh=False,
        reuse_max_age_days=7,
    )

    assert first.status == "SUCCEEDED"
    assert first.collected_sources == 5
    assert first.reused_sources == 0
    assert len(first.citations) >= 5
    assert all(len(citation.document_sha256) == 64 for citation in first.citations)
    assert Path(first.report_path).exists()
    assert Path(first.result_path).exists()
    assert Path(first.html_report_path).exists()
    assert Path(first.brief_path).exists()
    assert (store.root / "reports" / f"{plan.id}.md").exists()
    assert (store.root / "reports" / f"{plan.id}.html").exists()
    report = Path(first.report_path).read_text(encoding="utf-8")
    assert "담당자 검토 체크" in report
    assert "근거 점수" in report
    html = Path(first.html_report_path).read_text(encoding="utf-8")
    assert '<section id="overview">' in html
    assert f'id="evidence-{first.citations[0].id}"' in html
    assert '<script src=' not in html
    assert '<link rel="stylesheet"' not in html
    assert "../../sources/" in html
    stable_html = (store.root / "reports" / f"{plan.id}.html").read_text(
        encoding="utf-8"
    )
    assert "../sources/" in stable_html
    for citation in first.citations:
        assert citation.local_snapshot_path
        assert (store.root / citation.local_snapshot_path).exists()
    assert "한눈에 보기" in html
    assert "citation-chip" in html
    assert "https://cdn" not in html

    second = execute_run(
        store=store,
        plan=plan,
        sources=sources,
        refresh=False,
        reuse_max_age_days=7,
    )

    assert second.status == "SUCCEEDED"
    assert second.reused_sources == 5
    assert second.collected_sources == 0
    assert store.search_memory("보유기간", limit=10)
    assert len(store.list_citations(run_id=plan.id)) == len(second.citations)
    rebuilt = rebuild_report(store, plan.id)
    assert Path(rebuilt["report_path"]).exists()
    assert Path(rebuilt["report_html_path"]).exists()


def test_report_rebuild_uses_validated_brief_and_selected_format(tmp_path: Path) -> None:
    project = tmp_path / "project"
    store = ProjectStore.initialize(project, name="curated-report")
    plan = _plan(store)
    store.save_plan(plan)
    result = execute_run(
        store=store,
        plan=plan,
        sources=_source_files(tmp_path),
        refresh=False,
        reuse_max_age_days=7,
    )
    citation_id = result.citations[0].id
    original_markdown = Path(result.report_path).read_text(encoding="utf-8")
    curated = {
        "schema_version": "1.0",
        "title": "<script>alert(1)</script> 공공복리 보고서",
        "subtitle": "담당자가 편집한 브리프",
        "executive_summary": [
            {
                "kind": "FACT",
                "text": "정책 <검토> & 확인",
                "citation_ids": [citation_id],
            }
        ],
        "key_findings": [
            {
                "id": "finding-curated",
                "title": "근거가 연결된 확인사항",
                "kind": "FACT",
                "text": "공식자료가 확인하는 범위만 기술한다.",
                "citation_ids": [citation_id],
                "track_id": result.citations[0].track_id,
            }
        ],
        "implications": [
            {
                "kind": "INFERENCE",
                "text": "담당자의 적용범위 검토가 필요하다는 해석이다.",
                "citation_ids": [citation_id],
            }
        ],
        "recommendations": [
            {
                "kind": "RECOMMENDATION",
                "text": "최신 시행일을 별도로 확인할 것을 권고한다.",
                "citation_ids": [],
            }
        ],
        "open_questions": ["기관 내부 규정과의 관계는 추가 확인이 필요하다."],
    }
    brief_file = tmp_path / "brief-curated.json"
    brief_file.write_text(
        json.dumps(curated, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    html_paths = rebuild_report(
        store,
        plan.id,
        output_format="html",
        brief_file=str(brief_file),
    )

    assert "report_path" not in html_paths
    html = Path(html_paths["report_html_path"]).read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; 공공복리 보고서" in html
    assert "정책 &lt;검토&gt; &amp; 확인" in html
    assert 'data-kind="INFERENCE"' in html
    assert 'data-kind="RECOMMENDATION"' in html
    assert Path(result.report_path).read_text(encoding="utf-8") == original_markdown

    markdown_paths = rebuild_report(store, plan.id, output_format="md")

    assert "report_html_path" not in markdown_paths
    markdown = Path(markdown_paths["report_path"]).read_text(encoding="utf-8")
    assert "공공복리 보고서" in markdown
    assert "**해석**" in markdown
    assert "**검토 권고**" in markdown
    stored_brief = json.loads(Path(markdown_paths["brief_path"]).read_text(encoding="utf-8"))
    assert stored_brief == curated


def test_partial_failure_preserves_success(tmp_path: Path) -> None:
    project = tmp_path / "project"
    store = ProjectStore.initialize(project, name="partial")
    plan = _plan(store)
    store.save_plan(plan)
    sources = _source_files(tmp_path)[:1]
    sources.append(
        SourceInput(
            track_id="privacy",
            path=str(tmp_path / "missing.pdf"),
            source_tier="OFFICIAL_PRIMARY",
        )
    )

    result = execute_run(
        store=store,
        plan=plan,
        sources=sources,
        refresh=False,
        reuse_max_age_days=7,
    )

    assert result.status == "PARTIAL"
    assert result.citations
    assert result.failures[0].code == "FILE_NOT_FOUND"
    payload = json.loads(Path(result.result_path).read_text(encoding="utf-8"))
    assert payload["status"] == "PARTIAL"
    assert payload["failures"]
    assert "결과가 완전하지 않습니다" in " ".join(payload["gaps"])


def test_same_text_is_deduplicated_within_track(tmp_path: Path) -> None:
    project = tmp_path / "project"
    store = ProjectStore.initialize(project, name="dedup")
    plan = _plan(store)
    store.save_plan(plan)
    text = "<html><p>현행 법령은 적용대상과 시행일 및 의무를 정한다.</p></html>"
    sources = []
    for index in range(2):
        path = tmp_path / f"law-{index}.html"
        path.write_text(text, encoding="utf-8")
        sources.append(
            SourceInput(
                track_id="law-regulation",
                path=str(path),
                publisher=f"기관 {index}",
                source_tier="OFFICIAL_PRIMARY",
            )
        )

    result = execute_run(
        store=store,
        plan=plan,
        sources=sources,
        refresh=False,
        reuse_max_age_days=7,
    )

    payload = json.loads(Path(result.result_path).read_text(encoding="utf-8"))
    assert payload["metrics"]["deduplicated_passage_count"] == 1


def test_snapshot_metadata_contains_provenance(tmp_path: Path) -> None:
    project = tmp_path / "project"
    store = ProjectStore.initialize(project, name="metadata")
    plan = _plan(store)
    store.save_plan(plan)

    result = execute_run(
        store=store,
        plan=plan,
        sources=_source_files(tmp_path)[:1],
        refresh=False,
        reuse_max_age_days=7,
    )

    metadata_files = list((store.root / "sources").glob("**/metadata.json"))
    assert result.citations
    assert len(metadata_files) == 1
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert len(metadata["sha256"]) == 64
    assert metadata["source"]["track_id"] == "law-regulation"
