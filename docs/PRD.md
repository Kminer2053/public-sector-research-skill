# PRD — Universal Local Skill v0.2

[VISION](VISION.md) · [ARCHITECTURE](ARCHITECTURE.md) · [ROADMAP](ROADMAP.md)

## 목표

공공분야 담당자와 AI 에이전트가 특정 서비스 계정이나 중앙 저장소 없이 공식자료 중심의 조사계획, 로컬 원문 수집, Passage Evidence, 재사용 가능한 보고서를 만들 수 있게 한다.

## In Scope

| ID | 요구사항 | 우선순위 | Acceptance |
|---|---|---|---|
| FR-001 | 로컬 프로젝트 초기화 | Must | `.psr/research.db`, profile, 저장 폴더 생성 |
| FR-002 | Government profile 계획 | Must | 필수 track과 질문 관련 optional·conditional track만 생성 |
| FR-003 | 호스트 독립 source manifest | Must | URL·로컬 파일을 JSON/JSONL로 입력 |
| FR-004 | 안전한 원문 수집 | Must | HTTP(S), public IP, robots, byte, timeout 적용 |
| FR-005 | 문서 파싱 | Must | HTML·JSON·TEXT, 선택 PDF를 Passage로 변환 |
| FR-006 | 구조화 저장 | Must | Source·Document·Snapshot·Passage·Citation을 SQLite에 저장 |
| FR-007 | 중복·재사용 | Must | URL, SHA-256, Passage text 중복 최소화 |
| FR-008 | Evidence Score | Must | 종합점수와 7개 구성요소 설명 저장 |
| FR-009 | 부분성공 | Must | 실패 출처와 성공 Evidence를 함께 보존 |
| FR-010 | 보고서 | Must | citation 검증 brief와 한국어 Markdown·독립형 HTML 생성 |
| FR-011 | Memory 조회 | Must | 저장 Passage와 citation 검색·조회 |
| FR-012 | 호스트 이식성 | Must | 표준 `SKILL.md`, Codex metadata, Claude marketplace 제공 |
| FR-013 | Profile 확장 | Should | `.psr/profiles/*.json` 추가 가능 |

## Out of Scope

- 원격 MCP 서버
- 로그인·계정·조직·RBAC
- 클라우드 저장
- 자동 의미 Diff와 영향분석
- Knowledge Graph
- 자동 법률판단
- 모든 사이트를 지원하는 브라우저 자동화

## CLI 계약

```text
psr project init <path> --name <name>
psr research plan "<question>" [--include-track <id>] [--exclude-track <id>]
psr research run <run-id> --sources-file <json|jsonl>
psr evidence list [--run-id]
psr evidence show <evidence-id>
psr report build <run-id> [--brief-file <json>] [--format md|html|all]
psr memory search "<query>"
psr profile list
psr doctor
```

정상 출력은 stdout JSON, 입력·설정 오류는 stderr JSON과 exit code `2`, 예상하지 못한 내부 오류는 exit code `3`을 사용한다. `PARTIAL`은 조사 상태이며 CLI 실패가 아니므로 exit code `0`이다.

## 비기능 요구사항

| ID | 요구사항 |
|---|---|
| NFR-001 | Python 3.9 이상, 기본 기능은 표준 라이브러리만 사용 |
| NFR-002 | 사용자 콘텐츠를 중앙 서버로 전송하지 않음 |
| NFR-003 | 동일 실행은 deterministic ID와 hash로 중복 최소화 |
| NFR-004 | 한 출처 실패가 전체 결과를 삭제하지 않음 |
| NFR-005 | 원문 bytes와 SHA-256을 저장 |
| NFR-006 | 한국어 보고서에서 사실·해석·권고·gap·부분실패를 분리 |
| NFR-007 | 네트워크 없이 Memory 조회와 보고서 재생성 가능 |
| NFR-008 | HTML은 외부 실행 의존성 없이 사용자 콘텐츠를 escape하고 근거로 이동 가능 |

## Acceptance Scenario

1. 좁은 접근성 질문은 법령·정책 track만, AI 구매 질문은 조달·개인정보·데이터권리 track도 생성한다.
2. 공식 HTML, JSON, PDF 또는 로컬 fixture를 입력하면 원문·Passage·hash가 저장된다.
3. Markdown·HTML 보고서가 citation ID, locator, score breakdown과 원문 링크를 포함한다.
4. 같은 원문을 다시 실행하면 7일 이내 snapshot을 재사용한다.
5. 한 출처가 실패해도 나머지 Evidence와 실패 사유가 `PARTIAL` 결과에 남는다.
6. Codex와 Claude가 동일 `SKILL.md`와 CLI를 사용할 수 있다.
7. 편집한 `brief.json`의 사실·해석은 유효한 citation 없이는 보고서로 만들 수 없다.
