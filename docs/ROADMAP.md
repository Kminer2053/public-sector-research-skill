# Public Sector Research MCP — Roadmap

> 문서 상태: Accepted · 기준일: 2026-07-16 · 현재 목표: **Public Preview**

[VISION](./VISION.md) · [PRD](./PRD.md) · [ARCHITECTURE](./ARCHITECTURE.md) · [IMPLEMENTATION PLAN](./IMPLEMENTATION_PLAN.md) · [VALIDATION CRITERIA](./VALIDATION_CRITERIA.md) · [ADR-0010](./adr/0010-progressive-identity-and-opt-in-persistence.md)

## 1. 구현 전략

제품은 가입·저장·조직 기능을 먼저 완성하지 않는다. 다음 질문을 가장 싼 순서로 검증한다.

1. 공개 MCP endpoint를 안전하게 운영할 수 있는가?
2. 공공업무 질문에 공식 원문이 연결된 유용한 결과를 만들 수 있는가?
3. 질문·원문·결과를 장기 저장하지 않고도 긴 조사를 완료할 수 있는가?
4. 사람들이 반복 사용하고 저장·History를 실제로 원하는가?
5. 그때 선택 가입과 유료 저장이 지속 가능한가?

```text
검증된 Foundation
→ R1 공개 안전 기반
→ R2 빠른 Evidence Research
→ R3 Ephemeral Async
→ R4 Public Preview 운영·학습
→ R5 Opt-in Account Beta
→ R6 Paid Persistent
→ R7 Team / Public-Sector Enterprise
```

로드맵의 핵심 원칙은 다음과 같다.

- Public Preview의 기본값은 무가입·무보관이다.
- Foundation의 OAuth·PostgreSQL·RLS는 폐기하지 않지만 공개 요청의 필수 경로에서 제외한다.
- 공개 전 필수조건은 로그인보다 IP quota, SSRF, resource budget, purge, kill switch다.
- 조사 품질은 Tool 호출 수가 아니라 공식 근거 비율, citation 연결, 결과 수령, 사용자 유용성으로 평가한다.
- 선택 가입은 달력 일정이 아니라 사용자 수요 trigger로 시작한다.
- 유료화는 저장·장기실행 비용과 지불 의사가 확인된 뒤 진행한다.

## 2. 단계 요약

| 단계 | 목표 | 주요 산출물 | 진입/종료 판단 |
|---|---|---|---|
| R0 Foundation | MCP·OAuth·PostgreSQL·Host 기반 검증 | 현재 code와 G0~G5 증적 | 완료, 미래 mode 자산 |
| R1 Public Safety Core | 익명 endpoint를 안전하게 열 기반 마련 | public mode, quota, ephemeral store, purge | Public Safety Gate |
| R2 Useful Quick Research | 30초 이내 공식자료 중심 결과 | Planner/Profile, SafeCollector, Composer, quick Tool | Research Quality Gate |
| R3 Ephemeral Async | 긴 조사를 짧은 TTL로 수행·전달 | start/status/result/cancel, worker, sweeper | Zero-Retention Gate |
| R4 Public Preview | 실제 사용자에게 공개하고 효용 검증 | 배포, feedback, cost/quality 지표 | Product Validation Gate |
| R5 Account Beta | 희망 사용자만 저장·재사용 | OIDC, Personal Workspace, opt-in save | Account Trust Gate |
| R6 Paid Persistent | 저장·장기실행을 지속 가능한 서비스로 제공 | quota, billing, storage, backup/delete | Paid Reliability Gate |
| R7 Enterprise | 기관 팀·감사·보존 요구 지원 | SSO, Organization, RLS, Review, audit | Enterprise Readiness Gate |

## 3. R0 — Foundation Assets

### 상태

완료. 다음 기능은 이미 구현·검증된 자산이다.

- Python 3.12 package와 MCP `2025-11-25` Streamable HTTP
- Tool·Resource·Prompt schema와 capability-aware Host conformance
- domain/application/storage adapter 분리
- ResearchRun·Job state, idempotency, lease, retry, cancellation
- PostgreSQL persistence, migration, RLS
- OAuth/OIDC JWT·JWKS·Membership
- request size·timeout·process-local rate boundary
- structured audit와 coverage/supply-chain 검증

