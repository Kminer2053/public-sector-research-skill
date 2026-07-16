# Public Sector Research MCP — Implementation Plan

> 문서 상태: In Implementation · 기준일: 2026-07-16 · 현재:
> **PG1 로컬 수직 슬라이스·고정 URL Evidence·no-key curated smoke 완료,
> 사람 유용성 QA 대기**

[DETAILED DESIGN](./DETAILED_DESIGN.md) · [PRD](./PRD.md) · [ARCHITECTURE](./ARCHITECTURE.md) · [ROADMAP](./ROADMAP.md) · [VALIDATION CRITERIA](./VALIDATION_CRITERIA.md)

## 1. 목적

이 문서는 현재 Foundation codebase를 가입 없는 무보관 Public Preview로 전환하는 구현 순서를 정의한다. 각 change set은 다음을 포함해야 한다.

- 연결된 `FR-PUB`, `NFR-PUB`, `AC-PUB`, `VAL-PUB` ID
- 수정·생성할 package와 interface
- 선행조건과 명시적 비범위
- failure, retry, purge 동작
- 자동 검증과 수동 검토 증거
- rollback 또는 kill switch

현재 Foundation `F0~F4/G0~G5`는 완료된 과거 increment다. 다음 작업은 `G6` 기관 배포 승인이 아니라 Public Preview 경로 구현이다.

### 2026-07-16 구현 상태

- 완료: `ServiceMode.PUBLIC_EPHEMERAL`, public composition root, 익명 `service.policy`
- 완료: HMAC IP-first limiter와 invalid bearer rotation 우회 방지
- 완료: trusted proxy CIDR에서 온 단일 `X-PSR-Client-IP`만 정규화하고 위조 header 제거
- 완료: direct NGINX TLS·canonical Host·TCP peer IP overwrite·edge quota 기준과 정적검증
- 완료: filesystem ephemeral workspace, access block, TTL purge sweeper
- 완료: fixture quick lifecycle, content canary, immediate purge, quick kill switch
- 완료: deterministic Government Planner v0와 bounded stop condition
- 완료: legacy crawlkit characterization과 reuse/refactor/replace 판단
- 완료: HTTPS-only URL policy, redirect 재검증, 검증 IP 고정 transport, bounded SafeCollector
- 완료: official-first query builder, official domain registry, 선택형 Brave Search adapter
- 완료: 한국 공공부문 AI 조달 범위의 no-key curated source provider
- 완료: robots 선검사와 source access typed policy
- 완료: HTML·JSON·text parser와 subprocess-isolated PDF parser
- 완료: document quality, URL/hash dedup, component Evidence Score와 citation composer
- 완료: anchor가 모두 확인된 경우에만 조달 원칙 후보를 만드는 citation-constrained Writer
- 완료: 요약·조달 원칙 검토안·사실·근거·확인 필요사항을 분리한 한국어 Markdown
- 완료: track별 한·영 passage 선택어, 관련구간 excerpt, cross-track provenance 보존
- 완료: 동적 법령 shell 제외와 NIST 호스팅/저자 경계의 보수적 source 판정
- 완료: Search→Collect→Parse→Evidence→Markdown/JSON quick backend
- 완료: 같은 URL의 cross-track provenance를 유지하면서 network fetch 1회로 통합
- 검증: PostgreSQL 17·OAuth·TCP/TLS·gateway TLS spoof 포함 501 tests
- coverage gate: raw 95.13%, normalized statement 96.24%, branch 90.75%,
  critical module 95% 이상
- supply chain: project 53 package와 OCI build tool 6 package 알려진 취약점 0,
  `pypdf 6.14.2` BSD-3-Clause manifest 반영
- 검증: 고정 공식 URL 5종으로 7개 track citation과 실제 PDF page/HTML locator 확인
- 검증: curated 실제 quick에서 7개 track·12 citation·failure 0·purge 완료
- 남음: 공공업무 담당자 QA, 법령 source adapter, Writer 표현·적용범위 QA, 선택형 live Search
  비교검증, NGINX OCI·staging edge rehearsal, async flow

[Public S0 검증 보고서](./validation/2026-07-16-public-s0.md)를 따른다.
[PG1 로컬 수직 슬라이스 보고서](./validation/2026-07-16-pg1-useful-research.md)는
구현 증적과 실웹 검증 대기를 분리한다.

Legacy 수집기 분석과 이식 판단은
[Legacy crawlkit characterization](./analysis/legacy-crawlkit-characterization.md)에 고정했다.

