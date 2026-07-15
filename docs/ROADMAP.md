# Public Sector Research MCP — Roadmap

> 문서 상태: Proposed · 기준일: 2026-07-16 · 대상 기간: 설계 분리부터 v3까지

[VISION](./VISION.md) · [PRD](./PRD.md) · [ARCHITECTURE](./ARCHITECTURE.md) · [Repository README](../README.md)

## 1. 문서 목적

이 문서는 Public Sector Research MCP(이하 PSR MCP)를 별도 저장소의 설계안에서 실제 공공분야 Pilot 가능한 제품으로 만드는 구현 순서를 정의한다. 각 단계에서 다음을 명확히 한다.

- 어떤 사용자 위험과 기술 위험을 먼저 제거하는가
- 무엇을 만들고 무엇은 다음 단계로 미루는가
- 단계 종료를 어떤 증거로 판단하는가
- 기존 `adaptive-web-research`와 `crawlkit.py`를 언제, 어떤 기준으로 재사용하는가
- MCP protocol 변화와 제품 domain을 어떻게 분리하는가

일정은 승인된 팀 규모와 기관 보안심사 기간에 따라 달라질 수 있다. 아래 기간은 **제품 엔지니어 3~5명, Product/Research Lead 1명, Security/Legal/Accessibility reviewer의 부분 참여**를 가정한 상대 추정치다.

## 2. 구현 전략

### 2.1 Production-shaped vertical slice

첫 구현은 단일 사용자 CLI나 crawler demo가 아니다. 기능은 작게 만들되 다음 경로를 처음부터 관통한다.

```text
MCP Host
→ OAuth token 검증
→ Organization/Project authorization
→ versioned Tool schema
→ durable ResearchRun/Job
→ Worker의 허용된 공식 source 수집
→ immutable Snapshot/Passage
→ Evidence Review
→ Markdown/JSON Report
→ AuditEvent
```

초기 구현이 작은 이유는 source 수와 output 종류가 제한되기 때문이지, Tenant isolation이나 provenance를 생략하기 때문이 아니다.

### 2.2 Protocol shell, domain core

- MCP `2025-11-25`를 현재 운영 기준으로 사용한다.
- MCP Gateway는 application service의 얇은 adapter다.
- ResearchRun은 protocol session이나 experimental MCP Tasks가 아닌 application Job이다.
- `2026-07-28` 계열 protocol은 final, SDK, 목표 Host 지원을 확인한 후 transport adapter로 추가한다.
- protocol upgrade가 Evidence schema migration을 강제하지 않게 한다.

### 2.3 공식자료 우선의 구현 방식

공식자료 우선은 prompt 문구가 아니라 다음 네 요소로 구현한다.

1. 검토 가능한 `SourceRegistry`
2. Research Profile의 source tier·query·coverage rule
3. Planner의 evidence requirement와 stop condition
4. Report의 source coverage·gap·currentness 표시

### 2.4 사람 검토를 product flow로 구현

MVP부터 다음 action은 authenticated human Review를 요구한다.

- ResearchPlan 승인
- Evidence의 공식성·적용성 override
- Report publish
- source allow/deny policy 변경

Host가 보여주는 일반적인 Tool confirmation만으로 조직의 업무 승인을 대체하지 않는다.

### 2.5 Legacy는 characterization 후 추출

기존 저장소는 독립적으로 유지한다. `crawlkit.py` 전체를 복제하지 않는다.

1. 실제 input/output/failure를 fixture로 고정한다.
2. fetch, redirect, content detection, hash 중 재사용 가능한 동작을 식별한다.
3. credential redaction, SSRF 방어, 정책 검사, typed error가 없는 부분은 새 경계 뒤에서 보완한다.
4. 검토된 최소 구현만 `Collector`/`Parser` adapter로 추출한다.
5. legacy data는 import하며 원본 directory는 수정하지 않는다.

## 3. 단계 요약

| 단계 | 목표 | 핵심 사용자 | 예상 기간 | 출시 판단 |
|---|---|---|---:|---|
| Phase 0 | 저장소·제품 경계 확정 | 구현팀 | 완료 | 4종 문서와 별도 repo |
| Foundation | protocol·security 위험 spike | 구현팀/보안 | 2~3주 | vertical slice contract 승인 |
| MVP Internal Alpha | 한 조직의 공식자료 조사 end-to-end | 내부 담당자/Reviewer | 10~14주 | MVP Acceptance 통과 |
| v1.0 Public-Sector Pilot | 실제 기관 IdP·운영·감사 가능 | 2개 Pilot 조직 | 8~12주 | Pilot readiness review |
| v1.5 Living Evidence | 재사용·현행성·변경 영향 | 반복 사용자 | 8~12주 | Living Evidence test 통과 |
| v2 Ecosystem & Scale | client 확장·선택적 Tasks·graph | 여러 Host/운영팀 | 12~20주 | compatibility/scale gate |
| v3 Federation | 기관 간 통제된 지식 연계 | 다기관 운영자 | 별도 결정 | federation governance 승인 |

