# Public Sector Research MCP — Validation Criteria

> 문서 상태: Accepted · 기준일: 2026-07-16 · 현재 대상: **Public Preview PG0~PG3**

[PRD](./PRD.md) · [ARCHITECTURE](./ARCHITECTURE.md) · [IMPLEMENTATION PLAN](./IMPLEMENTATION_PLAN.md) · [THREAT MODEL](./security/THREAT_MODEL.md)

## 1. 목적

이 문서는 “공개 MCP가 잘 작동한다”를 검증 가능한 조건으로 정의한다. Public Preview는 다음 네 가지를 동시에 증명해야 한다.

1. 누구나 로그인 없이 사용할 수 있다.
2. 공식자료 중심의 쓸 만한 결과를 반환한다.
3. 익명 남용, SSRF, parser/resource 공격을 제한한다.
4. 질문·원문·결과를 약속한 TTL보다 오래 보관하지 않는다.

테스트 수와 coverage가 높아도 위 네 조건 중 하나가 실패하면 공개하지 않는다.

## 2. Gate 체계

| Gate | 의미 | 필수 영역 | 현재 상태 |
|---|---|---|---|
| G0~G5 | 기존 Foundation build/domain/MCP/DB/OAuth/Host | Foundation regression | PASS |
| PG0 | Public Boundary Safe | mode, catalog, quota, tmp, purge, no-content telemetry | IN PROGRESS |
| PG1 | Useful Research | planner, collector, parser, evidence, quick | CURATED LIVE SMOKE PASS / HUMAN QA PENDING |
| PG2 | Zero-Retention Async | handle, worker, consume, TTL, crash recovery | NOT IMPLEMENTED |
| PG3 | Public Preview Ready | edge, Host, load/cost, docs, incident rehearsal | NOT IMPLEMENTED |
| AG0 | Account Trust and Reuse | optional identity, opt-in save, freshness-aware reuse, user isolation, export/delete | FUTURE |

Foundation 통과는 Public Preview 통과를 의미하지 않는다. public composition, HMAC IP-first
limiter, ephemeral workspace/purge, Planner, Search port, SafeCollector, parser, Evidence
Composer와 quick 수직 슬라이스는 구현됐고 no-key curated mode의 실제 원문 수집·Evidence·
purge smoke도 통과했다. edge IP normalization, async lifecycle, 사람 유용성·비용·live
provider 보존 검증이 남아 있으므로 공개 endpoint는 아직 열 수 없다.

S0 실행 증적은 [2026-07-16 Public S0 보고서](./validation/2026-07-16-public-s0.md)에 기록한다.
PG1 로컬 수직 슬라이스는
[2026-07-16 PG1 보고서](./validation/2026-07-16-pg1-useful-research.md)에 기록한다.

## 3. 검증 환경

| 환경 | 목적 | 허용되는 주장 |
|---|---|---|
| Unit | policy, planner, TTL, handle, score | deterministic rule 구현 |
| In-memory integration | application/MCP contract | public flow contract 구현 |
| Ephemeral filesystem | permission, purge, orphan | local zero-retention 구현 |
| Network security lab | DNS, redirect, SSRF, malformed server | outbound policy 구현 |
| Document corpus | HTML/PDF/JSON parser | locator·limit·typed failure |
| Remote MCP | HTTPS와 실제 Host | interoperability |
| Staging | edge quota, egress, disk, crash, load | 공개 운영 경계 |
| Limited Preview | 실제 사용자와 비용 | 제품 유용성 |

## 4. 표준 품질 명령

```bash
uv sync --all-groups --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src tests scripts
uv audit --preview-features audit --frozen
uv run --frozen python scripts/dependency_licenses.py --check
uv run --frozen pytest --cov=psr_mcp --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json
uv run --frozen python scripts/coverage_gate.py --coverage-json coverage.json
```

추가 예정:

```bash
uv run --frozen pytest -m public
uv run --frozen pytest -m network_security
uv run --frozen pytest -m purge
uv run --frozen psrctl conformance-public --endpoint https://...
uv run --frozen psrctl verify-retention --ephemeral-root ...
```

실제 command가 구현될 때 CLI help, runbook, CI를 같은 change에서 갱신한다.

## 5. PG0 — Public Boundary Safe

### 5.1 Mode와 Catalog

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-MODE-001 | OAuth token 없이 public server initialize | 성공 |
| VAL-PUB-MODE-002 | public `tools/list` | 승인된 public Tool만 표시 |
| VAL-PUB-MODE-003 | Project/Admin/Persistent Tool | catalog에 0개 |
| VAL-PUB-MODE-004 | public request 중 Membership DB spy | 호출 0회 |
| VAL-PUB-MODE-005 | public request 중 persistent content repository spy | write 0회 |
| VAL-PUB-MODE-006 | public production+HTTP URL | startup 실패 |
| VAL-PUB-MODE-007 | ephemeral root 누락·unsafe permission | startup 실패 |
| VAL-PUB-MODE-008 | TTL이 ADR 최대값 초과 | startup 실패 |
| VAL-PUB-MODE-009 | content telemetry enabled | startup 실패 |
| VAL-PUB-MODE-010 | `service.policy` | 실제 TTL·quota·profile과 일치 |

### 5.2 Abuse와 비용

| ID | 공격/조건 | Expected |
|---|---|---|
| VAL-PUB-ABUSE-001 | 같은 IP 정상 quick 반복 | 설정된 한도 뒤 429/Tool error |
| VAL-PUB-ABUSE-002 | 같은 IP에서 invalid bearer 100개 회전 | IP quota 추가 획득 불가 |
| VAL-PUB-ABUSE-003 | 같은 IP에서 handle/client ID 회전 | IP quota 추가 획득 불가 |
| VAL-PUB-ABUSE-004 | 서로 다른 IP fixture | 독립 IP bucket |
| VAL-PUB-ABUSE-005 | raw IP 저장소·log scan | 0건 |
| VAL-PUB-ABUSE-006 | HMAC bucket key rotation | 이전 counter TTL 뒤 삭제 |
| VAL-PUB-ABUSE-007 | process active quick limit | 설정 상한 초과 quick은 workspace·network 전 거부, 종료 뒤 slot 반환 |
| VAL-PUB-ABUSE-008 | global outbound limit | 동시성 상한 유지 |
| VAL-PUB-ABUSE-009 | source host limit | 한 host가 worker 독점 불가 |
| VAL-PUB-ABUSE-010 | cost/time/byte 상한 | partial 종료, 무한 retry 없음 |
| VAL-PUB-ABUSE-011 | trusted proxy client IP | 정상 단일 IP만 bucket에 사용, header는 downstream에서 제거 |
| VAL-PUB-ABUSE-012 | untrusted peer의 client IP header 위조 | header 변경으로 quota 추가 획득 불가 |
| VAL-PUB-ABUSE-013 | kill switch ON | 새 quick/start 거부 |
| VAL-PUB-ABUSE-014 | kill switch ON | status/result/cancel/purge 유지 |
| VAL-PUB-ABUSE-015 | limiter backend 장애 | 새 고비용 요청 fail closed |
| VAL-PUB-ABUSE-016 | process UTC daily quick budget | invalid·active 초과 미차감, 시작된 성공·실패 차감, 소진 시 workspace·network 전 거부, 다음 UTC 일자 reset |
| VAL-PUB-ABUSE-017 | operator runtime pause | restart 없이 새 quick 거부·policy 반영, 진행 중 purge 유지, resume 가능 |