## 2. 현재 기준선

### 2.1 구현 완료

아래 수치는 Public Preview 착수 전 Foundation 기준선이며 현재 전체 회귀 수치는 1장의
2026-07-16 구현 상태를 따른다.

- Python 3.12, `src` layout, strict lint/type/test
- MCP Streamable HTTP server와 5개 Foundation Tool
- Project/ResearchRun application service
- PostgreSQL repository, migration, RLS, durable Job
- OAuth/OIDC token verifier와 Membership
- request size, timeout, process-local rate limit
- official SDK, Inspector, Codex Tool conformance
- 185 tests, statement 95.02%, branch 87.10%, critical module 95% 이상

### 2.2 아직 없음

- 실제 공식 인터넷 source를 사용하는 golden scenario 승인
- 인용 구간에서 업무용 정책 문장을 만드는 Evidence-grounded Writer
- 의미 기반 conflict 탐지와 법령 현행성 판정
- start/status/result/cancel public async flow
- content-free feedback와 product metric
- trusted edge client IP normalization과 multi-replica quota

### 2.3 확인된 보강 항목

| ID | 항목 | 영향 | 처리 단계 |
|---|---|---|---|
| FIX-001 | rate key가 token digest+IP라 invalid bearer 회전으로 별도 bucket 생성 가능 | 공개 endpoint 비용 우회 | S0 완료 |
| FIX-002 | `research_runs.initiated_by`가 global user FK | Account/Enterprise cross-tenant integrity | A0 Must |
| FIX-003 | unknown JWT `kid`마다 JWKS 강제 refresh | Account endpoint DoS | A0 Must |
| FIX-004 | `psrctl doctor`가 구현된 public pipeline을 미구현으로 표시 | 운영자 혼동 | P1 완료 |

## 3. 구현 원칙

1. Public mode는 기존 OAuth/Tenant flow의 “인증 생략 옵션”이 아니라 별도 composition root다.
2. 실제 web content를 받기 전에 quota, tmp permission, TTL, purge, telemetry 금지 규칙을 먼저 구현한다.
3. Public content는 PostgreSQL Foundation schema에 저장하지 않는다.
4. operational metadata model에는 User Content field를 정의하지 않는다.
5. 모든 outbound network는 `SearchProvider` 또는 `Collector` port 뒤에 둔다.
6. Planner v0와 Evidence lint는 LLM 없이 deterministic하게 검증 가능해야 한다.
7. legacy `crawlkit.py`는 characterization fixture 전 복사하지 않는다.
8. partial success는 정상 상태이며 성공한 근거와 실패를 함께 반환한다.
9. 공개 기능은 disable 가능해야 하고 purge 경로는 disable되면 안 된다.
10. Account/Paid 기능은 Public Preview product trigger 전 구현하지 않는다.

## 4. 목표 package 구조

기존 package를 유지하면서 다음 모듈을 추가한다.

```text
src/psr_mcp/
├─ public/
│  ├─ context.py
│  ├─ service.py
│  ├─ pipeline.py
│  ├─ development_fixture.py
│  └─ schemas.py
├─ planner/
│  ├─ models.py
│  ├─ government.py
│  └─ service.py
├─ search/
│  ├─ ports.py
│  ├─ models.py
│  ├─ government.py
│  ├─ registry.py
│  ├─ static.py
│  └─ brave.py
├─ collectors/
│  ├─ models.py
│  ├─ url_policy.py
│  ├─ safe.py
│  ├─ httpcore_transport.py
│  └─ access_policy.py
├─ parsers/
│  ├─ html.py
│  ├─ pdf.py
│  ├─ pdf_core.py
│  ├─ json_document.py
│  ├─ text.py
│  ├─ sniff.py
│  └─ dispatch.py
├─ parser_workers/
│  └─ pdf.py
├─ evidence/
│  ├─ models.py
│  ├─ quality.py
│  └─ composer.py
├─ ephemeral/
│  ├─ ports.py
│  ├─ filesystem.py
│  ├─ metadata.py
│  └─ sweeper.py
├─ abuse/
│  ├─ ports.py
│  └─ limiter.py
└─ feedback/
   ├─ models.py
   └─ sink.py
```

`domain/`, `application/`, `auth/`, `storage/postgres/`는 후속 account/enterprise mode를 위해 유지한다.

## 5. Increment 순서