기간은 앞 단계의 완료 기준을 만족한 뒤 시작한다. 날짜를 맞추기 위해 security 또는 provenance gate를 생략하지 않는다.

## 4. Phase 0 — Repository Split and Product Definition

### 4.1 목표

범용 조사형 crawler Skill과 공공분야 다중 사용자 Research MCP의 제품·저장소·위험 모델을 분리한다.

### 4.2 산출물

- 별도 `public-sector-research-mcp` repository
- [VISION](./VISION.md)
- [PRD](./PRD.md)
- [ARCHITECTURE](./ARCHITECTURE.md)
- 본 [ROADMAP](./ROADMAP.md)
- legacy repository와 신규 repository의 책임 경계
- MCP current/RC protocol decision

### 4.3 완료 기준

- `DOC-001`: 네 문서의 제품명, 단계명, 핵심 entity, protocol 기준이 일치한다.
- `DOC-002`: 신규 저장소에 기존 crawler source code가 복제되지 않는다.
- `DOC-003`: 기존 저장소의 source code와 research data가 변경되지 않는다.
- `DOC-004`: MVP에 OAuth, Tenant isolation, audit, human Review가 명시된다.
- `DOC-005`: legacy 재사용은 characterization과 보안 검토 이후로 제한된다.

## 5. Foundation — Protocol and Tenant Vertical Slice

### 5.1 목표

전체 구현에 앞서 가장 비용이 큰 protocol, authorization, Tenant, async Job 결정을 실행 가능한 최소 경로로 검증한다.

### 5.2 작업 패키지

#### WP-F01 — ADR와 repository scaffold

- `pyproject.toml`, package/module 경계, lint/type/test policy
- 운영용 `psrctl` scaffold와 versioned exit/output contract
- ADR-001~ADR-011 초안 확정
- Python 버전과 공식 MCP SDK 호환성 matrix
- local development용 container composition
- migration framework와 test database

**난이도:** 중간  
**선행조건:** Architecture 승인  
**완료 증거:** 빈 service가 CI와 local compose에서 동일하게 기동

#### WP-F02 — MCP conformance spike