### 5.3 Ephemeral Store

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-TMP-001 | run directory 이름 | user input 없는 random value |
| VAL-PUB-TMP-002 | directory/file mode | 0700/0600 |
| VAL-PUB-TMP-003 | `../`, absolute path | 거부 |
| VAL-PUB-TMP-004 | symlink target | follow·read·write 거부 |
| VAL-PUB-TMP-005 | concurrent write/purge | purge가 access를 최종 차단 |
| VAL-PUB-TMP-006 | metadata schema | User Content field 없음 |
| VAL-PUB-TMP-007 | disk full | 새 Run 거부, purge 가능 |
| VAL-PUB-TMP-008 | workspace locator | MCP response/log 미노출 |

### 5.4 Retention과 Leakage

| ID | 조건 | Expected |
|---|---|---|
| VAL-PUB-RET-001 | quick 응답 완료 | content 즉시 purge |
| VAL-PUB-RET-002 | delivered async result | 60초 내 접근 불가·삭제 |
| VAL-PUB-RET-003 | completed undelivered | 60분 내 삭제 |
| VAL-PUB-RET-004 | failed Run content | 실패 확정 후 10분 내 삭제 |
| VAL-PUB-RET-005 | running workspace | 기본 60분 정책 |
| VAL-PUB-RET-006 | orphan workspace | 생성 후 절대 2시간 내 삭제 |
| VAL-PUB-RET-007 | process restart | startup sweep 수행 |
| VAL-PUB-RET-008 | periodic sweep | 1분 주기 이내 만료 확인 |
| VAL-PUB-RET-009 | delete permission transient failure | access block 후 eventual delete |
| VAL-PUB-RET-010 | question canary | DB/log/trace/metric/crash output 0건 |
| VAL-PUB-RET-011 | source content canary | TTL 뒤 tmp/DB/log 0건 |
| VAL-PUB-RET-012 | result canary | TTL 뒤 tmp/DB/log 0건 |
| VAL-PUB-RET-013 | full handle canary | log/metric 0건 |
| VAL-PUB-RET-014 | purge alert | content 없이 state/latency만 포함 |

### PG0 판정

다음이 모두 필요하다.

- `AC-PUB-030~033` 공개 endpoint 방어 scenario 통과
- `VAL-PUB-MODE-*`, `ABUSE-*`, `TMP-*`, `RET-*` 100% 통과
- 기존 Foundation regression 100% 통과
- seeded User Content·secret leakage 0건
- 공개 Tool은 아직 fake result여도 lifecycle이 끝까지 동작
- unresolved public P0/P1 0건

## 6. PG1 — Useful Research

### 6.1 Planner

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-PLAN-001 | 10자 미만/4000자 초과 question | network 전 거부 |
| VAL-PUB-PLAN-002 | as-of 누락 | current date 적용·표시 |
| VAL-PUB-PLAN-003 | 공공기관 AI 구매 원칙 | 법령·조달·개인정보·데이터권리 track |
| VAL-PUB-PLAN-004 | 업체종속 질문 | lock-in/데이터 반환·이전성 track |
| VAL-PUB-PLAN-005 | broad question | bounded subquestion 또는 limitation |
| VAL-PUB-PLAN-006 | plan output | evidence requirement와 stop condition 포함 |
| VAL-PUB-PLAN-007 | same input/profile | deterministic baseline |
| VAL-PUB-PLAN-008 | source text의 instruction | plan/policy 변경 불가 |

### 6.2 Network와 SSRF

| ID | 공격 | Expected |
|---|---|---|
| VAL-PUB-NET-001 | `http`, `file`, `ftp`, `data` | 차단 |
| VAL-PUB-NET-002 | URL userinfo | 차단 |
| VAL-PUB-NET-003 | localhost/127.0.0.1/::1 | 차단 |
| VAL-PUB-NET-004 | RFC1918, link-local, multicast, reserved | 차단 |
| VAL-PUB-NET-005 | cloud metadata hostname/IP | 차단 |
| VAL-PUB-NET-006 | public→private redirect | redirect 전 차단 |
| VAL-PUB-NET-007 | redirect chain 초과 | typed failure |
| VAL-PUB-NET-008 | DNS answer 변경/rebinding fixture | private 연결 없음 |
| VAL-PUB-NET-009 | non-443 port | 기본 차단 |
| VAL-PUB-NET-010 | client bearer/cookie seeded | upstream request에 없음 |
| VAL-PUB-NET-011 | direct network call outside adapter | import/static test 실패 |
| VAL-PUB-NET-012 | robots/terms/access restriction | 우회 없이 policy result |