| Increment | 목표 | 예상 change 수 | 종료 Gate |
|---|---|---:|---|
| S0 | Public mode·quota·ephemeral purge | 4~6 | PG0 Public Boundary |
| P1 | Planner·SafeCollector·quick result | 6~9 | PG1 Useful Research |
| P2 | Ephemeral async run | 4~6 | PG2 Zero Retention |
| P3 | 공개 배포·관찰·feedback | 3~5 | PG3 Public Preview |
| A0 | 선택 가입 기반 보강 | product trigger 이후 | AG0 Account Trust |

## 6. S0 — Public Safety Core

### CH-S0.1 ServiceMode와 설정

**요구사항:** `FR-PUB-001~004`, `NFR-PUB-009`

**수정**

- `src/psr_mcp/config.py`
- `src/psr_mcp/bootstrap.py`
- `src/psr_mcp/cli/main.py`
- `tests/unit/test_config.py`
- `tests/unit/test_cli.py`

**추가**

- `ServiceMode`: `FOUNDATION`, `PUBLIC_EPHEMERAL`, `ACCOUNT_OPT_IN`, `PAID_PERSISTENT`, `ENTERPRISE`
- public TTL, ephemeral root, source/byte/time budget, kill switch 설정
- public production에서 OAuth/PostgreSQL을 요구하지 않는 대신 ephemeral root, HTTPS, abuse key를 요구
- ADR 최대 TTL보다 긴 설정 fail closed
- `doctor`가 service mode와 실제 검증 상태를 정확히 표시

**DoD**

- `PSR_SERVICE_MODE=public_ephemeral` production 설정이 OAuth 없이 유효하다.
- persistent content adapter가 public container에 주입되지 않는다.
- unsafe TTL, writable permission, content telemetry 설정은 startup 전에 실패한다.

### CH-S0.2 Public Access와 Tool Catalog Skeleton

**요구사항:** `FR-PUB-001~004`

**추가/수정**

- `src/psr_mcp/public/context.py`
- `src/psr_mcp/public/schemas.py`
- `src/psr_mcp/mcp/public_server.py`
- `src/psr_mcp/mcp/server.py`
- `tests/integration/test_public_mcp_contract.py`

**동작**

- public 요청은 identity·Membership 없이 `PublicRequestContext`를 만든다.
- 최초에는 `psr.service.policy`와 stub `psr.research.quick`만 등록한다.
- Foundation Tool은 public catalog에 나타나지 않는다.
- Tool schema는 `schema_version=1.0`과 stable error code를 사용한다.

**DoD**

- token 없는 MCP session에서 `service.policy` 성공
- public catalog snapshot deterministic
- public request가 `auth/`와 `storage/postgres/`를 호출하지 않는 spy test 통과

### CH-S0.3 Abuse Limiter 교체

**요구사항:** `FR-PUB-050~057`

**수정/추가**

- `src/psr_mcp/mcp/http_policy.py`
- `src/psr_mcp/abuse/ports.py`
- `src/psr_mcp/abuse/limiter.py`
- `tests/unit/test_public_abuse_limiter.py`
- `tests/integration/test_public_http_policy.py`

**정책**

- edge는 raw IP quota를 담당한다.
- application은 trusted proxy가 정규화한 client IP를 rotating HMAC으로 bucket화한다.
- token digest는 부가 bucket일 뿐 IP bucket을 대체하지 않는다.
- quick/start/active/global/source-host limiter를 분리한다.
- raw IP와 token은 log·DB에 저장하지 않는다.
- kill switch는 새 quick/start만 거부한다.

**상태:** process-local HMAC limiter, trusted proxy CIDR/client IP 정규화와
`PSR_PUBLIC_MAX_ACTIVE_QUICK` 기반 process-local quick 동시실행 상한은 구현 완료했다.
초과 요청은 workspace와 source network를 만들기 전에 `PUBLIC_LIMIT_REACHED`로 거부하며,
성공·오류·취소 경로 모두 slot을 반환한다. `PSR_PUBLIC_DAILY_QUICK_BUDGET` 기반 UTC 일일
진입 budget도 구현했다. production 공개 mode는 명시값 없이는 시작하지 않으며, 소진 시
workspace·network 전에
`PUBLIC_DAILY_BUDGET_EXHAUSTED`로 거부한다. `PSR_PUBLIC_PAUSE_FILE`의 존재 여부만 읽는
runtime pause도 구현했다. 새 quick은 즉시
거부하되 진행 중인 결과의 access block과 purge는 유지하며 sentinel 제거 시 restart 없이
resume한다. direct NGINX의 header overwrite, raw-IP request/connection quota 기준과 Python
TLS spoof 시험은 구현했다. 실제 NGINX OCI, public IP, multi-replica 공유 quota와 provider
billing hard cap은 CH-P3.1에서 검증한다.