- Streamable HTTP endpoint
- initialize/capability negotiation
- `tools/list`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`
- input/output JSON Schema validation
- `structuredContent`와 text compatibility output
- protocol error와 Tool execution error 분리
- deterministic pagination fixture

**난이도:** 높음  
**선행조건:** MCP SDK ADR  
**완료 증거:** current stable `2025-11-25` protocol test와 최소 2개 목표 Host smoke

#### WP-F03 — Authorization/Tenant slice

- local dev issuer와 production OIDC interface
- OAuth resource metadata
- issuer, audience, expiry, scope validation
- `AuthContext` 생성
- Organization/User/Membership/Project schema
- application authorization와 PostgreSQL RLS
- cross-tenant negative test
- downstream token passthrough 차단

**난이도:** 매우 높음  
**선행조건:** Threat model workshop  
**완료 증거:** ID를 알고 있어도 다른 Organization의 Project를 Tool/Resource/SQL로 읽지 못함

#### WP-F04 — Durable Job slice

- `ResearchRun`과 `Job` schema
- PostgreSQL-backed claim/lease/retry
- idempotency key
- cooperative cancellation
- crash recovery
- explicit `run_id` Resource

**난이도:** 높음  
**선행조건:** DB/queue ADR  
**완료 증거:** Gateway restart와 worker crash 이후에도 Job이 중복 실행되지 않고 상태 복구

### 5.3 Foundation exit gate

다음 중 하나라도 실패하면 feature 확장을 시작하지 않는다.

- 목표 Host에서 Tool/Resource/Prompt contract가 불안정하다.
- token audience 또는 Project authorization을 우회할 수 있다.
- Job retry가 중복 Snapshot을 만든다.
- protocol session loss가 application Job loss로 이어진다.
- audit의 actor와 operation ID가 end-to-end로 연결되지 않는다.

## 6. MVP Internal Alpha

### 6.1 MVP 정의

한 Organization의 승인된 내부 사용자들이 Government Profile로 공공기관 AI 구매 원칙 같은 질문을 계획하고, 제한된 공식 source를 조사하고, 근거를 Review한 뒤 Markdown/JSON report를 생성할 수 있는 production-shaped alpha다.

MVP는 공개 서비스가 아니다. 다중 Tenant 구조는 구현하지만 초기 운영 대상은 통제된 내부 Organization 1개다.

### 6.2 MVP In Scope

| Capability | 범위 | 우선순위 |
|---|---|---|
| Remote MCP | stable `2025-11-25`, Streamable HTTP | Must |
| Identity/Tenant | OIDC interface, RBAC, Project restriction, RLS | Must |
| Review Console | Plan/Evidence/Report 승인 최소 UI | Must |
| Planner | decision question, subquestion, source track, budget, stop condition | Must |
| Profile | Government and Public Sector 1종 | Must |
| Source Registry | seed registry + tenant override + Review status | Must |
| Collector | policy-aware HTML/PDF/JSON/text, allow/deny, timeout/retry | Must |
| Evidence store | PostgreSQL metadata + S3-compatible immutable object | Must |
| Evidence model | Snapshot, Passage, Claim, EvidenceLink, 8차원 Score | Must |
| Dedup | canonical URL, raw/normalized SHA-256 | Must |
| Report | Markdown/JSON, citation, gaps, conflicts, failures | Must |
| Audit/Observability | append-only AuditEvent, metrics, trace correlation | Must |
| Export | metadata/report package; raw 원문은 별도 정책 | Should |
| Legacy import | selected `probe.json` fixture import | Should |

### 6.3 MVP 제외

- 범용 web search engine 자체 개발
- 모든 웹사이트의 browser automation 또는 우회 수집
- 의미 기반 Diff와 ChangeEvent impact propagation
- Project Memory semantic search
- graph DB
- MCP Tasks 의존
- cross-Organization Evidence 공유
- 기관 결재시스템 연동
- 대규모 분산 worker autoscaling
- PDF 최종 보고서 export

### 6.4 MVP 작업 패키지

#### WP-M01 — Domain and storage core

- Organization, Project, Plan, Run, Source, Document, Snapshot, Passage
- Claim, EvidenceLink, Review, Report, AuditEvent
- repository interface와 transaction boundary
- PostgreSQL migration, object key convention, checksum verification
- immutable/append-only rule test

**난이도:** 높음  
**검증:** repository contract test, migration forward/backward test, object integrity test

#### WP-M02 — Government Research Profile

- 법령, 정부정책, 개인정보, 조달, 감사·평가, 공식사례 source track
- source tier와 evidence requirement
- 관할, 기준일, 시행일, 적용대상 field
- profile YAML/JSON Schema와 loader
- 기관별 override가 base profile을 파괴하지 않는 merge rule

**난이도:** 중간  
**검증:** AI 구매 원칙 fixture에서 필수 5개 쟁점이 생성되고 source coverage가 계산됨

#### WP-M03 — Research Planner v1

- 입력 모호성 검사와 `NEEDS_INPUT`
- decision question/research question 분해
- query·source track·budget·stop condition 생성
- Plan version과 approval state
- deterministic plan schema와 fixture-based LLM evaluation

**난이도:** 높음  
**검증:** golden scenario의 필수 질문 recall, budget/stop condition completeness, 사람 수정 이력 보존

#### WP-M04 — Source Registry and policy engine

- official/curated/observed/unverified state
- domain과 기관 관계
- jurisdiction/source type/review owner
- allow, deny, rate, maximum bytes, redirect policy
- private/link-local/metadata endpoint SSRF 차단

**난이도:** 높음  
**검증:** malicious URL corpus, redirect escape, DNS rebinding 방어 test

#### WP-M05 — Collector/Parser v1

- HTTP client adapter와 `CollectionAttempt`
- content magic/MIME 판별
- HTML main content·heading path
- PDF text·page locator; scanned PDF는 `OCR_REQUIRED`
- JSON original·JSON Pointer
- typed failure, partial success, retryability
- credential/log redaction

**난이도:** 매우 높음  
**검증:** official-source fixture corpus, login/error/empty page rejection, PDF page locator accuracy

#### WP-M06 — Evidence pipeline v1

- passage segmentation과 stable locator
- Claim type과 EvidenceLink relation
- 8차원 score 및 rationale
- 공식 원문 미확보·상충·단일 source·stale gap
- Reviewer override와 supersession

**난이도:** 높음  
**검증:** 같은 fixture에 score component가 재현되고 total-only record가 거부됨

#### WP-M07 — MCP application catalog

- PRD의 `psr.project.*`, `psr.research.*`, `psr.evidence.*`, `psr.report.*`
- versioned input/output schemas
- Tool authorization matrix
- `psr://` Resource resolver
- public-policy/review Prompt templates
- list pagination과 bounded Resource content

**난이도:** 높음  
**검증:** schema snapshots, negative authorization, 2개 Host end-to-end