### 6.3 Collector와 Parser

| ID | 조건 | Expected |
|---|---|---|
| VAL-PUB-COL-001 | connect/read timeout | bounded retry 후 typed failure |
| VAL-PUB-COL-002 | oversized response | byte limit에서 중단 |
| VAL-PUB-COL-003 | decompression bomb | ratio/byte limit에서 중단 |
| VAL-PUB-COL-004 | MIME 위장 | sniff 결과로 거부·재분류 |
| VAL-PUB-COL-005 | login/error/empty page | Evidence 제외 |
| VAL-PUB-COL-006 | 일부 source 실패 | 성공 source 보존, PARTIAL |
| VAL-PUB-PARSE-001 | HTML heading fixture | locator 일치 |
| VAL-PUB-PARSE-002 | PDF text fixture | page locator 일치 |
| VAL-PUB-PARSE-003 | scanned PDF | `OCR_REQUIRED`, 허위 text 없음 |
| VAL-PUB-PARSE-004 | JSON fixture | JSON Pointer 일치 |
| VAL-PUB-PARSE-005 | excessive node/page/depth | budget 중단 |
| VAL-PUB-PARSE-006 | malformed document | process crash 없이 failure |
| VAL-PUB-PARSE-007 | malicious embedded instruction | untrusted data로 유지 |

### 6.4 Evidence와 Result

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-EVD-001 | FACT finding | citation 1개 이상 |
| VAL-PUB-EVD-002 | citation 없는 사실 후보 | gap/inference로 하향 |
| VAL-PUB-EVD-003 | official/primary | 명시적 tier |
| VAL-PUB-EVD-004 | 보도자료 재인용 기사 5개 | 독립 근거 5개로 계산하지 않음 |
| VAL-PUB-EVD-005 | 동일 PDF mirror | content hash cluster |
| VAL-PUB-EVD-006 | locator | 채택 citation 95% 이상 완전 |
| VAL-PUB-EVD-007 | score | component와 rationale 존재 |
| VAL-PUB-EVD-008 | total-only score | schema 거부 |
| VAL-PUB-EVD-009 | official original 미확보 | gap 표시 |
| VAL-PUB-EVD-010 | conflict source | 양쪽 citation과 conflict 표시 |
| VAL-PUB-EVD-011 | inference | FACT와 별도 kind |
| VAL-PUB-EVD-012 | excerpt | 길이 상한과 locator 존재 |
| VAL-PUB-EVD-013 | Markdown/JSON | claim/citation ID 동일 |
| VAL-PUB-EVD-014 | result retention | `server_saved=false` 표시 |
| VAL-PUB-EVD-015 | 결과·정책 | 실제 `source_discovery` mode 표시 |
| VAL-PUB-EVD-016 | 한 URL·복수 track | network fetch 1회, track citation 모두 보존 |
| VAL-PUB-EVD-017 | recommendation anchor 하나 누락 | recommendation 생성 안 함 |
| VAL-PUB-EVD-018 | recommendation 생성 | kind 분리, citation 1개 이상 |
| VAL-PUB-EVD-019 | Markdown 결과 | 한국어 필수 heading과 JSON 동일 citation ID |
| VAL-PUB-EVD-020 | recommendation anchor 부족 | track ID와 missing anchor 이름을 gap에 표시 |

### 6.5 Golden Research Scenarios

#### GR-001 공공기관 AI 구매 원칙