**DoD**

- 100개의 invalid bearer를 회전해도 같은 IP budget을 초과할 수 없다.
- 다른 IP fixture는 독립 bucket을 사용한다.
- process active quick 상한에서 초과 요청은 workspace 생성 전에 거부되고 종료 뒤 slot이 반환된다.
- UTC 일일 budget은 잘못된 입력을 차감하지 않고 시작된 성공·실패를 차감하며 날짜 변경 시 reset된다.
- runtime pause는 service policy에 반영되고 새 quick만 거부하며 진행 중 purge를 막지 않는다.
- `Retry-After`와 `PUBLIC_LIMIT_REACHED`가 일관되다.
- HMAC key rotation과 counter TTL test가 있다.

### CH-S0.4 Ephemeral Workspace

**요구사항:** `FR-PUB-040~046`, `NFR-PUB-004~006`

**추가**

- `src/psr_mcp/ephemeral/ports.py`
- `src/psr_mcp/ephemeral/filesystem.py`
- `src/psr_mcp/ephemeral/metadata.py`
- `tests/contract/test_ephemeral_store.py`

**계약**

```python
class EphemeralWorkspaceStore(Protocol):
    async def create(self, *, expires_at: datetime) -> WorkspaceRef: ...
    async def write_bytes(self, ref: WorkspaceRef, kind: ArtifactKind, data: bytes) -> None: ...
    async def read_bytes(self, ref: WorkspaceRef, kind: ArtifactKind) -> bytes: ...
    async def block_access(self, ref: WorkspaceRef) -> None: ...
    async def purge(self, ref: WorkspaceRef) -> PurgeResult: ...
```

**불변조건**

- run directory 이름은 CSPRNG 값이다.
- directory `0700`, file `0600`
- path traversal과 symlink follow 금지
- file name에 user input·URL·기관명 금지
- operational metadata에 question/content field 금지

**DoD**

- permission, traversal, symlink, concurrent purge contract test 통과
- persistent DB에 content write가 발생하지 않음

### CH-S0.5 Purge Sweeper와 Leakage Test

**요구사항:** `AC-PUB-003`, `AC-PUB-020~022`

**추가**

- `src/psr_mcp/ephemeral/sweeper.py`
- `tests/integration/test_ephemeral_purge.py`
- `tests/security/test_content_canary.py`

**동작**

- startup scan
- 1분 주기 sweep
- delivered 60초, undelivered 60분, failed 10분, hard orphan 2시간
- 삭제 실패 시 먼저 access block, exponential retry, content-free alert
- process shutdown에서도 best-effort purge

**DoD**

- fake clock 상태별 TTL test
- SIGKILL equivalent 후 restart purge
- delete permission 오류 후 eventual purge
- log, tmp, operational metadata, exception output canary 0건

### S0 종료

`PG0`를 통과한 뒤에만 실제 URL 수집을 시작한다.

## 7. P1 — Useful Quick Research

### CH-P1.1 Legacy Characterization

**산출물**

- `tests/fixtures/legacy_crawlkit/`
- `docs/legacy/CRAWLKIT_CHARACTERIZATION.md`
- `docs/legacy/REUSE_MATRIX.md`

**검사**

- command/subcommand
- `probe` JSON
- HTML/PDF/JSON output
- hash와 filename 규칙
- retry/timeout/redirect
- cookie/header 처리
- 실패 exit code와 partial artifact
- dependency/license

**DoD**

- 확인하지 못한 동작은 `Assumption`으로 표시
- `reuse`, `refactor`, `replace`, `do-not-port`가 함수/기능 단위로 분류

### CH-P1.2 Planner/Profile Baseline

**요구사항:** `FR-PUB-010~014`

**추가**

- `src/psr_mcp/planner/models.py`
- `src/psr_mcp/planner/government.py`
- `src/psr_mcp/planner/service.py`
- `profiles/government-v0.yaml`
- `profiles/schema.json`
- `tests/unit/test_government_planner.py`

**입력**

- question, as_of_date, jurisdiction, budget

**출력**

- normalized scope
- subquestions
- source tracks
- evidence requirements
- stop conditions