### Public Preview에서 재사용

- MCP composition과 schema/error convention
- bounded HTTP middleware, request ID, timeout
- Job lifecycle과 worker lease의 핵심 개념
- configuration fail-closed pattern
- conformance, coverage, dependency audit CI

### Public Preview에서 사용하지 않는 것

- 사용자 질문·원문·결과의 PostgreSQL 영구저장
- OAuth 로그인과 Membership 확인
- Organization/Project 승인 workflow
- persistent Resource로 결과 제공

### 후속 수정

- `research_runs.initiated_by`를 tenant composite FK로 강화: R5 전 Must
- unknown JWT `kid` JWKS refresh negative cache/cooldown: R5 전 Must
- `psrctl doctor`의 public backend/fixture/readiness 표시 정확성: R2에서 완료

## 4. R1 — Public Safety Core

### 목표

실제 검색·수집을 붙이기 전에 익명 요청을 제한하고 content를 임시로 처리·삭제하는 실행경계를 만든다.

> 구현 상태: 2026-07-16 기준 public mode, 익명 policy/quick Tool, IP-first limiter,
> trusted edge IP normalization, process-local active quick 상한, filesystem workspace,
> process-local UTC daily quick budget, content canary, immediate purge, quick kill switch와
> operator runtime pause-file signal, sweeper는 완료됐다. 실제 gateway quota, provider billing
> hard cap, multi-replica 공유 quota와 삭제 retry/backoff alert가 남아 있어 R1/PG0 전체는
> 아직 종료되지 않았다.

### 작업 패키지

#### WP-R1.1 Service Mode와 Public Catalog

- `ServiceMode.PUBLIC_EPHEMERAL` 추가
- public 전용 composition root
- token 없이 호출 가능한 `psr.service.policy`
- 기존 Project/Admin Tool을 public catalog에서 제거
- Public mode에서 OAuth·Membership·persistent content repository를 호출하지 않는 import/contract test

**난이도:** 중간
**완료 기준:** 익명 `service.policy` 성공, public Tool snapshot에 관리 Tool 0개

#### WP-R1.2 Public Abuse Boundary

- edge raw IP quota 계약
- application rotating-HMAC IP bucket
- trusted proxy CIDR에서만 canonical client IP header를 소비하고 downstream 전달 전 제거
- quick/start/active run/global concurrency limit
- token·invalid bearer·handle 변경으로 IP quota를 우회하지 못하는 test
- `Retry-After`, stable error code
- 새 조사만 중단하는 kill switch

**난이도:** 높음
**현재:** application IP-first limiter, trusted proxy normalization, process-local active quick
상한, UTC daily quick budget과 operator runtime pause는 local PASS. 실제 edge header
overwrite, provider billing hard cap과 multi-replica 공유 quota는 R4에서 검증한다.

**완료 기준:** `VAL-PUB-ABUSE-*` 전부 통과

#### WP-R1.3 Ephemeral Workspace

- `EphemeralWorkspaceStore` port
- restrictive permission의 random run directory
- content와 operational metadata 분리
- running, failed, delivered, undelivered TTL
- startup orphan scan과 periodic sweeper
- 삭제 실패 시 접근 차단 후 retry

**난이도:** 높음
**완료 기준:** fake clock, crash, restart, permission failure purge test 통과

#### WP-R1.4 Content-Free Observability

- log/trace/metric field allowlist
- 질문·검색어·URL credential·원문·결과·handle·raw IP 금지
- canary 기반 leakage scanner
- purge latency, status, failure, cost bucket만 관찰

**난이도:** 중간
**완료 기준:** 정상·오류·crash 경로 canary 잔존 0건

#### WP-R1.5 Operator Readiness Gate

- read-only `psrctl doctor`가 backend, ephemeral root, secret availability, trusted proxy,
  daily budget과 runtime pause를 check별 pass/warn/fail로 표시
- local smoke와 production 공개 설정 준비를 분리
- CI/pre-deploy용 `--require-public-ready` exit 5
- gateway·provider·staging·사용자 검증은 external pending gate로 유지