- 법령, 조달, 개인정보, 데이터 권리, 업체 종속을 다룬다.
- 공식 source를 우선한다.
- 데이터 반환, 학습 재사용, 기록 이전 관련 주장에 locator가 있다.
- 확인하지 못한 요구는 gap이다.

#### GR-002 법령과 가이드 현행성

- 법령/시행령/행정가이드의 법적 성격을 구분한다.
- 시행일·기준일·적용대상을 표시한다.
- 구버전만 확보하면 stale limitation을 표시한다.

#### GR-003 재인용 분리

- 정부 보도자료, 재인용 기사, 블로그를 provenance chain으로 구분한다.
- 같은 원 출처가 독립성 점수를 부풀리지 않는다.

#### GR-004 부분 실패

- source 5개 중 2개 timeout이어도 나머지로 결과를 만든다.
- 실패 원인, retryability, coverage gap을 표시한다.

### PG1 품질 기준

| Metric | Gate |
|---|---:|
| FACT citation coverage | 100% schema lint, 운영 목표 ≥95% |
| Citation locator completeness | ≥95% |
| 공식 1차 source 비율 | golden corpus ≥70% |
| golden 필수 track recall | 100% |
| critical factual contradiction | 0 |
| unsupported legal conclusion | 0 |
| quick hard deadline | ≤30초 또는 async 안내 |

### 6.6 현재 PG1 판정 규칙

PG1은 두 층으로 판정한다.

1. **Local Implementation:** 통제된 Search·HTTP·document fixture에서 모든 모듈과 failure
   semantics를 검증한다.
2. **Live Official-Source QA:** 실제 공식 source로 GR-001~004를 실행하고 공공업무 담당자가
   claim·citation·gap의 유용성을 검토한다.

2026-07-16 현재 1은 PASS다. 2는 고정 URL 재파싱뿐 아니라 no-key curated mode에서 실제
원문 수집→Evidence→결과→purge까지 PASS했다. 다만 공공업무 담당자 human QA와 범용 live
Search recall은 PENDING이다. 따라서 “제한된 curated 범위의 실제 원문 end-to-end smoke를
검증했다”는 표현은 허용하지만
“공공분야 리서치 품질 검증 완료” 또는 “PG1 최종 PASS”는 허용하지 않는다.

Live QA는 다음을 추가로 충족해야 한다.

- 운영자가 승인한 Search provider 또는 reviewed source seed 사용
- live Search를 사용할 때 외부 provider에 전달되는 query와 provider-side retention 고지
- site별 robots 결과와 Terms/저작권 운영검토
- 실제 공식 1차 source 비율과 locator completeness 측정
- 동적 법령 shell처럼 본문이 빠진 문서의 Evidence 제외
- 동일 원문의 여러 track 연결 보존과 citation `track_id` 노출
- 사람이 읽는 결과에서 unsupported legal conclusion 0건
- generic evidence bundle이 불충분하면 citation-constrained Writer 보강

사람 검토는 `scripts/live_curated_review.py`가 출력하는 표준 packet을 사용한다. 자동 구조
검사는 FACT·RECOMMENDATION citation coverage, locator completeness, unique document 기준
공식 1차자료 비율과 필수 track recall만 판정한다. 업무 적합성, 법적 과잉해석, 상충·누락과
한국어 품질은 자동 PASS로 승격하지 않고 공공업무 담당자가 별도로 판정한다.

### 6.7 Human Review Packet

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-HQA-001 | 구조지표 | citation·locator·official-primary·track recall을 재현 가능하게 계산 |
| VAL-PUB-HQA-002 | 사람 전용 판단 | 업무 적합성·법적 과잉해석·누락·한국어 품질을 자동 PASS 처리하지 않음 |
| VAL-PUB-HQA-003 | capability 비노출 | packet에 feedback token과 operation ID 0건 |
| VAL-PUB-HQA-004 | 보존 경계 | local stdout만 사용하고 server/DB 자동 저장 0건 |
| VAL-PUB-HQA-005 | 근거 적용범위 | 개인정보 근거를 기관 데이터 전체 권리로 확대하지 않음 |