**DoD**

- 같은 입력은 같은 baseline plan을 생성
- 공공기관 AI 구매 원칙 fixture가 법령·조달·개인정보·데이터권리·업체종속을 포함
- over-broad question은 budget 안의 범위로 축소하거나 limitation을 반환

### CH-P1.3 Search/URL Policy

**요구사항:** `FR-PUB-020~023`

**추가**

- `src/psr_mcp/search/ports.py`
- `src/psr_mcp/search/providers/<provider>.py`
- `src/psr_mcp/collectors/policy.py`
- `tests/security/test_ssrf_policy.py`

**DoD**

- HTTPS 443 기본
- userinfo, IP literal 정책, DNS private range, metadata hostname 차단
- redirect마다 전체 재검증
- DNS rebinding 방어 방식이 test 가능
- user cookie, Authorization, client certificate 입력 자체를 받지 않음

**상태:** 구현 완료. `GovernmentQueryBuilder`, `GovernmentSourceRegistry`,
`CuratedOfficialSourceProvider`, `BraveSearchProvider`, `UrlPolicy`,
`PinnedHttpcoreTransport`가 연결됐다. 모든 discovery 결과는 Evidence가 아닌 candidate로만
취급한다. 기본값은 disabled이고, curated는 no-key 제한 범위, Brave는 server-side API key가
필요한 선택형 live Search다.

### CH-P1.4 Bounded Collector

**요구사항:** `FR-PUB-024~025`, `FR-PUB-051~052`

**추가**

- `src/psr_mcp/collectors/ports.py`
- `src/psr_mcp/collectors/models.py`
- `src/psr_mcp/collectors/http.py`
- `tests/contract/test_collector.py`

**결과**

```text
CollectionResult
- status: SUCCESS | PARTIAL | BLOCKED | FAILED
- media_type
- bytes_received
- retrieved_at
- redirect_chain
- policy_results
- retryable
- artifact_ref
```

**DoD**

- timeout, retry, rate, byte, decompression budget
- login/error/empty page 제외
- source별 실패가 전체 Run을 자동 실패시키지 않음

**상태:** 구현 완료. 요청별/Run별 byte budget, connect/read/total timeout, manual redirect,
identity encoding, header allowlist와 typed partial failure를 적용했다. production pipeline은
같은 SafeCollector로 `robots.txt`를 먼저 검사한다.

### CH-P1.5 Parsers

**추가**

- `src/psr_mcp/parsers/html.py`
- `src/psr_mcp/parsers/pdf.py`
- `src/psr_mcp/parsers/json.py`
- `tests/fixtures/documents/`

**DoD**

- HTML heading path locator
- PDF page locator
- JSON Pointer
- scanned PDF는 허위 text 대신 `OCR_REQUIRED`
- page/node/depth/string/time/memory budget test

**상태:** 구현 완료. magic/MIME sniff 뒤 HTML·JSON·text를 bounded parser로 처리한다. PDF는
별도 subprocess에서 pypdf로 읽고 page·text·wall-time 제한과 가능한 환경의 memory/CPU/FD
제한을 적용한다. blank scan은 `OCR_REQUIRED`, 암호화 문서는 `ENCRYPTED_DOCUMENT`다.

### CH-P1.6 Evidence and Reporting

**요구사항:** `FR-PUB-030~035`

**추가**

- `src/psr_mcp/evidence/models.py`
- `src/psr_mcp/evidence/dedup.py`
- `src/psr_mcp/evidence/scoring.py`
- `src/psr_mcp/evidence/composer.py`
- `src/psr_mcp/reporting/markdown.py`
- `src/psr_mcp/reporting/json.py`

**Evidence Score v0**

- authority
- primary_source
- directness
- freshness
- original_obtained
- independence
- locator_quality
- applicability

각 component는 `value`, `reason`, `observed facts`를 가진다. 하나의 total score만 저장하지 않는다.

**DoD**

- citation 없는 FACT lint 실패
- official primary와 republisher cluster 구분
- Markdown/JSON의 finding·citation ID 일치
- excerpt 길이 상한과 저작권 고지