**현재:** local implementation PASS. 실제 배포환경 preflight 실행은 R4에서 검증한다.

**완료 기준:** `VAL-PUB-EDGE-009` local PASS와 staging 증적

### R1 종료 게이트

- 익명 endpoint의 IP quota 우회가 불가능하다.
- content는 persistent DB와 일반 telemetry에 들어가지 않는다.
- TTL이 ADR-0009보다 길면 startup이 실패한다.
- kill switch 중에도 result 조회·cancel·purge가 계속된다.
- 현재 단계에서는 fake research 결과여도 lifecycle 전체가 검증된다.

## 5. R2 — Useful Quick Research

### 목표

공공분야 질문 하나를 받아 공식자료 중심의 근거가 연결된 결과를 30초 내 반환한다.

### 작업 패키지

#### WP-R2.1 Legacy Collector Characterization

- 기존 `adaptive-web-research`와 `crawlkit.py` command/input/output/failure fixture 작성
- HTML, PDF, JSON, redirect, empty/login page, malformed content 동작 기록
- fetch, MIME detection, extraction, hash의 `reuse/refactor/replace` 분류
- 기존 code를 통째로 복사하지 않고 adapter 뒤 선택적 추출

**난이도:** 중간  
**완료 기준:** 재사용 판단표와 고정 fixture가 code 이식보다 먼저 merge

**상태:** 완료. `docs/analysis/legacy-crawlkit-characterization.md`에 source hash, 실제 저장 사례,
MIME/empty/403 failure와 이식 판단을 기록했다.

#### WP-R2.2 Safe Search and URL Policy

- `SearchProvider` port와 provider 1종
- Government Profile의 공식 domain/tier 우선 query
- HTTPS·port·userinfo·DNS/IP·redirect 정책
- private/link-local/loopback/reserved/metadata endpoint 차단
- user credential 미수용·미전달

**난이도:** 매우 높음
**완료 기준:** SSRF·redirect·DNS rebinding corpus 100% 차단

**상태:** 로컬 구현 완료. HTTPS/userinfo/port/hostname/IP/redirect 정책과 검증 IP 고정
transport, `SearchProvider` port, official domain registry, no-key curated source provider와
선택형 Brave adapter가 구현됐다. curated actual-source smoke는 통과했고, live Search
credential, 운영 edge/network egress와 비용상한 검증은 남아 있다.

#### WP-R2.3 Bounded Collector and Parser

- response/header/compressed/raw/decompressed byte 제한
- connect/read/total timeout과 retry budget
- MIME sniff, login/error/empty document 판별
- HTML main text·heading locator
- PDF text·page locator, scanned PDF는 `OCR_REQUIRED`
- JSON bounded traversal과 JSON Pointer
- parser time/memory/page/depth 제한

**난이도:** 매우 높음  
**완료 기준:** bomb fixture가 process를 고갈시키지 않고 typed partial failure 반환

**상태:** 로컬 구현 완료. SafeCollector의 timeout/byte/redirect/encoding 제한, robots 선검사,
MIME sniff, HTML·JSON·text locator와 subprocess PDF parser를 구현했다. 실제 대형·복잡한
공공 PDF corpus와 운영 OS resource isolation은 추가 검증 대상이다.

#### WP-R2.4 Planner and Government Profile v0

- 기준일·관할·결정 질문·조사 질문 정규화
- 법령, 정책, 공공기관, 조달, 개인정보, 국제표준 source track
- 문서·byte·시간·source budget
- 완료조건과 stop condition
- LLM 없이도 동작하는 deterministic baseline

**난이도:** 높음
**완료 기준:** AI 구매 원칙 golden question의 필수 track recall 통과

**상태:** deterministic baseline과 실제 search query generation/source registry 연결 완료.
실제 공공질문에서 track precision과 provider 비용은 운영 검증 대상이다.

#### WP-R2.5 Evidence Composer and Quick Tool

- FACT·INFERENCE·RECOMMENDATION 분리
- citation local ID, publisher, URL, retrieved_at, locator, excerpt, source tier
- canonical URL과 content hash 기반 최소 dedup
- 공식 1차자료와 재인용 구분
- gap, conflict, failure, limitation
- Markdown/JSON 동등성
- `psr.research.quick`