## 7. PG2 — Zero-Retention Async

### 7.1 Handle

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-HANDLE-001 | entropy | CSPRNG 192-bit 이상 |
| VAL-PUB-HANDLE-002 | payload inspection | user/question/time/URL 복원 불가 |
| VAL-PUB-HANDLE-003 | metadata storage | keyed digest만 저장 |
| VAL-PUB-HANDLE-004 | compare | constant-time |
| VAL-PUB-HANDLE-005 | malformed/expired/unknown | 동일 오류 |
| VAL-PUB-HANDLE-006 | result consumed | content 권한 상실 |
| VAL-PUB-HANDLE-007 | concurrent consume | 최대 1회 content 전달 |

### 7.2 Async Flow

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-ASYNC-001 | `start` latency | 2초 내 handle/expires_at |
| VAL-PUB-ASYNC-002 | 새 MCP session의 status | 성공 |
| VAL-PUB-ASYNC-003 | status payload | content 없음 |
| VAL-PUB-ASYNC-004 | result ready | schema-compliant result |
| VAL-PUB-ASYNC-005 | cancel queued | 즉시 purge pending |
| VAL-PUB-ASYNC-006 | cancel running | 새 source 작업 중지 |
| VAL-PUB-ASYNC-007 | worker crash | bounded retry 또는 PARTIAL |
| VAL-PUB-ASYNC-008 | metadata store 장애 | 새 start fail closed |
| VAL-PUB-ASYNC-009 | temp disk full | 새 Run 거부, 기존 purge 유지 |
| VAL-PUB-ASYNC-010 | gateway restart | 기존 handle 조회 가능 |
| VAL-PUB-ASYNC-011 | result too large | bounded summary/citation 반환 |
| VAL-PUB-ASYNC-012 | provider/source 장애 | usable partial |

### PG2 판정

- `AC-PUB-010~013`, `AC-PUB-020~022` 통과
- delivered, expired, cancelled, failed, orphan 모든 상태의 purge 증거
- async content가 persistent MCP Resource나 PostgreSQL evidence table에 없음
- handle leakage 0건

## 8. PG3 — Public Preview Ready

### 8.1 Remote와 Edge

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-EDGE-001 | TLS endpoint | supported cipher/cert 검증 |
| VAL-PUB-EDGE-002 | trusted client IP | app local PASS, 실제 gateway overwrite·spoof rehearsal |
| VAL-PUB-EDGE-003 | edge IP quota | application limiter 앞에서 동작 |
| VAL-PUB-EDGE-004 | request body/time | proxy와 app limit 일치 |
| VAL-PUB-EDGE-005 | egress policy | private network route 없음 |
| VAL-PUB-EDGE-006 | Host 2종 | anonymous quick 실제 호출 |
| VAL-PUB-EDGE-007 | disconnect/reconnect | async result 조회 |
| VAL-PUB-EDGE-008 | service policy | 배포 config와 자동 일치 |
| VAL-PUB-EDGE-009 | operator doctor | local smoke/public config 분리, secret 미노출, 미달 시 exit 5 |
| VAL-PUB-EDGE-010 | public conformance | anonymous policy→quick→purge→재연결, content-free summary |
| VAL-PUB-EDGE-011 | synthetic feedback | 기본 미제출, staging 명시 옵션에서만 1회 검증 |
| VAL-PUB-EDGE-012 | OCI runtime | pinned base, non-root, read-only root, tmpfs workspace, no capabilities, fixture smoke 뒤 root empty |