**상태:** 핵심 구현 완료. citation ID, 원문 SHA-256, locator, 짧은 excerpt와 7개 설명형
score component를 반환한다. URL·동일 passage·동일 document hash를 중복 제거하고 track별
citation을 우선 확보한다. 동일 원문이 여러 track을 지지하는 관계를 보존하고, Government
Profile의 한·영 selection term으로 관련 구간 주변 excerpt를 만든다. 현재 자동 finding은
원문 발췌 FACT와 사전 검토된 anchor group을 모두 만족한 조달 원칙 후보를 구분해 만든다.
anchor가 부족한 track에는 recommendation을 생성하지 않으며, 적용범위와 conflict synthesis는
사람 QA 뒤 고도화한다.

### CH-P1.7 Quick Research Tool

**요구사항:** `AC-PUB-001~003`, `AC-PUB-040~043`

**추가/수정**

- `src/psr_mcp/public/services.py`
- `src/psr_mcp/mcp/public_server.py`
- `tests/e2e/test_public_quick_research.py`

**처리**

```text
validate
→ quota
→ create workspace
→ plan
→ search/collect/parse
→ dedup/compose
→ render
→ return
→ purge
```

**DoD**

- 30초 hard limit
- budget 초과는 `PARTIAL`
- result에 as-of, citations, gaps, conflicts, failures, retention
- response 완료 후 workspace content 0

**상태:** 구현 완료. 실제 pipeline 결과의 source/extracted/result를 ephemeral workspace에서
처리하고 접근 차단·purge 성공 뒤에만 응답한다. Search·수집·파싱 일부 실패는 성공 근거와 함께
`PARTIAL`로 보존한다.

### CH-P1.8 Live Official-Source Validation

**선행조건**

- 운영자가 승인한 Search provider credential 또는 별도 official-source seed adapter
- 외부 provider 고지와 비용상한
- 당시 source 약관·robots·저작권 운영검토

**검증**

- 실제 법령·정부 가이드·조달·개인정보 source로 GR-001~004 실행
- source tier·locator·hash·점수의 사람이 읽는 검토
- generic evidence bundle이 실제 공공업무 초안에 충분한지 평가
- 부족하면 LLM을 바로 신뢰하지 않고 citation-constrained Writer 계약과 lint를 추가
- query/provider 비용, timeout, 403, robots unavailable 비율 측정

**2026-07-16 중간 결과**

- fixed official URL 5종으로 7개 track의 실제 citation/locator 선택은 PASS
- `CuratedOfficialSourceProvider`와 `PSR_SEARCH_PROVIDER=curated` 구현
- 실제 quick smoke에서 7개 track, 12개 citation, failure 0, curated limitation과
  government-policy·procurement missing-anchor gap 3건
- Writer는 12개 FACT와 근거 anchor가 충족된 5개 RECOMMENDATION을 생성
- 실제 quick Markdown은 한국어 검토 순서와 동일 citation ID를 유지하고 약 19KB로 반환
- 동일 PIPC·WEF URL은 각 1회만 수집하고 여러 track provenance를 보존
- 결과 전달 뒤 `server_saved=false`, `PURGED`, ephemeral directory empty 확인
- 개인정보위 PDF `pdf:page:40`, NIST AI RMF `pdf:page:20`,
  WEF 조달자료 `pdf:page:19`와 `pdf:page:26:chunk-1` 선택 확인
- 국가법령정보센터 동적 shell은 Evidence 제외, 정적 조문정보는 사용 가능
- live Search provider recall·비용·보존경계와 공공업무 담당자 human QA는 PENDING
- local review packet은 구조지표를 자동 계산하고 법적 과잉해석·업무 유용성은 사람 판정으로
  남기며, 질문·결과는 stdout에만 출력하고 feedback token은 제외한다.
- 첫 실제 packet 내부 검토에서 개인정보 근거를 “기관 데이터 전체”로 확대한 권고를 발견해
  개인정보·이용자 입력데이터와 정보주체의 선택권 범위로 좁혔다. 외부 공공업무 담당자
  독립 QA와 GR-002~004는 PENDING이다.

**DoD**

- 실제 공식 원문 비율 70% 이상
- citation 없는 FACT 0개
- critical factual contradiction과 unsupported legal conclusion 0개
- provider query retention과 PSR server retention을 사용자에게 분리 고지
- validation report에 credential을 노출하지 않은 evidence artifact 기록

## 8. P2 — Ephemeral Async

### CH-P2.1 Handle and Run Metadata

- 192-bit CSPRNG handle
- keyed digest 저장
- full handle log 금지
- `EphemeralRun` content-free schema
- uniform `RUN_EXPIRED_OR_NOT_FOUND`

### CH-P2.2 Async Application Service