**난이도:** 높음
**완료 기준:** citation 없는 FACT 0개, locator completeness 95% 이상

**상태:** 로컬 수직 슬라이스와 고정 URL Evidence 선택, no-key curated 실제 quick smoke 완료.
component score, track-aware URL/passage/document hash dedup, citation `track_id`, 한·영 passage
선택, shared URL single fetch, Markdown/JSON, partial failure와 purge-after-quick을 구현했다.
anchor-complete track에만 조달 원칙 후보를 만드는 deterministic Writer도 구현했다.
권고를 만들지 못한 track은 부족한 anchor 이름을 확인 필요사항으로 공개한다.
Markdown은 조사 요약, 조달 원칙 검토안, 확인한 사실, 근거, 확인 필요사항을 분리한 한국어
검토 문서로 렌더링한다.
공공업무 담당자의 초안 유용성, live Search recall과 conflict/recommendation 표현 품질은
아직 승인되지 않았다.

### R2 종료 게이트

- quick 호출은 30초 안에 결과 또는 async 전환 안내를 반환한다.
- 공공기관 AI 구매 원칙 scenario에서 필수 track과 공식 원문을 보여준다.
- 일부 source 실패에도 usable partial 결과를 반환한다.
- 질문·원문·결과 canary는 응답 후 남지 않는다.

**현재 판정:** deterministic/local implementation, 고정 URL Evidence와 curated 실제
수집→결과→purge smoke는 통과했지만 R2 종료 게이트는 열려 있다. 사람의 유용성 검토,
GR-002~004 확대, 법령 source adapter, 선택형 live provider 비용·보존 고지가 남았다.

## 6. R3 — Ephemeral Async

### 목표

다중 PDF처럼 긴 조사를 연결 유지 없이 수행하되 결과 전달 또는 TTL 뒤 content를 삭제한다.

### 작업 패키지

- `psr.research.start`
- `psr.research.run.status`
- `psr.research.run.result`
- `psr.research.run.cancel`
- 192-bit 이상 opaque handle과 keyed digest
- content 없는 operational run metadata
- ephemeral worker claim/heartbeat/retry/cancel
- delivered purge 60초, undelivered 60분, hard orphan 2시간
- process restart와 worker crash 복구
- 결과 크기 제한과 `consume=true`

### 주요 결정

- 단일 node encrypted tmpdir와 작은 worker pool로 시작한다.
- multi-region, Redis cluster, distributed object store는 도입하지 않는다.
- Public Preview는 결과 복구 SLA보다 삭제 신뢰성을 우선한다.
- metadata store 장애 시 새 async Run은 fail closed한다.

### R3 종료 게이트

- 새 MCP 연결에서 handle로 status/result 조회가 가능하다.
- handle은 질문·사용자·URL 정보를 encode하지 않는다.
- 결과 수령 후 60초 이내 content 접근이 불가능하고 삭제된다.
- crash/restart 뒤 orphan content가 절대 TTL을 넘지 않는다.
- 만료·오입력 handle은 동일 오류를 반환한다.

## 7. R4 — Public Preview

### 목표

실제 사용자가 가입 없이 연결해 제품의 유용성, 안전성, 비용을 검증한다.

### 출시 준비

- 공개 TLS endpoint와 최소 WAF/edge IP quota
- 지원 MCP Host 2종 연결 가이드
- `service.policy`의 실제 한도·TTL·외부 provider 고지
- 공개 상태 페이지 또는 최소 운영 공지
- dependency/license/secret scan
- abuse·비용 alert와 운영 kill switch rehearsal
- incident, purge failure, source block runbook
- boolean helpful + save/history interest feedback

### 운영 학습

- 실패율이 높은 질문 유형과 source track 파악
- 공식 1차자료 비율과 citation completeness 측정
- 결과 수령률과 helpful 비율 측정
- 평균·상위 cost bucket과 rate-limit 빈도 측정
- 저장·History·재사용 요청자 수 측정
- 질문 본문 없이 profile·status·count 단위로만 집계

### Public Preview 성공 기준

