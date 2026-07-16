from __future__ import annotations

import json
from pathlib import Path

import pytest
from psr_core.models import SourceInput
from psr_core.storage import (
    ProjectNotInitializedError,
    ProjectStore,
    RecordNotFoundError,
)
from psr_core.workflow import load_sources


def test_load_sources_combines_inline_json_and_jsonl(tmp_path: Path) -> None:
    json_path = tmp_path / "sources.json"
    json_path.write_text(
        json.dumps(
            [
                {
                    "track_id": "privacy",
                    "url": "https://example.go.kr/privacy",
                    "source_tier": "OFFICIAL_PRIMARY",
                }
            ]
        ),
        encoding="utf-8",
    )
    sources = load_sources(
        inline_sources=["law-regulation=./law.html"],
        sources_file=str(json_path),
    )
    assert len(sources) == 2
    assert sources[0].path == "./law.html"
    assert sources[1].url == "https://example.go.kr/privacy"

    jsonl_path = tmp_path / "sources.jsonl"
    jsonl_path.write_text(
        "\n"
        + json.dumps({"track_id": "procurement", "path": "./procurement.html"})
        + "\n",
        encoding="utf-8",
    )
    assert load_sources(inline_sources=[], sources_file=str(jsonl_path))[0].track_id == (
        "procurement"
    )


@pytest.mark.parametrize(
    "inline",
    [
        ["missing-separator"],
        ["=https://example.com"],
        ["privacy="],
    ],
)
def test_load_sources_rejects_bad_inline(inline: list[str]) -> None:
    with pytest.raises(ValueError):
        load_sources(inline_sources=inline, sources_file=None)


def test_load_sources_rejects_invalid_manifest(tmp_path: Path) -> None:
    path = tmp_path / "sources.jsonl"
    path.write_text("{bad json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSONL"):
        load_sources(inline_sources=[], sources_file=str(path))

    path = tmp_path / "sources.json"
    path.write_text('{"not":"an array"}', encoding="utf-8")
    with pytest.raises(ValueError, match="must contain an array"):
        load_sources(inline_sources=[], sources_file=str(path))


def test_source_input_validates_locator_and_date() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        SourceInput(track_id="privacy")
    with pytest.raises(ValueError):
        SourceInput(track_id="privacy", path="./x", published_at="not-a-date")


def test_storage_reports_missing_project_and_records(tmp_path: Path) -> None:
    uninitialized = ProjectStore(tmp_path)
    with pytest.raises(ProjectNotInitializedError):
        uninitialized.require_initialized()

    store = ProjectStore.initialize(tmp_path, name="errors")
    with pytest.raises(RecordNotFoundError):
        store.get_plan("missing")
    with pytest.raises(RecordNotFoundError):
        store.run_record("missing")
    with pytest.raises(RecordNotFoundError):
        store.set_run_status("missing", "RUNNING")
    with pytest.raises(RecordNotFoundError):
        store.get_citation("missing")


def test_memory_search_validates_query(tmp_path: Path) -> None:
    store = ProjectStore.initialize(tmp_path, name="errors")
    with pytest.raises(ValueError, match="must not be empty"):
        store.search_memory("   ", limit=10)