- start: 2초 안에 handle
- status: progress bucket만
- result: `consume=true` 기본
- cancel: access block + purge
- idempotency는 optional anonymous request key로 제한

### CH-P2.3 Worker Lifecycle

- claim, heartbeat, retry, cancellation
- source별 partial success
- metadata store와 workspace 상태 reconciliation
- worker crash 후 bounded retry

### CH-P2.4 MCP Contract and Fault Tests

- `psr.research.start`
- `psr.research.run.status`
- `psr.research.run.result`
- `psr.research.run.cancel`
- reconnect, restart, expired handle, concurrent consume
- delivered purge, undelivered TTL, disk full

### P2 종료

- `PG2 Zero Retention` 전부 통과
- async result가 persistent Resource에 저장되지 않음
- handle 분실 시 복구 불가를 정책에 명시

## 9. P3 — Public Preview

### CH-P3.1 Deployment Boundary

- TLS reverse proxy/WAF
- gateway가 `X-PSR-Client-IP`를 단일 canonical IP로 overwrite하는 설정과 spoof rehearsal
- edge quota와 application quota 이중 적용
- encrypted ephemeral volume
- egress allow/deny와 DNS policy
- public kill switch rehearsal

**현재:** pinned multi-stage OCI artifact, non-root runtime, read-only/tmpfs 실행계약,
network-none fixture smoke와 static contract CI를 구현했다. 로컬 환경에는 Docker engine이 없어
실제 image build는 CI 증적 전까지 PENDING이다. 실제 TLS gateway, egress와 provider hard cap은
계속 외부 gate다.

### CH-P3.2 Feedback and Product Metrics

- one-time feedback token
- `helpful: bool`
- `save_feature_interest: bool`
- free text 기본 비활성
- question/run/content와 join 불가
- 결과 수령률, official ratio, citation coverage, cost bucket

**현재:** purge 확인 뒤 version·nonce·expiry만 가진 HMAC token을 발급하고
`psr.feedback.submit`이 boolean 2개만 수집한다. raw token·question·result는 저장·로그하지
않고 만료형 token digest와 process-local aggregate count만 유지한다. 변조·만료·재사용은
`FEEDBACK_TOKEN_INVALID_OR_USED`로 통합한다. multi-replica shared replay cache와 durable
content-free metric sink는 실제 공개 확장 전 후속이다.

### CH-P3.3 Documentation and Host Onboarding

- 공개 MCP 연결 가이드
- 지원 Host 2종 smoke
- 실제 `service.policy`와 config 자동 비교
- known limitation, provider/privacy/copyright notice
- `psrctl doctor` stale limitation 수정

**현재:** doctor는 `local_smoke_ready`, `public_deployment_config_ready`,
`accepting_new_research`, check별 pass/warn/fail과 외부 pending gate를 출력한다.
`--require-public-ready`는 미달 시 exit 5이며 secret 값은 출력하지 않는다. 실제 Host 2종과
gateway staging rehearsal은 여전히 외부 검증 대상이다.

`psrctl conformance-public`은 공식 SDK로 anonymous initialize, 정확한 public Tool catalog,
빈 Resource/Prompt catalog, service policy, quick schema·구조 품질, purge 표시와 새 연결의
policy 일치를 검사한다. 출력은 count·ratio·상태만 포함하고 질문·인용·feedback token을
제외한다. `--verify-feedback`은 aggregate를 오염시키므로 staging에서만 사용한다.

OCI `test` target의 `scripts/container_smoke.py`는 development fixture에서만
`release_gate=false`로 같은 SDK flow를 실행한다. 이는 image wiring과 purge를 검증하지만 실제
공식자료 품질이나 공개 release gate로 승격하지 않는다.

### CH-P3.4 Public Release Rehearsal

- load/cost test
- abuse simulation
- purge failure game day
- dependency/license/secret scan
- rollback/kill switch
- 24~72시간 제한 공개 후 gate review

## 10. A0 — Free Account Beta 준비

R4 product trigger 전에는 착수하지 않는다.

초기 Account Beta는 무료·제한 quota이며 Public endpoint를 대체하지 않는다. 아래 변경은 한 번에
구현하지 않고 identity-only → opt-in save → freshness-aware reuse 순으로 나눈다.

### A0.1 Identity-only