### 8.2 Load와 Cost

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-PERF-001 | `service.policy` | P95 200ms 이하 |
| VAL-PUB-PERF-002 | async start | P95 2초 이하 |
| VAL-PUB-PERF-003 | quick | P95 30초 이하 또는 async 전환 |
| VAL-PUB-PERF-004 | quota saturation | memory/FD/thread 안정 |
| VAL-PUB-PERF-005 | source slow response | global worker 고갈 없음 |
| VAL-PUB-COST-001 | run cost ceiling | 설정 상한 초과 0 |
| VAL-PUB-COST-002 | daily budget | 도달 시 새 collection 중지 |
| VAL-PUB-COST-003 | kill switch rehearsal | 5분 내 운영 가능 |

### 8.3 Feedback와 개인정보

| ID | 기준 | Expected |
|---|---|---|
| VAL-PUB-FBK-001 | feedback token | payload가 version·nonce·expiry뿐이며 content/run/user/IP 복원 불가 |
| VAL-PUB-FBK-002 | 기본 field | helpful/save interest boolean 2개만 |
| VAL-PUB-FBK-003 | question/result join | raw token·question·result 미저장/미로그 |
| VAL-PUB-FBK-004 | free text | Tool schema에 field 없음 |
| VAL-PUB-FBK-005 | deletion/retention notice | 결과 purge 뒤 token 발급, 사용자에게 명확 |
| VAL-PUB-FBK-006 | 변조·만료·replay | 동일 typed error, single-process 중복 집계 0 |
| VAL-PUB-FBK-007 | aggregate metric | submitted/helpful/save-interest count만 허용 |
| VAL-PUB-FBK-008 | digest expiry | token expiry 뒤 purge sweep interval 이내 process memory에서 제거 |

### 8.4 Release Review

- dependency critical/high 0 또는 승인된 waiver
- secret scan 0
- license/NOTICE 검토
- threat model Public Preview section 승인
- incident·purge failure·cost spike runbook
- kill switch와 rollback rehearsal
- 제한 공개 24~72시간 동안 P0/P1 0
- User Content canary 잔존 0

## 9. Product Validation

PG3는 기술적 공개 가능성이다. Account Beta 시작은 다음 실제 사용 증거를 별도로 요구한다.

| Metric | Trigger |
|---|---:|
| 주간 완료 조사 | 4주 연속 ≥100 |
| 결과 수령률 | ≥60% |
| helpful 응답 수/긍정률 | ≥50 / ≥60% |
| 공식 1차 source 비율 | ≥70% |
| FACT citation coverage | ≥95% |
| 저장·History·reuse 관심 사용자 | ≥20 |
| TTL 이후 content 잔존 | 0 |
| 조사당 비용 | 운영 상한 안에서 안정 |

이 조건이 부족하면 Account 기능 대신 연결 성공률, planner, source coverage, result quality를 개선한다.

## 10. AG0 — Account Trust (Future)

| ID | 기준 | Expected |
|---|---|---|
| VAL-ACC-001 | signup 미선택 public 사용자 | 기존 anonymous flow 유지 |
| VAL-ACC-002 | account default | `retention_mode=ephemeral` |
| VAL-ACC-003 | `retention_mode=ephemeral` 조사 | persistent content 0 |
| VAL-ACC-004 | `retention_mode=saved` 조사 | 해당 사용자 workspace에만 저장 |
| VAL-ACC-005 | cross-user ID guess | opaque denial |
| VAL-ACC-006 | actor FK | cross-tenant user reference DB 거부 |
| VAL-ACC-007 | unknown JWT `kid` flood | bounded JWKS refresh |
| VAL-ACC-008 | export | 저장 조사·metadata 완전 |
| VAL-ACC-009 | delete/account close | DB/object deletion manifest 일치 |
| VAL-ACC-010 | consent version | 저장 시점에 기록 |
| VAL-ACC-011 | `saved` preflight storage 장애 | collection 시작 전 `PERSISTENCE_UNAVAILABLE` |
| VAL-ACC-012 | 익명 완료 run을 account에 귀속 시도 | 자동 귀속 거부, 명시적 import만 허용 |
| VAL-ACC-013 | Account service 장애 | anonymous Public Preview 정상 동작 |
| VAL-ACC-014 | 신규 계정 기본값 | `retention_mode=ephemeral`, `reuse_mode=off` |
| VAL-ACC-015 | `ephemeral + prefer_fresh` | 저장 Evidence read 가능, 새 결과 persistent write 0 |
| VAL-ACC-016 | `saved + prefer_fresh` | fresh 저장근거 재사용, 부족·stale track만 새 조사 |
| VAL-ACC-017 | `saved_only` | outbound network 0, 부족한 근거는 gap |
| VAL-ACC-018 | stale/unknown Evidence | 최신 자료처럼 숨기지 않고 freshness·refresh 상태 표시 |
| VAL-ACC-019 | reuse provenance | reused/new Evidence와 출처·freshness가 결과에 구분됨 |
| VAL-ACC-020 | cross-user Evidence ID guess | reuse candidate와 결과에 포함 0 |
| VAL-ACC-021 | 저장 Evidence 삭제 | delete commit 뒤 reuse lookup 0 |
| VAL-ACC-022 | anonymous import | 사용자 명시 import만 허용, `user_imported` provenance 유지 |
| VAL-ACC-023 | 공개 품질 회귀 | Account 출시 전후 anonymous golden 품질 기준 동일 |