#### WP-M08 — Review Console minimum

- OIDC login
- pending Plan/Evidence/Report queue
- original Passage와 metadata 확인
- approve/reject/request-changes
- subject/version-bound approval nonce
- audit view

**난이도:** 높음  
**검증:** stale nonce, 다른 user, 다른 version, replay가 모두 거부됨

#### WP-M09 — Report and export v1

- Markdown/JSON renderer
- Claim→Passage citation
- scope, 기준일, source coverage, conflict, gap, failure
- unlinked FACT publish lint
- dependency manifest
- raw 원문 제외가 기본인 export

**난이도:** 중간  
**검증:** report Claim 전부가 evidence 또는 명시적 `UNVERIFIED` 상태를 가짐

#### WP-M10 — Operations and quality

- structured log, metric, trace, operation ID
- queue depth, partial failure, source health dashboard
- backup/restore drill
- dependency/SBOM/secret scan
- Korean quality and citation QA
- operator runbook

**난이도:** 높음  
**검증:** 장애·복구 game day와 MVP Acceptance suite

### 6.5 MVP milestone

| Milestone | 결과 | Exit criteria |
|---|---|---|
| M0 | Foundation approved | F01~F04 gate 통과 |
| M1 | Authenticated empty MCP | 사용자별 Tool/Resource 목록과 audit |
| M2 | Plan approval slice | Plan 생성·Console 승인·Run start |
| M3 | One-source evidence slice | 공식 HTML 또는 PDF → Passage → Review |
| M4 | Multi-track partial run | source별 성공/실패와 failed-only retry |
| M5 | Evidence report | Markdown/JSON, citation, gap, publish gate |
| M6 | Internal Alpha | PRD 시나리오 A~E와 운영 검토 통과 |

### 6.6 MVP 완료 기준

- PRD `AC-001` 계열 Tenant test와 시나리오 A~E가 통과한다.
- Cross-tenant 접근 성공 0건, seeded secret leakage 0건이다.
- EvidenceLink의 Passage locator completeness가 100%다.
- 공식 원문 미확보·부분실패·추론을 report가 숨기지 않는다.
- Plan과 Report publish에 authenticated human Review가 있다.
- worker crash와 duplicate start에서 성공 Snapshot이 손실·중복되지 않는다.
- 지원 Host 2종에서 같은 Project를 조회하고 core flow를 완료한다.
- restore drill로 DB와 object manifest consistency를 복구한다.
- 코드, 운영문서, threat model, data dictionary가 함께 release tag에 포함된다.

## 7. v1.0 — Public-Sector Pilot

### 7.1 목표

2개 Pilot Organization이 실제 기관 정책과 IdP 아래에서 제한된 업무에 반복 사용하도록 운영 준비도를 높인다.

### 7.2 기능·운영 범위

- 실제 OIDC provider 2종 연동과 account lifecycle
- Organization Admin Console과 Project/Membership 관리
- quota, retention, legal hold, export/delete workflow
- source registry owner workflow와 institution override
- shared seed registry의 signed release
- HTML/PDF parser coverage 확대와 OCR adapter
- Markdown, JSON, JSONL, HTML, CSV, citation bundle
- raw Snapshot expiring access handle와 별도 scope
- 접근성 WCAG 목표와 한국어 UI QA
- SLO, alert, incident response, backup/restore, disaster recovery
- vulnerability management, penetration test, dependency policy
- 기관별 배포와 managed deployment의 동일 artifact 검증
- 지원 Host compatibility matrix와 troubleshooting guide

### 7.3 Pilot entry criteria

- MVP release가 4주 이상 내부 운영되고 P0/P1 open defect가 없다.
- 기관별 data classification, retention, permitted source가 합의됐다.
- IdP, security, privacy, copyright, records-management reviewer가 지정됐다.
- production credential과 source credential의 owner/rotation policy가 있다.
- Pilot 업무는 법률판단 자동화가 아닌 조사 보조로 정의됐다.

### 7.4 Pilot exit criteria

- 두 Organization에서 30일간 cross-tenant incident 0건이다.
- 핵심 조사 20건 이상 중 citation locator 정합성 98% 이상이다.
- Reviewer가 공식 source status를 확인할 수 있고 override가 audit된다.
- partial run과 stale evidence가 완전 결과로 publish되지 않는다.
- backup/restore와 tenant export/delete rehearsal이 통과한다.
- 담당자 재사용률과 조사 리드타임이 baseline보다 개선된다.
- Pilot 종료 후 go/conditional-go/stop 의사결정 기록이 남는다.

## 8. v1.5 — Living Evidence

### 8.1 목표

