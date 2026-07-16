"""SQLite metadata and filesystem snapshot storage for a local research project."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from psr_core.models import (
    Citation,
    CollectedDocument,
    EvidenceScore,
    ParsedDocument,
    Passage,
    ResearchPlan,
    ScoreComponent,
    SourceInput,
    StoredDocument,
    utc_now,
)
from psr_core.parsers import extracted_markdown
from psr_core.profiles import install_builtin_profiles


class ProjectNotInitializedError(RuntimeError):
    pass


class RecordNotFoundError(LookupError):
    pass


class ProjectStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.expanduser().resolve()
        self.root = self.project_root / ".psr"
        self.db_path = self.root / "research.db"
        self.profile_dir = self.root / "profiles"

    @classmethod
    def initialize(cls, project_root: Path, *, name: str) -> "ProjectStore":
        store = cls(project_root)
        normalized_name = " ".join(name.split())
        if not normalized_name:
            raise ValueError("project name must not be empty")
        store.root.mkdir(parents=True, exist_ok=True)
        for directory in ("runs", "sources", "reports", "exports", "profiles"):
            (store.root / directory).mkdir(parents=True, exist_ok=True)
        project_path = store.root / "project.json"
        if project_path.exists():
            project_payload = json.loads(project_path.read_text(encoding="utf-8"))
        else:
            project_payload = {
                "schema_version": "1.0",
                "id": f"prj-{uuid4().hex}",
                "name": normalized_name,
                "created_at": utc_now(),
                "default_profile": "government",
                "storage": "local-filesystem-and-sqlite",
            }
            project_path.write_text(
                json.dumps(project_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        install_builtin_profiles(store.profile_dir)
        with store.connect() as connection:
            store._migrate(connection)
            connection.execute(
                """
                INSERT INTO project(id, name, created_at, default_profile)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name
                """,
                (
                    project_payload["id"],
                    project_payload["name"],
                    project_payload["created_at"],
                    project_payload["default_profile"],
                ),
            )
        return store

    def require_initialized(self) -> None:
        if not self.db_path.exists() or not (self.root / "project.json").exists():
            raise ProjectNotInitializedError(
                f"project is not initialized: {self.project_root}; run `psr project init`"
            )

    def connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.db_path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        self._migrate(connection)
        return connection

    def save_plan(self, plan: ResearchPlan) -> Path:
        self.require_initialized()
        run_dir = self.root / "runs" / plan.id
        run_dir.mkdir(parents=True, exist_ok=True)
        plan_path = run_dir / "plan.json"
        plan_json = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
        plan_path.write_text(plan_json + "\n", encoding="utf-8")
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_run(
                    id, question, as_of_date, jurisdiction, profile, status,
                    plan_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'PLANNED', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    plan_json=excluded.plan_json,
                    updated_at=excluded.updated_at
                """,
                (
                    plan.id,
                    plan.question,
                    plan.as_of_date,
                    plan.jurisdiction,
                    plan.profile,
                    plan_json,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO event(run_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    plan.id,
                    "PLAN_SAVED",
                    json.dumps({"plan_path": str(plan_path)}, ensure_ascii=False),
                    now,
                ),
            )
        return plan_path

    def get_plan(self, run_id: str) -> ResearchPlan:
        self.require_initialized()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT plan_json FROM research_run WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"research run not found: {run_id}")
        return ResearchPlan.from_dict(json.loads(row["plan_json"]))

    def run_record(self, run_id: str) -> Dict[str, Any]:
        self.require_initialized()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_run WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"research run not found: {run_id}")
        return dict(row)

    def set_run_status(self, run_id: str, status: str) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE research_run SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), run_id),
            )
            if cursor.rowcount != 1:
                raise RecordNotFoundError(f"research run not found: {run_id}")

    def store_document(
        self,
        source: SourceInput,
        collected: CollectedDocument,
        parsed: ParsedDocument,
        *,
        reused: bool = False,
    ) -> StoredDocument:
        self.require_initialized()
        source_locator = collected.final_locator
        source_id = "src-" + hashlib.sha256(source_locator.encode("utf-8")).hexdigest()[:20]
        document_id = "doc-" + collected.sha256[:20]
        snapshot_id = (
            "snp-"
            + hashlib.sha256(f"{source_id}\0{collected.sha256}".encode("utf-8")).hexdigest()[:20]
        )
        title = source.title or parsed.title or _title_from_locator(source_locator)
        publisher = source.publisher or _publisher_from_locator(source_locator)
        snapshot_dir = (
            self.root
            / "sources"
            / source_id
            / "documents"
            / document_id
            / "snapshots"
            / snapshot_id
        )
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        extension = _extension(parsed.kind)
        original_path = snapshot_dir / f"original{extension}"
        extracted_path = snapshot_dir / "extracted.md"
        metadata_path = snapshot_dir / "metadata.json"
        if not original_path.exists():
            original_path.write_bytes(collected.body)
        if not extracted_path.exists():
            extracted_path.write_text(extracted_markdown(parsed), encoding="utf-8")
        stored_passages = [
            Passage(
                id=(
                    "psg-"
                    + hashlib.sha256(
                        f"{snapshot_id}\0{passage.locator}\0{passage.text}".encode("utf-8")
                    ).hexdigest()[:20]
                ),
                text=passage.text,
                locator=passage.locator,
                heading=passage.heading,
            )
            for passage in parsed.passages
        ]
        stored_parsed = ParsedDocument(
            kind=parsed.kind,
            title=parsed.title,
            passages=stored_passages,
            warnings=parsed.warnings,
        )
        metadata = {
            "schema_version": "1.0",
            "source_id": source_id,
            "document_id": document_id,
            "snapshot_id": snapshot_id,
            "requested_locator": collected.requested_locator,
            "final_locator": collected.final_locator,
            "retrieved_at": collected.retrieved_at,
            "status": collected.status,
            "media_type": collected.media_type,
            "sha256": collected.sha256,
            "headers": collected.headers,
            "warnings": collected.warnings + parsed.warnings,
            "source": asdict(source),
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO source(
                    id, canonical_locator, title, publisher, source_tier, published_at,
                    first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    publisher=excluded.publisher,
                    source_tier=excluded.source_tier,
                    published_at=COALESCE(excluded.published_at, source.published_at),
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    source_id,
                    source_locator,
                    title,
                    publisher,
                    source.source_tier,
                    source.published_at,
                    now,
                    collected.retrieved_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO document(id, sha256, media_type, title, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (document_id, collected.sha256, collected.media_type, title, now),
            )
            connection.execute(
                """
                INSERT INTO snapshot(
                    id, source_id, document_id, retrieved_at, original_path,
                    extracted_path, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET retrieved_at=excluded.retrieved_at
                """,
                (
                    snapshot_id,
                    source_id,
                    document_id,
                    collected.retrieved_at,
                    str(original_path.relative_to(self.root)),
                    str(extracted_path.relative_to(self.root)),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            for passage in stored_passages:
                connection.execute(
                    """
                    INSERT INTO passage(
                        id, snapshot_id, locator, heading, text, text_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        passage.id,
                        snapshot_id,
                        passage.locator,
                        passage.heading,
                        passage.text,
                        hashlib.sha256(passage.text.encode("utf-8")).hexdigest(),
                    ),
                )
        return StoredDocument(
            source_id=source_id,
            document_id=document_id,
            snapshot_id=snapshot_id,
            title=title,
            publisher=publisher,
            source_tier=source.source_tier,
            source_locator=source_locator,
            published_at=source.published_at,
            collected=collected,
            parsed=stored_parsed,
            reused=reused,
        )

    def reusable_document(
        self,
        source: SourceInput,
        *,
        max_age_days: int,
    ) -> Optional[StoredDocument]:
        self.require_initialized()
        if max_age_days < 0:
            return None
        locator = str(Path(source.path).expanduser().resolve()) if source.path else source.url or ""
        if source.url:
            try:
                from psr_core.collector import canonicalize_url

                locator = canonicalize_url(source.url)
            except Exception:
                return None
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=max_age_days
        )
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    s.id AS source_id, s.canonical_locator, s.title, s.publisher,
                    s.source_tier, s.published_at,
                    sn.id AS snapshot_id, sn.retrieved_at, sn.original_path,
                    sn.metadata_json,
                    d.id AS document_id, d.sha256, d.media_type
                FROM source s
                JOIN snapshot sn ON sn.source_id = s.id
                JOIN document d ON d.id = sn.document_id
                WHERE s.canonical_locator = ?
                ORDER BY sn.retrieved_at DESC
                LIMIT 1
                """,
                (locator,),
            ).fetchone()
            if row is None or _parse_timestamp(row["retrieved_at"]) < cutoff:
                return None
            passage_rows = connection.execute(
                """
                SELECT id, locator, heading, text
                FROM passage
                WHERE snapshot_id = ?
                ORDER BY rowid
                """,
                (row["snapshot_id"],),
            ).fetchall()
        original_path = self.root / row["original_path"]
        if not original_path.exists():
            return None
        metadata = json.loads(row["metadata_json"])
        body = original_path.read_bytes()
        collected = CollectedDocument(
            requested_locator=metadata.get("requested_locator", locator),
            final_locator=row["canonical_locator"],
            status=int(metadata.get("status", 200)),
            headers=dict(metadata.get("headers", {})),
            media_type=row["media_type"],
            body=body,
            sha256=row["sha256"],
            retrieved_at=row["retrieved_at"],
            warnings=["reused local snapshot"],
        )
        parsed = ParsedDocument(
            kind=_kind_from_path(original_path),
            title=row["title"],
            passages=[
                Passage(
                    id=passage["id"],
                    text=passage["text"],
                    locator=passage["locator"],
                    heading=passage["heading"],
                )
                for passage in passage_rows
            ],
            warnings=["reused local snapshot"],
        )
        return StoredDocument(
            source_id=row["source_id"],
            document_id=row["document_id"],
            snapshot_id=row["snapshot_id"],
            title=source.title or row["title"],
            publisher=source.publisher or row["publisher"],
            source_tier=(
                row["source_tier"]
                if source.source_tier == "UNVERIFIED_WEB"
                else source.source_tier
            ),
            source_locator=row["canonical_locator"],
            published_at=source.published_at or row["published_at"],
            collected=collected,
            parsed=parsed,
            reused=True,
        )

    def record_run_source(
        self,
        *,
        run_id: str,
        source: SourceInput,
        source_id: Optional[str],
        status: str,
        failure: Optional[Dict[str, Any]] = None,
    ) -> None:
        key = source_id or (
            "failed-" + hashlib.sha256(source.locator.encode("utf-8")).hexdigest()[:20]
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO run_source(
                    run_id, source_key, source_id, track_id, requested_locator,
                    status, failure_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, source_key, track_id) DO UPDATE SET
                    status=excluded.status,
                    failure_json=excluded.failure_json
                """,
                (
                    run_id,
                    key,
                    source_id,
                    source.track_id,
                    source.locator,
                    status,
                    json.dumps(failure, ensure_ascii=False) if failure else None,
                ),
            )

    def replace_citations(self, run_id: str, citations: List[Citation]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM citation WHERE run_id = ?", (run_id,))
            for citation in citations:
                connection.execute(
                    """
                    INSERT INTO citation(
                        id, run_id, passage_id, track_id, excerpt, score_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        citation.id,
                        run_id,
                        citation.passage_id,
                        citation.track_id,
                        citation.excerpt,
                        json.dumps(citation.score.to_dict(), ensure_ascii=False),
                        utc_now(),
                    ),
                )

    def list_citations(self, *, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self.require_initialized()
        query = """
            SELECT
                c.id, c.run_id, c.track_id, c.excerpt, c.score_json,
                p.locator, p.heading, p.text,
                s.title, s.publisher, s.canonical_locator, s.source_tier,
                sn.retrieved_at, d.sha256
            FROM citation c
            JOIN passage p ON p.id = c.passage_id
            JOIN snapshot sn ON sn.id = p.snapshot_id
            JOIN source s ON s.id = sn.source_id
            JOIN document d ON d.id = sn.document_id
        """
        parameters: tuple = ()
        if run_id:
            query += " WHERE c.run_id = ?"
            parameters = (run_id,)
        query += " ORDER BY c.run_id, c.track_id, c.id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "track_id": row["track_id"],
                "title": row["title"],
                "publisher": row["publisher"],
                "source_locator": row["canonical_locator"],
                "source_tier": row["source_tier"],
                "retrieved_at": row["retrieved_at"],
                "locator": row["locator"],
                "excerpt": row["excerpt"],
                "document_sha256": row["sha256"],
                "score": json.loads(row["score_json"]),
            }
            for row in rows
        ]

    def get_citation(self, citation_id: str) -> Dict[str, Any]:
        rows = [row for row in self.list_citations() if row["id"] == citation_id]
        if not rows:
            raise RecordNotFoundError(f"evidence citation not found: {citation_id}")
        return rows[0]

    def search_memory(self, query: str, *, limit: int) -> List[Dict[str, Any]]:
        normalized = " ".join(query.split())
        if not normalized:
            raise ValueError("memory search query must not be empty")
        pattern = f"%{normalized}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.id AS passage_id, p.locator, p.heading, p.text,
                    s.id AS source_id, s.title, s.publisher, s.canonical_locator,
                    s.source_tier, sn.retrieved_at, d.sha256
                FROM passage p
                JOIN snapshot sn ON sn.id = p.snapshot_id
                JOIN source s ON s.id = sn.source_id
                JOIN document d ON d.id = sn.document_id
                WHERE p.text LIKE ? OR p.heading LIKE ? OR s.title LIKE ?
                ORDER BY sn.retrieved_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [
            {
                "passage_id": row["passage_id"],
                "source_id": row["source_id"],
                "title": row["title"],
                "publisher": row["publisher"],
                "source_locator": row["canonical_locator"],
                "source_tier": row["source_tier"],
                "retrieved_at": row["retrieved_at"],
                "locator": row["locator"],
                "heading": row["heading"],
                "text": row["text"],
                "document_sha256": row["sha256"],
            }
            for row in rows
        ]

    def write_run_outputs(
        self,
        run_id: str,
        *,
        result: Dict[str, Any],
        markdown: str,
    ) -> Dict[str, str]:
        run_dir = self.root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        result_path = run_dir / "result.json"
        report_path = run_dir / "report.md"
        stable_report_path = self.root / "reports" / f"{run_id}.md"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report_path.write_text(markdown, encoding="utf-8")
        stable_report_path.write_text(markdown, encoding="utf-8")
        return {
            "result_path": str(result_path),
            "report_path": str(report_path),
            "stable_report_path": str(stable_report_path),
        }

    def _migrate(self, connection: sqlite3.Connection) -> None:
        connection.executescript(_SCHEMA)


def _score_from_dict(payload: Dict[str, Any]) -> EvidenceScore:
    return EvidenceScore(
        overall=float(payload["overall"]),
        authority=ScoreComponent(**payload["authority"]),
        primary_source=ScoreComponent(**payload["primary_source"]),
        direct_relevance=ScoreComponent(**payload["direct_relevance"]),
        original_snapshot=ScoreComponent(**payload["original_snapshot"]),
        specificity=ScoreComponent(**payload["specificity"]),
        freshness=ScoreComponent(**payload["freshness"]),
        independence=ScoreComponent(**payload["independence"]),
    )


def _extension(kind: str) -> str:
    return {
        "HTML": ".html",
        "JSON": ".json",
        "PDF": ".pdf",
        "TEXT": ".txt",
    }.get(kind, ".bin")


def _kind_from_path(path: Path) -> str:
    return {
        ".html": "HTML",
        ".htm": "HTML",
        ".json": "JSON",
        ".pdf": "PDF",
        ".txt": "TEXT",
        ".md": "TEXT",
    }.get(path.suffix.lower(), "TEXT")


def _title_from_locator(locator: str) -> str:
    if "://" in locator:
        tail = locator.rstrip("/").rsplit("/", 1)[-1]
        return tail or locator
    return Path(locator).name


def _publisher_from_locator(locator: str) -> str:
    if "://" not in locator:
        return "Local file"
    from urllib.parse import urlsplit

    return (urlsplit(locator).hostname or "Unknown publisher").lower()


def _parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


_SCHEMA = """
CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    default_profile TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_run (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    profile TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source (
    id TEXT PRIMARY KEY,
    canonical_locator TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    source_tier TEXT NOT NULL,
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    media_type TEXT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshot (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source(id),
    document_id TEXT NOT NULL REFERENCES document(id),
    retrieved_at TEXT NOT NULL,
    original_path TEXT NOT NULL,
    extracted_path TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(source_id, document_id)
);

CREATE TABLE IF NOT EXISTS passage (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES snapshot(id),
    locator TEXT NOT NULL,
    heading TEXT,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_passage_snapshot ON passage(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_passage_text_hash ON passage(text_sha256);

CREATE TABLE IF NOT EXISTS run_source (
    run_id TEXT NOT NULL REFERENCES research_run(id),
    source_key TEXT NOT NULL,
    source_id TEXT REFERENCES source(id),
    track_id TEXT NOT NULL,
    requested_locator TEXT NOT NULL,
    status TEXT NOT NULL,
    failure_json TEXT,
    PRIMARY KEY(run_id, source_key, track_id)
);

CREATE TABLE IF NOT EXISTS citation (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES research_run(id),
    passage_id TEXT NOT NULL REFERENCES passage(id),
    track_id TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    score_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_citation_run ON citation(run_id);

CREATE TABLE IF NOT EXISTS event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES research_run(id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