다음을 모두 만족하면 R5 검토를 시작한다.

1. 4주 연속 주간 완료 조사 100건 이상
2. 결과 수령률 60% 이상
3. helpful 응답 50건 이상, 긍정률 60% 이상
4. 공식 1차 source 비율 70% 이상
5. FACT citation coverage 95% 이상
6. TTL 이후 content 잔존 0건
7. 저장·History·재사용 요청 20명 이상
8. abuse와 조사당 비용이 운영 상한 안에서 안정

조건이 미달하면 가입 기능을 만들지 않고 조사 품질·연결 편의·source coverage를 개선한다.

## 8. R5 — Opt-in Account Beta

### 시작 조건

- R4 Product Validation Gate 통과
- 계정과 저장에 대한 Privacy/Security 설계 승인
- 사용자가 저장하지 않는 mode를 계속 선택할 수 있음

### 기능

- Google/Microsoft 등을 지원하는 OIDC broker
- self-service signup과 Personal Workspace
- `save=true`인 조사만 persistent store로 이동
- 저장한 조사 History·검색·재사용
- `saved` preflight 실패 시 조사 시작 전 명시적 거부
- 익명 완료 결과는 자동 소급 귀속하지 않고 export/import로만 이전
- 기존 저장 근거의 freshness 표시
- export/delete/account close
- 저장 동의 version과 retention 표시
- account mode에서도 기본은 ephemeral

### Foundation 보강

- tenant actor composite FK
- JWKS unknown `kid` negative cache/cooldown
- account별 abuse·quota
- Personal Workspace RLS
- persistent object namespace와 encryption

### 종료 기준

- 가입하지 않은 공개 사용 흐름이 그대로 유지된다.
- `save=false` 조사 content가 persistent store에 남지 않는다.
- 사용자가 저장한 조사만 History에 나타난다.
- export/delete가 저장 metadata와 object를 일관되게 처리한다.
- cross-user data 접근 성공 0건이다.

## 9. R6 — Paid Persistent Service

### 시작 조건

- 반복 사용자와 저장 사용량이 존재
- 높은 quota·장기실행·저장에 대한 지불 의사 확인
- 저장·전송·모델·검색 provider 원가 측정 가능

### 기능

- 저장공간·run time·source count quota
- 장기 ResearchRun과 예약 refresh
- 고급 Research Profile
- Evidence reuse와 Project Memory
- Markdown, JSON, JSONL, HTML, CSV, citation bundle
- backup/restore와 삭제 manifest
- billing meter, invoice/refund/error policy
- encryption key rotation과 support process

### 종료 기준

- billing과 실제 resource usage 차이가 허용 오차 안이다.
- backup/restore와 계정 삭제 rehearsal이 통과한다.
- 저장 약속, 보존기간, 환불·장애 정책이 명확하다.
- 무결제 Public Preview의 안전·품질이 악화되지 않는다.

## 10. R7 — Team / Public-Sector Enterprise

### 기능

- Organization, Membership, institution SSO
- Project 격리와 PostgreSQL RLS
- Plan/Evidence/Report human Review
- audit export, legal hold, 기관 보존정책
- 팀 Evidence reuse와 Living Report
- 변경 감지와 영향받는 Claim/Report 재검토
- 관리자 Console과 기관별 source policy
- 기관 결재·문서관리 adapter 후보

### 종료 기준

- cross-tenant 접근 성공 0건
- 기관 IdP·gateway·retention 실제 환경 검증
- Review와 audit가 기관 workflow에서 사용 가능
- backup/restore/export/delete/legal hold 충돌 규칙 확정
- 독립 Security/Privacy/Legal review 통과

## 11. 기능 단계 배치