일회성 보고서 생성에서 벗어나 Project Evidence를 반복 재사용하고 변경 영향을 관리한다.

### 8.2 기능

- Project Memory: 질문, 검색어, 검토 source, 제외 사유, 확정 판단, 미해결 쟁점
- exact/filter search 우선의 Evidence reuse
- source freshness schedule과 conditional request
- 새 Snapshot의 raw/normalized/structural diff
- layout-only/content/metadata change 분류
- ChangeEvent와 Claim/Report dependency impact
- Review queue와 `STALE_REVIEW_REQUIRED`
- supported client의 Resource subscription/update notification
- Report section 부분 재생성·before/after manifest
- regulation/compliance와 procurement Profile 추가
- 검증된 공개 source metadata의 shared catalog projection
- Follow-up Discovery 후보와 비용·위험·승인 policy

### 8.3 제외 또는 제한

- semantic diff는 deterministic structural diff의 보조 signal로만 사용한다.
- 자동 change classification이 사람 Review 없이 보고서를 publish하지 않는다.
- Project Memory의 사용자 선호가 기관 policy를 override하지 않는다.
- cross-Organization raw Evidence는 공유하지 않는다.

### 8.4 완료 기준

- PRD 시나리오 F가 end-to-end로 통과한다.
- 변경된 Passage에서 영향 Claim·Report까지 provenance 경로가 존재한다.
- layout-only fixture의 false positive와 content-change false negative 목표가 정의·측정된다.
- 재사용 가능/현행성 확인 필요/재수집 필요를 구분한다.
- 동일 질문 재실행에서 불필요한 full fetch가 측정 가능하게 감소한다.
- 부분 재생성 전후 Claim/Evidence dependency diff가 저장된다.

## 9. v2 — Ecosystem, Graph and Scale

### 9.1 목표

다양한 MCP Host, 증가한 조사량, 복잡한 관계 탐색을 지원하되 core provenance와 권한 모델을 유지한다.

### 9.2 Protocol evolution

- `2026-07-28` 계열이 final이 된 시점의 사양·SDK·Host matrix 재검토
- stateless transport adapter와 backward compatibility test
- MCP Tasks가 stable이고 목표 Host가 지원하면 optional `TaskAdapter`
- core Tool은 Tasks 없이도 계속 작동
- resource link/handle의 수명과 authorization 재검증
- protocol version별 conformance suite와 deprecation policy

### 9.3 기능

- 최소 Knowledge Graph의 relation query와 graph projection
- 필요성이 입증될 때에만 graph DB read model 검토
- Technology/Open Source, Strategy/Benchmarking Profile
- 정책상 허용된 search provider connector
- organization source catalog package와 검증된 update channel
- queue backend adapter와 workload class
- worker autoscaling, per-tenant fairness, backpressure
- encrypted tenant export/import package
- 기관 결재·문서관리 시스템 adapter
- evaluation harness와 Profile별 benchmark corpus
- report template/version registry

### 9.4 Scale trigger

다음 중 하나가 4주 연속 발생할 때 PostgreSQL queue 또는 relational graph projection의 분리를 검토한다.

- queue claim/maintenance가 database CPU 또는 lock wait의 주요 원인
- P95 queue wait가 SLO를 초과
- worker가 50개 이상이거나 장시간 Job 유형이 다양해짐
- graph traversal이 핵심 query latency를 지배
- backup/restore window가 허용 범위를 초과

### 9.5 완료 기준

- current와 previous supported protocol adapter가 동일 application contract suite를 통과한다.
- optional Tasks 미지원 Host에서도 core flow가 유지된다.
- noisy tenant workload가 다른 tenant SLO를 깨지 않는다.
- graph 결과가 원 Snapshot/Passage로 역추적된다.
- connector는 source policy, credential isolation, audit를 우회하지 않는다.

## 10. v3 — Controlled Federation

### 10.1 목표

단일 서비스의 단순 확장이 아니라, 기관이 소유권과 공개범위를 통제하면서 검증된 공공 Evidence metadata를 연계하는 모델을 검증한다.

### 10.2 후보 기능

- 기관별 배포 간 signed source catalog federation
- 공개 가능한 Document/Snapshot hash·metadata 교환
- policy-aware federated search
- 기관 내부 Claim과 public Claim의 명시적 경계
- provenance signature와 package verification
- 폐쇄망/간헐 연결 환경을 위한 offline sync package
- records schedule와 legal hold의 기관별 enforcement
- 고가용성 multi-region deployment option
- 승인된 통계만 제공하는 cross-institution analytics

### 10.3 시작 조건

