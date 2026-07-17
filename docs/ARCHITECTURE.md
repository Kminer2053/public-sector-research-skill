# ARCHITECTURE — Local-First Portable Core

[VISION](VISION.md) · [PRD](PRD.md) · [ROADMAP](ROADMAP.md)

## Context

```mermaid
flowchart LR
    U["공공업무 사용자"] --> H["Codex / Claude / Agent Host"]
    H --> S["Universal Agent Skill"]
    H --> W["호스트 검색·브라우저"]
    W --> S
    S --> C["psr CLI + Python Core"]
    C --> N["공식 웹 원문"]
    C --> L["Local .psr Evidence Store"]
    L --> H
```

호스트는 질문 이해와 검색을 담당한다. Core는 계획, 안전 수집, 파싱, 점수, 저장, 보고서를 결정적으로 수행한다.

Planner는 프로필의 base track catalog에서 필수 track을 먼저 선택하고, 질문 keyword·넓은 범위
표현·CLI include/exclude에 따라 optional·conditional track을 결정한다. 활성 track 목록은
결정적 run ID에 포함되며, 선택되지 않은 track은 gap 계산 대상이 아니다.

## Component

```mermaid
flowchart TB
    CLI["cli.py"] --> PLAN["planner.py / profiles.py"]
    CLI --> FLOW["workflow.py"]
    FLOW --> COL["collector.py"]
    FLOW --> PAR["parsers.py"]
    FLOW --> EVI["evidence.py"]
    FLOW --> BRIEF["briefing.py"]
    FLOW --> REP["reporting.py"]
    PLAN --> DB["storage.py"]
    COL --> DB
    PAR --> DB
    EVI --> DB
    REP --> DB
```

## 저장

파일시스템은 원문과 사람이 읽는 extracted Markdown을 저장하고 SQLite는 관계와 검색 색인을 저장한다.

```text
.psr/
├─ project.json
├─ research.db
├─ profiles/
├─ runs/<run-id>/{plan.json,result.json,brief.json,report.md,report.html}
├─ sources/<source-id>/documents/<document-id>/snapshots/<snapshot-id>/
└─ reports/<run-id>.{md,html}
```

ID:

- `source_id`: canonical locator SHA-256
- `document_id`: 원문 bytes SHA-256
- `snapshot_id`: source ID + document hash
- `passage_id`: snapshot ID + locator + text
- `citation_id`: run ID + track ID + passage ID

`brief.json`은 사람이 편집할 수 있는 보고서 입력층이다. `FACT`와 `INFERENCE`는 저장된
`citation_id`가 있어야 하며, 검증을 통과한 brief만 Markdown과 독립형 HTML로 렌더링한다.
HTML은 외부 JavaScript·CSS·폰트 없이 동작하고 원문 URL과 로컬 snapshot을 함께 연결한다.

## 데이터 모델

SQLite MVP entity:

- Project
- ResearchRun
- Source
- Document
- Snapshot
- Passage
- RunSource
- Citation
- Event

Knowledge Graph, Claim, Review, ChangeEvent는 제품 단계 브랜치에서 추가한다.

## 안전 경계

- `http`·`https`만 허용
- URL userinfo, 비표준 port, localhost, private/link-local/reserved IP 차단
- redirect마다 URL 재검증
- robots.txt 명시적 disallow 준수
- 기본 20 MiB parser 상한
- 출처별 timeout과 최대 2회 재시도
- cookie·credential을 저장하거나 전달하지 않음
- 원문 header는 allowlist만 저장

로컬 Skill이므로 운영 서버의 완전한 DNS pinning·sandbox와 동일한 보안 경계는 아니다. 민감한 네트워크에서 실행할 때는 조직의 outbound proxy·sandbox를 추가해야 한다.

## 확장 경계

`main`의 Core는 서버 framework, MCP SDK, OAuth, PostgreSQL을 import하지 않는다. 이후 adapter는 CLI/Core public interface를 호출한다.

```text
main
  └─ portable core

product/local-mcp-adapter
  └─ local MCP → portable core

product/hosted-public-preview
  └─ remote MCP/API → isolated runtime → portable core
```