| 기능 | Public Preview | Account Beta | Paid | Enterprise |
|---|---|---|---|---|
| Research Planner | Government v0 | 개인 선호 보조 | profile 고도화 | 기관 override |
| Parallel Research | bounded track | 저장 Run 재실행 | 장기·예약 | tenant fairness |
| Evidence Scoring | 설명형 최소 component | 저장 Evidence score | calibration | 기관 Review |
| Evidence Database | 결과 내 local 구조 | opt-in 저장 | 정식 Evidence Index | Organization DB |
| Dedup/Provenance | URL/hash/재인용 최소 | 저장 문서 version | revision chain | shared catalog |
| Knowledge Graph | 없음 | relation table 후보 | Project graph | 기관 graph |
| Follow-up Discovery | gap 제시 | 저장 후보 | bounded auto-run | 승인 workflow |
| Living Report | 없음 | History | 부분 재생성 | Review·impact |
| Diff Detection | 없음 | freshness check | structural diff | impact propagation |
| Project Memory | 없음 | 저장 조사 재사용 | 정식 기능 | 팀 memory |
| Research Profiles | Government v0 | Regulation 후보 | 다중 profile | 기관 profile |
| Exporter | Markdown/JSON | account export | bundle/HTML/CSV | signed package |

## 12. 주요 위험과 완화

| 위험 | 조기 신호 | 완화 | 차단 단계 |
|---|---|---|---|
| 익명 비용 남용 | token 변경·동시 Run 증가 | IP+HMAC+global quota, kill switch | R1 |
| SSRF와 parser 공격 | private redirect, oversized PDF | URL 재검증, sandbox·budget | R2 |
| 무보관 약속 위반 | log/tmp canary 발견 | allowlist telemetry, sweeper, release gate | R1~R4 |
| 조사결과가 쓸모없음 | 낮은 result retrieval/helpful | golden QA, profile·source 개선 | R2~R4 |
| 공식자료 확보 실패 | 기사 비중 증가 | gap 표시, source registry 개선 | R2 |
| 임시 결과 유실 | async result 조회 실패 | handle/TTL/fault test, 명확한 SLA | R3 |
| 계정 기능 조기 투자 | 저장 요청 부족 | R4 trigger 전 R5 시작 금지 | R4 |
| 영구저장 보안 결함 | cross-user reference 허용 | composite FK, RLS, export/delete test | R5 |
| OAuth JWKS DoS | unknown `kid` 반복 refresh | negative cache/cooldown | R5 |
| 범위 팽창 | UI·graph·billing 선행 | 단계별 Won't와 gate | 전체 |

## 13. 검증과 출시 증거

각 단계 release는 다음을 남긴다.

- 요구사항→구현→Validation ID traceability
- test 결과와 coverage
- 공개 Tool schema snapshot
- threat model 변경분
- fixture corpus manifest와 출처·license
- content canary scan 결과
- purge/fault/kill-switch rehearsal
- 지원 Host compatibility
- known limitations와 open risks
- 배포·rollback·disable 절차

## 14. 기술부채 정책

### 초기 허용

- 단일 region·단일 node 또는 sticky routing
- process-local worker pool
- encrypted tmpdir 기반 ephemeral storage
- rule-based Planner와 source tier
- provider 1종
- content-free aggregate metric

### 초기 금지

- 질문·원문·결과의 일반 log 또는 영구 DB 저장
- token digest만으로 IP quota를 대체
- URL redirect 후 정책 재검증 생략
- locator 없는 FACT
- 삭제 실패 content의 계속 제공
- 자동 opt-in 저장
- 가입을 Public Preview 사용조건으로 변경
- public mode에서 account/tenant repository 암묵 호출

## 15. 가장 먼저 구현할 작업

초기 public safety와 curated quick smoke는 완료됐다. 현재 가장 먼저 수행할 작업은 다음이다.

```text
CH-P1.9 Human Usefulness QA
+ curated 결과의 claim/citation/gap 과잉해석·누락 평가
+ 국가법령정보센터 source adapter 결정
+ citation-constrained Writer 필요성 판단
+ 선택형 live Search의 recall·비용·query retention 비교
```

그 결과가 유용하지만 시간이 길면 R3 async를 우선하고, evidence bundle이 빈약하면
citation-constrained Writer를 먼저 추가한다. 이후 trusted edge IP·비용 kill switch를 닫아
R4 제한 공개로 이동한다.

---

이 로드맵은 “기능을 많이 만든 뒤 사용자를 찾는 계획”이 아니다. **안전하게 공개하고, 유용성을 증명하고, 사용자가 저장을 원할 때만 계정과 영구저장을 추가하는 계획**이다.