- v2까지 single-tenant boundary와 audit model이 검증됐다.
- 참여기관 간 data classification·ownership·withdrawal agreement가 있다.
- 어떤 metadata가 공개 가능하고 어떤 raw object가 금지되는지 합의됐다.
- federation이 실제 반복 문제를 해결한다는 evidence가 있다.

### 10.4 완료 기준

- 참여기관이 공개 범위를 독립적으로 승인·철회할 수 있다.
- federated result에도 origin, snapshot time, signature, review status가 보존된다.
- 기관 내부 object·Claim·user activity가 다른 기관에 노출되지 않는다.
- 철회·정정·key rotation·compromise recovery rehearsal이 통과한다.

## 11. 기능 후보의 단계 배치

| 기능 | MVP | v1.0 | v1.5 | v2 | v3 |
|---|---|---|---|---|---|
| Research Planner | v1 기본 | 품질 개선 | memory-aware | profile별 고도화 | federated scope |
| Parallel Research | bounded source tracks | worker 운영화 | scheduled refresh | scale/fairness | federated |
| Evidence Scoring | 8차원 v1 | calibration | freshness/impact | profile별 model | 기관 간 호환 검토 |
| Evidence Database | 핵심 entity | retention/admin | ChangeEvent/Memory | projection 확장 | federated metadata |
| Dedup/Provenance | URL/hash/version | mirror/source chain 개선 | revision graph | shared catalog | cross-instance hash |
| Knowledge Graph | relation table 최소 | query 없음 | impact relation | graph query/read model | federation |
| Follow-up Discovery | gap만 표시 | 수동 후보 | 비용·위험·승인 후보 | bounded auto-run | policy federation |
| Living Report | dependency manifest | publish workflow | diff/부분 재생성 | templates | cross-institution package |
| Diff Detection | hash/freshness | schedule 준비 | structural/semantic assist | scale | federated change |
| Project Memory | audit/history 기초 | 검색 개선 | 정식 기능 | semantic retrieval 검토 | 기관 정책별 sync |
| Research Profiles | Government 1종 | 기관 override | Regulation/Procurement | Technology/Strategy | shared profile catalog |
| Exporter | Markdown/JSON | HTML/CSV/JSONL/bundle | diff package | signed package | offline federation |
| MCP Server | primary interface | Pilot 운영 | subscriptions | next protocol/Tasks optional | federation gateway |

## 12. 선행조건과 외부 의존성

| 영역 | 선행조건/의존성 | 대응 |
|---|---|---|
| MCP SDK | current protocol과 Python 지원 | 첫 spike에서 pinning·compatibility test |
| Identity | Pilot IdP의 OIDC metadata와 claim | `IdentityProvider` adapter, local dev issuer 분리 |
| Database | PostgreSQL 16+ 운영환경 검토 | version ADR와 managed/self-hosted matrix |
| Object store | S3-compatible versioning/encryption | MinIO dev, Pilot provider 검증 |
| Parsing | PDF/HTML parser license·품질 | fixture corpus와 dependency review |
| Search | provider 약관과 API 권한 | MVP는 curated source/direct collection 중심 |
| Source Registry | 공공 source owner와 분류기준 | Product/Research governance workshop |
| Security | threat model, pentest, incident owner | Foundation부터 reviewer 참여 |
| Records | 보존·삭제·legal hold 정책 | Pilot 전 기관별 policy 결정 |
| Accessibility | 대상 기준과 test method | Console 개발 전 design acceptance |

## 13. 주요 위험과 완화

| 위험 | 가능성/영향 | 조기 신호 | 완화 | Owner |
|---|---|---|---|---|
| 공식 source도 개정·오류가 있음 | 중/높음 | 서로 다른 시행일·버전 | currentness, contradiction, human Review | Research Lead |
| Tenant data leakage | 낮음/치명적 | authorization negative test 실패 | RLS, app guard, namespace, pentest | Security Lead |
| MCP protocol/SDK 변화 | 높음/중간 | RC와 SDK 불일치 | adapter, conformance matrix, current baseline | Architect |
| crawler가 prompt injection을 운반 | 중/높음 | 원문 지시가 tool flow 변경 | content/instruction boundary, eval fixture | AI Safety Owner |
| SSRF/credential leakage | 중/치명적 | private IP redirect·secret log | policy engine, egress, redaction, scan | Security Lead |
| PDF locator 부정확 | 높음/높음 | page mismatch | parser corpus, source bytes 보존, Review | Evidence Lead |
| Source Registry 유지비 | 높음/중간 | stale owner review | seed release, institution override, freshness | Product Ops |
| 지나친 자동승인 | 중/높음 | AI identity approval | human subject, nonce, immutable Review | Product/Security |
| MVP 범위 팽창 | 높음/높음 | source/profile/export 추가 | scenario A 중심, Won't list, change control | Product Lead |
| PostgreSQL queue 병목 | 낮음/중간 | lock/queue wait 증가 | metrics, scale trigger, queue adapter | Platform Lead |
| 저작권/약관 오판 | 중/높음 | raw export 요청·restricted source | policy, metadata-only mode, legal review | Governance Owner |
| 사용자 신뢰 부족 | 중/높음 | evidence 확인 없이 report 사용 | visible citation/gap/review UX | Product Lead |

