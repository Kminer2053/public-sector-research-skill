"""Local research orchestration with partial-success and reuse semantics."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from psr_core.collector import CollectionError, collect
from psr_core.evidence import compose_citations
from psr_core.models import (
    Failure,
    ResearchPlan,
    RunResult,
    SourceInput,
    StoredDocument,
)
from psr_core.parsers import DocumentParseError, parse_document
from psr_core.reporting import build_result_payload, render_markdown
from psr_core.storage import ProjectStore


def load_sources(
    *,
    inline_sources: Sequence[str],
    sources_file: str | None,
) -> List[SourceInput]:
    payloads: List[Dict[str, Any]] = []
    for value in inline_sources:
        if "=" not in value:
            raise ValueError("--source must use TRACK_ID=URL_OR_PATH")
        track_id, locator = value.split("=", 1)
        locator = locator.strip()
        if not track_id.strip() or not locator:
            raise ValueError("--source must use TRACK_ID=URL_OR_PATH")
        if "://" in locator:
            payloads.append({"track_id": track_id.strip(), "url": locator})
        else:
            payloads.append({"track_id": track_id.strip(), "path": locator})
    if sources_file:
        path = Path(sources_file).expanduser().resolve()
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".jsonl":
            for line_number, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    payloads.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"invalid JSONL at {path}:{line_number}: {error}"
                    ) from error
        else:
            decoded = json.loads(text)
            if not isinstance(decoded, list):
                raise ValueError("sources JSON file must contain an array")
            payloads.extend(decoded)
    result = []
    for payload in payloads:
        if not isinstance(payload, dict):
            raise ValueError("each source manifest item must be an object")
        result.append(
            SourceInput(
                track_id=str(payload["track_id"]),
                url=_optional_string(payload.get("url")),
                path=_optional_string(payload.get("path")),
                title=_optional_string(payload.get("title")),
                publisher=_optional_string(payload.get("publisher")),
                source_tier=str(payload.get("source_tier", "UNVERIFIED_WEB")),
                published_at=_optional_string(payload.get("published_at")),
            )
        )
    return result


def execute_run(
    *,
    store: ProjectStore,
    plan: ResearchPlan,
    sources: Sequence[SourceInput],
    refresh: bool,
    reuse_max_age_days: int,
    respect_robots: bool = True,
    max_workers: int = 4,
) -> RunResult:
    track_ids = {track.id for track in plan.tracks}
    if not sources:
        raise ValueError("research run requires at least one source")
    if len(sources) > plan.stop_conditions.max_sources:
        raise ValueError(
            f"source count exceeds plan limit {plan.stop_conditions.max_sources}"
        )
    for source in sources:
        if source.track_id not in track_ids:
            raise ValueError(f"source references unknown track: {source.track_id}")
    store.set_run_status(plan.id, "RUNNING")
    per_source_bytes = max(1, plan.stop_conditions.max_bytes // max(1, len(sources)))
    documents: List[Tuple[SourceInput, StoredDocument]] = []
    failures: List[Failure] = []
    pending: List[SourceInput] = []
    reused_count = 0
    collected_count = 0
    for source in sources:
        reusable = None
        if not refresh:
            reusable = store.reusable_document(
                source,
                max_age_days=reuse_max_age_days,
            )
        if reusable is None:
            pending.append(source)
            continue
        reused_count += 1
        documents.append((source, reusable))
        store.record_run_source(
            run_id=plan.id,
            source=source,
            source_id=reusable.source_id,
            status="REUSED",
        )

    workers = max(1, min(max_workers, 8, len(pending) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                _collect_and_parse,
                source,
                max_bytes=per_source_bytes,
                timeout_seconds=min(plan.stop_conditions.timeout_seconds, 30.0),
                respect_robots=respect_robots,
            ): source
            for source in pending
        }
        for future in as_completed(future_map):
            source = future_map[future]
            try:
                collected, parsed = future.result()
                stored = store.store_document(source, collected, parsed)
                documents.append((source, stored))
                collected_count += 1
                store.record_run_source(
                    run_id=plan.id,
                    source=source,
                    source_id=stored.source_id,
                    status="COLLECTED",
                )
            except CollectionError as error:
                failure = Failure(
                    source_locator=source.locator,
                    track_id=source.track_id,
                    code=error.code,
                    message=error.message,
                    retryable=error.retryable,
                )
                failures.append(failure)
                store.record_run_source(
                    run_id=plan.id,
                    source=source,
                    source_id=None,
                    status="FAILED",
                    failure=failure.to_dict(),
                )
            except DocumentParseError as error:
                failure = Failure(
                    source_locator=source.locator,
                    track_id=source.track_id,
                    code=error.code,
                    message=error.message,
                    retryable=False,
                )
                failures.append(failure)
                store.record_run_source(
                    run_id=plan.id,
                    source=source,
                    source_id=None,
                    status="FAILED",
                    failure=failure.to_dict(),
                )
            except Exception as error:
                failure = Failure(
                    source_locator=source.locator,
                    track_id=source.track_id,
                    code="INTERNAL_ERROR",
                    message=f"source processing failed safely: {error}",
                    retryable=False,
                )
                failures.append(failure)
                store.record_run_source(
                    run_id=plan.id,
                    source=source,
                    source_id=None,
                    status="FAILED",
                    failure=failure.to_dict(),
                )

    documents.sort(key=lambda item: (item[0].track_id, item[1].source_locator))
    failures.sort(key=lambda failure: (failure.track_id, failure.source_locator))
    citations, evidence_gaps, deduplicated_count = compose_citations(
        run_id=plan.id,
        plan=plan,
        documents=documents,
    )
    store.replace_citations(plan.id, citations)
    gaps = list(evidence_gaps)
    if failures:
        gaps.append(
            f"전체 {len(sources)}개 출처 중 {len(failures)}개 처리에 실패하여 "
            "결과가 완전하지 않습니다."
        )
    if not citations:
        gaps.append("검토 가능한 citation이 없어 결론이나 권고를 생성하지 않았습니다.")
    status = "SUCCEEDED" if citations and not gaps and not failures else "PARTIAL"
    payload = build_result_payload(
        plan=plan,
        status=status,
        citations=citations,
        gaps=gaps,
        failures=failures,
        reused_sources=reused_count,
        collected_sources=collected_count,
        deduplicated_count=deduplicated_count,
    )
    markdown = render_markdown(
        plan=plan,
        payload=payload,
        citations=citations,
        gaps=gaps,
        failures=failures,
    )
    paths = store.write_run_outputs(plan.id, result=payload, markdown=markdown)
    store.set_run_status(plan.id, status)
    return RunResult(
        run_id=plan.id,
        status=status,
        summary=str(payload["summary"]),
        citations=citations,
        gaps=gaps,
        failures=failures,
        reused_sources=reused_count,
        collected_sources=collected_count,
        report_path=paths["report_path"],
        result_path=paths["result_path"],
    )


def rebuild_report(store: ProjectStore, run_id: str) -> Dict[str, str]:
    plan = store.get_plan(run_id)
    record = store.run_record(run_id)
    raw_citations = store.list_citations(run_id=run_id)
    from psr_core.models import Citation, EvidenceScore, ScoreComponent

    citations = []
    for item in raw_citations:
        score_payload = item["score"]
        score = EvidenceScore(
            overall=float(score_payload["overall"]),
            authority=ScoreComponent(**score_payload["authority"]),
            primary_source=ScoreComponent(**score_payload["primary_source"]),
            direct_relevance=ScoreComponent(**score_payload["direct_relevance"]),
            original_snapshot=ScoreComponent(**score_payload["original_snapshot"]),
            specificity=ScoreComponent(**score_payload["specificity"]),
            freshness=ScoreComponent(**score_payload["freshness"]),
            independence=ScoreComponent(**score_payload["independence"]),
        )
        citations.append(
            Citation(
                id=item["id"],
                run_id=item["run_id"],
                track_id=item["track_id"],
                passage_id="stored",
                title=item["title"],
                publisher=item["publisher"],
                source_locator=item["source_locator"],
                retrieved_at=item["retrieved_at"],
                locator=item["locator"],
                excerpt=item["excerpt"],
                source_tier=item["source_tier"],
                document_sha256=item["document_sha256"],
                score=score,
            )
        )
    result_path = store.root / "runs" / run_id / "result.json"
    if result_path.exists():
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        payload = build_result_payload(
            plan=plan,
            status=record["status"],
            citations=citations,
            gaps=[],
            failures=[],
            reused_sources=0,
            collected_sources=0,
            deduplicated_count=0,
        )
    gaps = [str(value) for value in payload.get("gaps", [])]
    failures = [
        Failure(
            source_locator=str(value["source_locator"]),
            track_id=str(value["track_id"]),
            code=str(value["code"]),
            message=str(value["message"]),
            retryable=bool(value["retryable"]),
        )
        for value in payload.get("failures", [])
    ]
    markdown = render_markdown(
        plan=plan,
        payload=payload,
        citations=citations,
        gaps=gaps,
        failures=failures,
    )
    return store.write_run_outputs(run_id, result=payload, markdown=markdown)


def _collect_and_parse(
    source: SourceInput,
    *,
    max_bytes: int,
    timeout_seconds: float,
    respect_robots: bool,
) -> Tuple[Any, Any]:
    collected = collect(
        source.locator,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
        respect_robots=respect_robots,
    )
    parsed = parse_document(collected.body, collected.media_type)
    return collected, parsed


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