## 11. Foundation Regression

기존 `G0~G5` 검증은 계속 실행한다.

- build, lint, type, coverage
- domain state와 idempotency
- MCP schema/error
- PostgreSQL migration/RLS/lease
- OAuth issuer/audience/JWKS/Membership
- remote Streamable HTTP conformance

Public change가 Account/Enterprise foundation을 깨뜨리지 않아야 한다. 다만 Foundation G6 기관 owner 승인은 Public Preview release gate가 아니다.

## 12. Coverage와 Test 품질

- 전체 statement coverage 90% 이상
- 전체 branch coverage 85% 이상
- public quota, URL policy, handle, purge, evidence lint: statement 95% 이상
- security corpus case 100%
- golden required assertion 100%
- flaky test: 100회 반복 0건 목표
- wall clock, 실제 public internet, random nondeterminism에 직접 의존하지 않음
- network test는 통제된 local malicious server와 resolver fixture 사용

Coverage 수치가 security 또는 retention failure를 상쇄하지 않는다.

## 13. 문서 검증

| ID | 기준 |
|---|---|
| VAL-DOC-001 | 모든 상대 링크 존재 |
| VAL-DOC-002 | Mermaid/code fence 균형 |
| VAL-DOC-003 | PRD→Implementation→Validation 추적 가능 |
| VAL-DOC-004 | ADR status와 현재 제품단계 일치 |
| VAL-DOC-005 | README가 구현/미구현을 사실대로 구분 |
| VAL-DOC-006 | service policy 예시와 config 제한 일치 |
| VAL-DOC-007 | Foundation 문서는 미래 mode 자산임을 표시 |
| VAL-DOC-008 | Open Question에 추천안과 결정시점 존재 |

## 14. 완료 선언 규칙

허용:

> Foundation G0~G5는 검증됐고, Public Preview PG0~PG3는 별도 구현·검증 대상이다.

PG3 전 금지:

- public ready
- anonymous production ready
- zero retention verified
- safe public crawler
- public research quality verified

PG1 Live QA 전 금지:

- useful public-policy answers verified
- official-source golden scenarios passed
- end-to-end zero data retention

R4 제품 지표 전 금지:

- product-market fit
- 사용자가 저장기능을 원한다
- Account Beta가 필요하다

## 15. 검증 기록 양식

```text
Validation ID:
Environment/commit:
Fixture or command:
Expected:
Observed:
Content retained:
Evidence artifact:
Pass/Fail/Blocked:
Reviewer:
Date:
```

---

Public Preview의 최종 기준은 단순하다. **로그인 없이 유용한 근거를 돌려주고, 공격과 비용을 제한하며, 사용자의 content를 약속한 시간 안에 실제로 지워야 한다.**