## 14. 검증 전략

### 14.1 Test pyramid

1. pure domain unit test: score, state, policy, identifier
2. repository/adapter contract test
3. protocol schema/conformance test
4. parser/collector fixture test
5. security negative test
6. end-to-end golden research scenario
7. target Host smoke
8. operator game day와 Pilot user acceptance

### 14.2 Golden scenarios

- 공공기관 AI 구매 원칙
- 법령·시행령·가이드의 현행성 구분
- 동일 보도자료 재인용 기사와 원 source 구분
- 개정 전후 정부 PDF
- official original 미확보
- 일부 source timeout과 failed-only retry
- malicious HTML prompt injection
- 다른 Organization ID를 사용한 Tool/Resource 접근

### 14.3 Release evidence

각 milestone은 다음 artifact를 release package에 남긴다.

- requirement/Acceptance test traceability matrix
- protocol/Host compatibility result
- migration version과 data dictionary
- threat model 변경분과 security test result
- fixture corpus manifest와 license/provenance
- performance/queue/source health baseline
- known limitation과 unresolved risk
- operator/user/reviewer guide

## 15. Definition of Done

작업 패키지는 code merge만으로 완료되지 않는다. 다음이 모두 필요하다.

- PRD requirement와 Acceptance ID가 연결됨
- unit/contract/integration/security test가 있음
- Tenant/authorization path가 검토됨
- structured log와 metric이 정의됨
- error/partial failure/retry가 문서화됨
- schema와 migration 또는 호환성 근거가 있음
- 한국어 사용자 문구와 영문 원문 표기가 검토됨
- API/MCP schema와 example이 갱신됨
- runbook과 known limitation이 갱신됨
- Product, Architecture, Security 중 필요한 owner가 승인함

## 16. 기술부채 관리

### 16.1 허용 가능한 초기 선택

- PostgreSQL-backed queue
- 단일 또는 sticky MCP Gateway instance
- rule-based source tier와 score weight
- relation table 기반 최소 graph
- Government Profile 1종
- manual source owner review

### 16.2 허용하지 않는 부채

- `organization_id` 없는 domain row
- raw SQL에서 임의로 빠질 수 있는 Tenant filter
- mutable Snapshot
- locator 없는 Evidence
- total-only Evidence Score
- bearer token passthrough
- AI-only approval
- source content와 system instruction의 혼합
- success와 partial failure를 구분하지 않는 status

### 16.3 관리 방식

- ADR에 선택 이유, trigger, reversal cost를 기록한다.
- `debt` item은 owner, 기한 대신 **해소 trigger**, 위험을 가진다.
- milestone마다 schema/protocol/collector dependency debt를 검토한다.
- feature throughput 외에 stale dependency, migration lag, flaky fixture를 metric으로 본다.

## 17. 기존 코드와 데이터 마이그레이션

### 17.1 원칙

- legacy repository의 성능 지향 crawler는 계속 독립한다.
- 신규 제품은 법적·보안·공공업무 정책을 명시적으로 적용한다.
- 동일 기능처럼 보여도 trust boundary가 다르면 그대로 재사용하지 않는다.
- 기존 code history를 신규 repository에 합치지 않는다.
- code/data license와 ownership을 검토한다.

### 17.2 실행 순서

| 단계 | 작업 | 산출물 | Go 조건 |
|---|---|---|---|
| L1 | `crawlkit.py` characterization | command/input/output/failure fixtures | 동작 재현 가능 |
| L2 | 재사용 후보 분류 | reuse/refactor/replace matrix | 보안 gap 명시 |
| L3 | interface 추출 | Collector/Parser protocol | legacy import 없이 test 통과 |
| L4 | 보안 hardening | policy/redaction/validation/retry | security corpus 통과 |
| L5 | selected behavior 이식 | reviewed commits | attribution/license 확인 |
| L6 | legacy data importer | dry-run manifest | 원본 불변·error report |
| L7 | sample migration | verification report | object/hash/metadata 정합 |

### 17.3 폐기 후보

다음은 characterization 후에도 신규 제품에서 폐기하거나 격리할 가능성이 높다.