1. OIDC broker와 `AccountIdentity(issuer, subject)` bootstrap
2. Personal Workspace 자동 생성과 user-scoped authorization
3. Account deployment 전용 protected resource metadata와 Tool catalog
4. 로그인 상태에서도 `retention_mode=ephemeral`, `reuse_mode=off` 기본값
5. Account 장애 중 anonymous Public conformance가 통과하는 독립 배포 test

### A0.2 Opt-in Save

1. `users`와 `research_runs.initiated_by`의 `(organization_id, id)` composite FK
2. unknown `kid` negative cache와 refresh cooldown
3. `retention_mode=saved` explicit consent
4. Personal Workspace RLS와 persistent object namespace
5. export/delete/account close
6. persistent object encryption과 deletion manifest
7. saved preflight 실패 시 조사 시작 전 fail-closed
8. 익명 완료 결과의 자동 소급 귀속 금지와 명시적 `user_imported` provenance

### A0.3 Freshness-aware Reuse

1. `reuse_mode=off|prefer_fresh|saved_only`
2. 신규 계정은 `off`, Workspace 기본값 변경은 사용자 명시 동의
3. Saved Evidence search port와 relevance filter
4. Research Profile별 `FreshnessEvaluator`
5. fresh/stale/unknown 판정과 stale track의 bounded refresh
6. 결과의 reused/new Evidence와 freshness provenance
7. delete와 reuse index의 원자적 제거
8. cross-user reuse와 `saved_only` network call 0 test

Public Preview deployment와 Account deployment는 mode와 data sink가 분리돼야 한다.

## 11. 요구사항 추적

| 요구사항 | 구현 increment | 검증 |
|---|---|---|
| FR-PUB-001~004 | S0.1~S0.2 | VAL-PUB-MODE, MCP |
| FR-PUB-010~016 | P1.2, P1.8 | VAL-PUB-PLAN, SOURCE DISCOVERY |
| FR-PUB-020~025 | P1.3~P1.5 | VAL-PUB-NET, PARSE |
| FR-PUB-030~039 | P1.6~P1.9 | VAL-PUB-EVIDENCE, QUALITY |
| FR-PUB-040~046 | S0.4~S0.5, P2 | VAL-PUB-RETENTION |
| FR-PUB-050~054 | S0.3, P3.1 | VAL-PUB-ABUSE |
| FR-PUB-060~063 | P3.2 | VAL-PUB-FBK-* |
| NFR-PUB-001~010 | S0~P3 | PG0~PG3 |
| FR-ACC-001~009 | A0.1~A0.2 | AG0 |
| FR-ACC-010~015 | A0.3 | AG0 |

## 12. Definition of Ready

- 연결된 requirement와 validation ID
- input/output/error schema
- content retention과 log 영향
- network/secret/SSRF 영향
- sample fixture
- disable/rollback 방법
- 명시적 비범위

## 13. Definition of Done

- 구현과 unit/contract/integration/security test가 같은 change에 있음
- `ruff`, `mypy`, 전체 test와 독립 coverage gate 통과
- User Content canary scan 통과
- partial failure와 retry가 typed result로 검증됨
- schema snapshot과 docs 갱신
- mode별 startup fail-closed 검증
- 운영 metric은 allowlist field만 사용
- known limitation과 다음 gate 기록

## 14. 현재 다음 세 change

```text
CH-P1.9 공공업무 담당자 QA와 citation-constrained Writer 판단
CH-P1.10 국가법령정보센터 source adapter
CH-P3.1 trusted edge IP·cost kill switch의 최소 공개 경계
CH-P2.1/2 opaque handle과 ephemeral async lifecycle
```

curated 실제 source 수집·Evidence·purge smoke는 완료됐다. 사람이 읽은 결과가 업무에 충분하지
않으면 async보다 먼저 citation-constrained Writer를 보강한다. 반대로 quick이 유용하지만 30초
안에 끝나지 않는 비율이 높으면 P2 async를 우선한다. Brave 등 live Search는 curated 범위를
넓히는 비교 실험으로 별도 승인하며, Account/Paid 기능은 R4 product trigger 전 시작하지 않는다.

## 15. 진행 보고 형식

```text
Completed:
Validated:
Content retained:
Public risks changed:
Not validated:
Artifacts:
Next gate:
```

`Content retained`는 항상 명시하며 Public Preview에서 기대값은 `none beyond documented TTL`이다.

---

현재 구현의 첫 목적은 로그인이나 저장기능이 아니다. **익명 사용자가 안전하게 조사 한 건을 받고, 서버가 그 content를 약속대로 지우는 vertical slice**다.