- 무제한 임의 URL 접근
- credential/cookie가 artifact에 남는 경로
- HTML/PDF 성공 여부를 status code만으로 판단하는 로직
- multi-tenant context가 없는 global cache
- 절대경로를 영구 식별자로 사용하는 metadata
- typed failure와 retryability가 없는 exception flow

## 18. 테스트·문서화 계획

| 시점 | 테스트 | 문서 |
|---|---|---|
| Foundation | protocol/auth/tenant/job spike | ADR, threat model, contributor setup |
| MVP M2 | Plan/approval/schema | Tool/Resource/Prompt reference |
| MVP M4 | collector/parser/partial retry | source policy, fixture guide |
| MVP M5 | evidence/report | reviewer guide, data dictionary |
| MVP M6 | end-to-end/security/recovery | operator runbook, limitations |
| v1.0 | IdP/pentest/accessibility/Pilot UAT | admin, incident, retention guide |
| v1.5 | diff/impact/reuse evaluation | Living Evidence operations |
| v2 | protocol matrix/load/scale | compatibility/deprecation policy |

문서는 code와 같은 pull request에서 갱신한다. 사용자에게 노출되는 MCP schema는 generated reference와 hand-written rationale를 함께 둔다.

## 19. MCP 전환 시점

이 프로젝트는 처음부터 MCP가 primary interface이므로 “나중에 crawler를 MCP로 감싸는 전환”을 하지 않는다. 다만 capability는 단계적으로 연다.

1. **Foundation:** protocol contract와 tenant-aware Resource 1개
2. **MVP:** core Tools/Resources/Prompts와 explicit Job
3. **v1.0:** remote operation, IdP, admin/review flow
4. **v1.5:** Resource subscriptions와 change notification
5. **v2:** next final protocol adapter와 optional MCP Tasks

MCP Tasks 채택 조건은 모두 충족해야 한다.

- 해당 기능이 stable specification이다.
- Python SDK와 목표 Host가 interoperable하게 지원한다.
- authorization과 task result lifetime이 명확하다.
- explicit `ResearchRun` contract의 backward compatibility가 유지된다.
- adoption이 실제 user/operations 문제를 줄인다.

## 20. 향후 선택 가능한 확장

다음은 core roadmap을 통과한 뒤 사용자 evidence가 있을 때 선택한다.

- 폐쇄망용 local MCP gateway와 offline Evidence package
- 기관별 전용 search connector
- OCR·표·도식 extraction 고도화
- 번역 alignment와 bilingual Passage
- citation format adapter와 기관 문서 template
- 법령 조문·시행일 specialized parser
- public source registry community contribution workflow
- formal records-management connector
- signed report/evidence package
- benchmark/evaluation 공개 세트
- privacy-preserving usage analytics

## 21. 가장 먼저 수행할 구현 작업

설계 승인 후 첫 작업은 `crawlkit.py` 리팩터링이 아니라 **MCP·Tenant vertical slice**다.

### Sprint 0 권장 순서

1. ADR-003(MCP SDK), ADR-009(Job queue), ADR-010(ID)을 spike로 확정한다.
2. Python package와 CI를 scaffold한다.
3. local OIDC issuer, PostgreSQL, object store가 있는 development environment를 만든다.
4. `psr.project.list` Tool과 `psr://projects/{project_id}` Resource를 구현한다.
5. OAuth audience/scope, Membership, RLS를 연결한다.
6. 두 Organization의 positive/negative access test를 만든다.
7. empty durable Job을 시작·조회·취소하고 Gateway restart test를 수행한다.
8. 목표 MCP Host 2종의 compatibility result를 ADR에 기록한다.

이 vertical slice가 통과한 다음에만 Planner와 Collector를 붙인다. 그래야 이후 모든 기능이 동일한 identity, Tenant, Job, audit 계약 위에서 성장한다.

## 22. Roadmap 의사결정 규칙

- **Must:** 단계 목표를 검증하는 데 필수이며 제거 시 release를 중단한다.
- **Should:** Pilot 가치나 운영성을 크게 높이지만 명시적 waiver로 이월할 수 있다.
- **Could:** evidence와 capacity가 있을 때 수행한다.
- **Won't now:** 현재 단계에서는 하지 않으며 다음 단계의 entry review에서 재평가한다.
- scope 변경은 PRD, Architecture, threat model, milestone에 미치는 영향을 함께 기록한다.
- 새 crawler capability보다 공식 source coverage, citation integrity, Review turnaround, Tenant safety를 우선한다.

---

이 Roadmap의 핵심은 기능 수를 빠르게 늘리는 것이 아니라, **공공업무 담당자가 근거를 믿고 사람이 책임 있게 검토할 수 있는 최소 경로를 먼저 완성한 뒤 재사용·변경감지·다기관 확장으로 나아가는 것**이다.
