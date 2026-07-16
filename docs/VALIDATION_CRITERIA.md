# Public Sector Research MCP — Validation Criteria

> 문서 상태: Approved for Implementation · 기준일: 2026-07-16 · 대상: Foundation F0~F4

[DETAILED DESIGN](./DETAILED_DESIGN.md) · [IMPLEMENTATION PLAN](./IMPLEMENTATION_PLAN.md) · [PRD](./PRD.md)

## 1. 목적

이 문서는 “동작한다”를 관찰 가능한 증거로 바꾼다. 검증은 기능 happy path뿐 아니라 Tenant 격리, 상태 경합, 장애 복구, protocol 호환성을 포함한다.

표기:

- **Automated:** CI에서 매 변경 실행
- **Environment:** PostgreSQL·OIDC·Host 같은 실제 환경 필요
- **Review:** 사람이 schema, report, threat model을 확인
- **Gate:** 미통과 시 다음 단계로 진행 불가

## 2. 검증 환경

| Environment | 목적 | 허용되는 주장 |
|---|---|---|
| Unit | pure domain/policy | invariant 구현됨 |
| In-memory integration | service/UoW/MCP contract | application contract 구현됨 |
| PostgreSQL integration | RLS/transaction/lease | durability와 DB tenant 격리 검증됨 |
| OAuth integration | issuer/audience/scope/JWKS | production auth adapter 검증됨 |
| Remote MCP | HTTP/proxy/Host | transport interoperability 검증됨 |
| Pilot | 실제 사용자/기관 정책 | operational readiness |

In-memory test만으로 durability, RLS, OAuth, production readiness를 주장하지 않는다.

## 3. 표준 검증 명령

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
uv run pytest --cov=psr_mcp --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json
uv run python scripts/coverage_gate.py --coverage-json coverage.json
```

PostgreSQL 환경:

```bash
uv run pytest -m postgres
```

Remote conformance:

```bash
uv run psrctl conformance --json
```

실제 command는 해당 increment에서 구현되며, 문서와 CI를 함께 갱신한다.

## 4. Gate 요약

| Gate | 의미 | 필수 검증 |
|---|---|---|
| G0 | Buildable | BUILD, dependency, import boundary |
| G1 | Domain Safe | DOM, AUTH, APP, PORT |
| G2 | MCP Contract | MCP schema/flow/error |
| G3 | Durable | DB, JOB, recovery, audit atomicity |
| G4 | Authenticated | OAuth, Membership, security |
| G5 | Interoperable | Streamable HTTP, 2 Hosts |
| G6 | Foundation Exit | G0~G5 + docs/runbook/no P0/P1 |

현재 구현 increment는 `G0~G2`, PostgreSQL 17.10 local `G3`, OAuth/Membership local `G4`를 통과했다. F4 code와 SDK/Inspector remote conformance는 완료됐지만 Codex Resource/Prompt 보안 승인이 남아 `G5 PARTIAL`, `G6 OPEN`이다. 실행 증적은 [Foundation Core 보고서](./validation/2026-07-16-foundation-core.md), [PostgreSQL G3 보고서](./validation/2026-07-16-postgresql-g3.md), [OAuth G4 보고서](./validation/2026-07-16-oauth-g4.md), [Remote G5 보고서](./validation/2026-07-16-remote-g5.md)에 있다.

## 5. Build와 Dependency

| ID | 기준 | 방법 | Gate |
|---|---|---|---|
| VAL-BUILD-001 | Python 3.12에서 install 가능 | clean `uv sync` | G0 |
| VAL-BUILD-002 | `mcp` major 1 lock | lockfile 검사 | G0 |
| VAL-BUILD-003 | package import 성공 | `python -c`/test | G0 |
| VAL-BUILD-004 | source package에 circular import 없음 | import test | G0 |
| VAL-BUILD-005 | ruff/mypy clean | automated | G0 |
| VAL-BUILD-006 | domain/application이 `mcp`, DB driver import 안 함 | AST/import boundary test | G0 |
| VAL-BUILD-007 | dependency vulnerability critical 0 | scanner, release | G6 |
| VAL-BUILD-008 | dependency license manifest 존재 | review | G6 |

## 6. Domain

| ID | 기준 | Expected |
|---|---|---|
| VAL-DOM-001 | 빈 Organization/User/Project ID 거부 | domain error |
| VAL-DOM-002 | naive datetime 거부 | domain error |
| VAL-DOM-003 | Project version은 1 이상 | invalid 거부 |
| VAL-DOM-004 | APPROVED Plan은 approver/time 필수 | invalid 거부 |
| VAL-DOM-005 | DRAFT Plan에 approver 없음 | invalid 거부 |
| VAL-DOM-006 | Run은 QUEUED로 생성 | exact state |
| VAL-DOM-007 | terminal→nonterminal 전이 거부 | `INVALID_STATE` |
| VAL-DOM-008 | RUNNING→SUCCEEDED/PARTIAL/FAILED/CANCELLED 허용 | version 증가 |
| VAL-DOM-009 | cancellation reason length 검증 | invalid 거부 |
| VAL-DOM-010 | idempotency key constraint | invalid 거부 |
| VAL-DOM-011 | Job lease expiry는 UTC로 비교 | deterministic clock |
| VAL-DOM-012 | domain은 immutable value semantics | mutation 불가 |

## 7. Authorization과 Tenant

### 7.1 Matrix

fixture:

- Organization A: Project A1, A2
- Organization B: Project B1
- User A-wide: A의 Researcher, org-wide
- User A-limited: A의 Researcher, A1 only
- Manager A: A의 Research Manager
- User B: B의 Researcher
- Revoked A: revoked Membership
- Service A: service identity, no human approval capability

| ID | 행위 | Expected |
|---|---|---|
| VAL-AUTH-001 | A-wide가 A1 list/get | 허용 |
| VAL-AUTH-002 | A-wide가 B1 ID get | `NOT_FOUND_OR_FORBIDDEN` |
| VAL-AUTH-003 | A-limited가 A2 get | `NOT_FOUND_OR_FORBIDDEN` |
| VAL-AUTH-004 | User B가 A Run status | 거부 |
| VAL-AUTH-005 | scope 없는 A가 A1 get | `AUTH_SCOPE_REQUIRED` |
| VAL-AUTH-006 | role 없는 scope 보유자 | 거부 |
| VAL-AUTH-007 | revoked Membership | 거부 |
| VAL-AUTH-008 | Resource와 Tool의 동일 target | 동일 policy result |
| VAL-AUTH-009 | error/log에 B entity name 없음 | leakage 0 |
| VAL-AUTH-010 | service identity가 human approval | 거부 |

### 7.2 Production OAuth

| ID | Token | Expected | Gate |
|---|---|---|---|
| VAL-OAUTH-001 | valid issuer/audience/scope | context 생성 | G4 |
| VAL-OAUTH-002 | wrong issuer | 401 | G4 |
| VAL-OAUTH-003 | wrong audience | 401 | G4 |
| VAL-OAUTH-004 | expired/not-before | 401 | G4 |
| VAL-OAUTH-005 | missing scope | 403/Tool denied | G4 |
| VAL-OAUTH-006 | unsupported algorithm | 401 | G4 |
| VAL-OAUTH-007 | rotated key | refresh 후 성공 | G4 |
| VAL-OAUTH-008 | AS unavailable, unknown key | fail closed | G4 |
| VAL-OAUTH-009 | client token in downstream | 없음 | Collector gate |
| VAL-OAUTH-010 | Protected Resource Metadata | spec/schema valid | G4 |

## 8. Port와 Transaction

| ID | 기준 | Expected |
|---|---|---|
| VAL-PORT-001 | repository method에 organization 필수 | signature/static test |
| VAL-PORT-002 | transaction commit | 변경 보존 |
| VAL-PORT-003 | exception rollback | 변경 없음 |
| VAL-PORT-004 | uncommitted context exit | rollback |
| VAL-PORT-005 | read-your-write | transaction 내 보임 |
| VAL-PORT-006 | duplicate idempotency unique | conflict 또는 기존 반환 |
| VAL-PORT-007 | stale version update | `VERSION_CONFLICT` |
| VAL-PORT-008 | audit 실패 | business write rollback |
| VAL-PORT-009 | memory/PG adapter contract 동일 | parameterized suite |

## 9. Application Service

| ID | 기준 | Expected |
|---|---|---|
| VAL-APP-001 | list 기본 limit/정렬 | deterministic |
| VAL-APP-002 | limit 0/101 | `INPUT_INVALID` |
| VAL-APP-003 | invalid cursor | `INPUT_INVALID` |
| VAL-APP-004 | Project filter가 tenant/restriction 적용 | authorized only |
| VAL-APP-005 | approved Plan start | QUEUED Run/Job |
| VAL-APP-006 | draft/rejected Plan start | `PLAN_NOT_APPROVED` |
| VAL-APP-007 | archived Project start | `INVALID_STATE` |
| VAL-APP-008 | 동일 key+request 재호출 | 같은 Run ID |
| VAL-APP-009 | 동일 key+다른 Plan | `IDEMPOTENCY_CONFLICT` |
| VAL-APP-010 | Run start audit | actor/target/outcome |
| VAL-APP-011 | status는 lease owner 미노출 | field 없음 |
| VAL-APP-012 | QUEUED cancel | 즉시 CANCELLED |
| VAL-APP-013 | RUNNING cancel | request flag |
| VAL-APP-014 | stale expected version | `VERSION_CONFLICT` |
| VAL-APP-015 | terminal cancel | `INVALID_STATE` |
| VAL-APP-016 | 실패 transaction | Run/Job/Audit 모두 없음 |

## 10. Job과 Concurrency

| ID | 기준 | Expected | Gate |
|---|---|---|---|
| VAL-JOB-001 | QUEUED claim | RUNNING, owner, expiry | G1 |
| VAL-JOB-002 | 두 worker 동시 claim | 한 worker만 획득 | G1/G3 |
| VAL-JOB-003 | owner heartbeat | expiry 연장 | G1 |
| VAL-JOB-004 | 다른 owner heartbeat | 거부 | G1 |
| VAL-JOB-005 | expired lease | 재claim 가능 | G1 |
| VAL-JOB-006 | max attempts | FAILED/RETRY_EXHAUSTED | G1 |
| VAL-JOB-007 | cancel requested | 새 step 시작 안 함 | G1 |
| VAL-JOB-008 | complete terminal | lease clear | G1 |
| VAL-JOB-009 | PG `SKIP LOCKED` | exclusive claim | G3 |
| VAL-JOB-010 | worker crash | expiry 후 복구 | G3 |
| VAL-JOB-011 | commit 전 DB loss | Run 미생성 | G3 |
| VAL-JOB-012 | commit 후 response loss+retry | 같은 Run 반환 | G3 |
| VAL-JOB-013 | cancel/complete race | 한 transition, 다른 conflict | G3 |
| VAL-JOB-014 | queue fairness fixture | deterministic order | G3 |
| VAL-JOB-015 | attempts persistent | restart 후 유지 | G3 |

## 11. MCP Contract

| ID | 기준 | Expected |
|---|---|---|
| VAL-MCP-001 | Tool 이름 | 정확한 `psr.*` 5개 |
| VAL-MCP-002 | inputSchema | 필수/길이/범위 반영 |
| VAL-MCP-003 | outputSchema | Pydantic schema와 일치 |
| VAL-MCP-004 | schema version | `1.0` |
| VAL-MCP-005 | list ordering | deterministic |
| VAL-MCP-006 | schema snapshot 변화 | explicit review 필요 |
| VAL-MCP-007 | success structuredContent | machine-readable |
| VAL-MCP-008 | text fallback | 짧고 secret 없음 |
| VAL-MCP-009 | domain error | `isError=true`, code 포함 |
| VAL-MCP-010 | protocol malformed request | JSON-RPC error |
| VAL-MCP-011 | internal error | operation ID만 노출 |
| VAL-MCP-012 | Tool/Resource auth parity | 동일 결과 |
| VAL-MCP-013 | annotations 무시해도 안전 | server auth 적용 |
| VAL-MCP-014 | Project Resource read | authorized JSON |
| VAL-MCP-015 | Run Resource read | authorized status |
| VAL-MCP-016 | unauthorized URI | opaque denial |
| VAL-MCP-017 | Prompt list/get | 등록·argument schema |
| VAL-MCP-018 | Prompt가 authorization 대체 안 함 | protected ID 거부 |
| VAL-MCP-019 | Tasks capability 없어도 flow | 성공 |
| VAL-MCP-020 | disconnect 후 status | explicit ID로 조회 |

## 12. PostgreSQL과 RLS

| ID | 기준 | Expected |
|---|---|---|
| VAL-DB-001 | tenant table `organization_id NOT NULL` | 100% |
| VAL-DB-002 | tenant composite FK | cross-org FK 불가 |
| VAL-DB-003 | RLS enabled+forced | runtime owner에도 적용 |
| VAL-DB-004 | no tenant context | row 0 또는 error |
| VAL-DB-005 | Org A context | A rows only |
| VAL-DB-006 | pool reuse A→B | A data leakage 0 |
| VAL-DB-007 | `SET LOCAL` transaction end | context reset |
| VAL-DB-008 | runtime role no BYPASSRLS | verified |
| VAL-DB-009 | idempotency unique race | one row |
| VAL-DB-010 | optimistic update | one success |
| VAL-DB-011 | migration fresh install | success |
| VAL-DB-012 | migration rollback/restore path | documented/tested |

## 13. Audit와 Observability

| ID | 기준 | Expected |
|---|---|---|
| VAL-AUDIT-001 | write마다 AuditEvent | 100% |
| VAL-AUDIT-002 | actor/org/project/operation/outcome | 필수 field 완전 |
| VAL-AUDIT-003 | idempotent replay | 별도 outcome |
| VAL-AUDIT-004 | authorization denial | security event |
| VAL-AUDIT-005 | bearer token/cookie/raw question | artifact/log 0 |
| VAL-AUDIT-006 | operation ID | request→audit 추적 |
| VAL-AUDIT-007 | metric label cardinality | tenant/user ID 없음 |
| VAL-AUDIT-008 | audit insert failure | write rollback |

## 14. Configuration

| ID | 조건 | Expected |
|---|---|---|
| VAL-CFG-001 | development defaults | loopback only |
| VAL-CFG-002 | production+HTTP public URL | startup fail |
| VAL-CFG-003 | production+static auth | startup fail |
| VAL-CFG-004 | production+memory repository | startup fail |
| VAL-CFG-005 | production missing issuer/DB | startup fail |
| VAL-CFG-006 | diagnostics | secret redacted |
| VAL-CFG-007 | invalid log level/port | input error |
| VAL-CFG-008 | development banner | visible |

## 15. Security Tests

| ID | Attack | Expected |
|---|---|---|
| VAL-SEC-001 | guessed Project/Run ID | opaque denial |
| VAL-SEC-002 | oversized limit/reason/key | schema reject |
| VAL-SEC-003 | forged/modified cursor | reject |
| VAL-SEC-004 | exception with sensitive fixture | response/log redacted |
| VAL-SEC-005 | token passthrough | absent |
| VAL-SEC-006 | production dev mode bypass | impossible |
| VAL-SEC-007 | Prompt/Resource injection into ID | schema reject |
| VAL-SEC-008 | dependency secret scan | finding 0 |

Collector가 추가되면 SSRF, DNS rebinding, redirect escape, decompression bomb, parser bomb, prompt injection corpus를 별도 gate로 추가한다.

## 16. Performance Budget

Foundation Internal Alpha 기준이며 production SLO가 아니다.

| Operation | 조건 | Budget |
|---|---|---:|
| Tool list | 20 tools 이하 | P95 100ms server time |
| Project list | 20 rows, warm DB | P95 200ms |
| Project/Run get | warm DB | P95 150ms |
| Run start | DB healthy | P95 500ms; PRD 외부 2초 이내 |
| Run status | warm DB | P95 150ms |
| Job claim | queue 10k rows | P95 250ms |

성능 테스트가 security filter나 audit를 끈 상태로 실행되면 무효다.

## 17. Recovery

| ID | Fault | Expected |
|---|---|---|
| VAL-REC-001 | Gateway restart | Run status 유지 |
| VAL-REC-002 | worker crash | lease 후 재claim |
| VAL-REC-003 | duplicate client retry | Run 중복 없음 |
| VAL-REC-004 | DB transient | retryable error/무허위 성공 |
| VAL-REC-005 | audit telemetry outage | DB audit 유지 |
| VAL-REC-006 | backup restore | Run/Job/Audit referential integrity |

## 18. Coverage와 품질 기준

- 전체 line coverage: Foundation 90% 이상
- branch coverage: 85% 이상
- domain/policy/application critical modules: line 95% 이상
- authorization matrix에 명시된 case: 100%
- mutation testing은 F2부터 critical state/policy에 적용 검토
- flaky test: 100회 반복에서 0건을 목표
- test가 wall clock, random UUID, locale, network에 직접 의존하지 않음

Coverage 수치만으로 Gate를 통과하지 않는다. security negative case와 environment integration이 우선한다.

`pytest-cov`의 기본 combined percentage는 위 세 임계값을 개별적으로 증명하지 않는다. CI는 coverage JSON에서 statement, branch, critical module을 각각 판정한다. 2026-07-16 완료 감사와 보강 결과는 [Foundation Coverage Gate 감사 보고서](./validation/2026-07-16-foundation-coverage-audit.md)에 기록한다.

## 19. Schema Compatibility

- Tool name 삭제/변경은 major application schema change다.
- required input 추가, enum 제거, field 의미 변경은 breaking이다.
- optional output 추가는 compatible이나 snapshot review가 필요하다.
- `schema_version`은 protocol version과 별도다.
- previous supported schema fixture로 regression test한다.
- Resource URI 변경은 redirect가 아니라 resolver compatibility를 제공한다.

## 20. 문서 검증

| ID | 기준 |
|---|---|
| VAL-DOC-001 | README 링크가 모두 존재 |
| VAL-DOC-002 | Mermaid/code fence가 균형 |
| VAL-DOC-003 | PRD requirement→implementation→validation 추적 가능 |
| VAL-DOC-004 | ADR status와 implementation이 일치 |
| VAL-DOC-005 | command와 실제 entrypoint 일치 |
| VAL-DOC-006 | limitation/open gate가 최신 |

## 21. Gate 판정

### G0 Buildable

- BUILD 전부 통과
- dependency lock 존재
- clean checkout 재현

### G1 Domain Safe

- DOM-001~012, AUTH-001~006·008~009, PORT-001~008, APP-001~016, JOB-001~008, CFG 통과
- cross-tenant failure 0
- critical coverage target 통과

AUTH-007 revoked Membership는 production Membership resolver가 생기는 G4, AUTH-010 human approval은 Planner review workflow가 생기는 P0에서 판정한다. PORT-009의 PostgreSQL 공통 contract는 G3에서 판정한다.

### G2 MCP Contract

- MCP-001~020 통과
- canonical Tool catalog digest 승인
- SDK v1 in-memory/transport test 통과
- application error가 secret/target existence를 노출하지 않음

### G3 Durable

- DB-001~012, JOB-009~015, REC-001~006 통과
- PostgreSQL contract test와 crash test
- backup/restore evidence

### G4 Authenticated

- OAUTH-001~008·010 통과, OAUTH-009는 Collector gate로 명시 이관
- IdP key rotation과 revoked Membership
- security review P0/P1 0건

### G5 Interoperable

- MCP current stable conformance
- 목표 Host 2종에서 Tool/Resource/Prompt
- disconnect/reconnect
- compatibility matrix

### G6 Foundation Exit

- G0~G5 모두 통과
- 운영 runbook, threat model, data dictionary
- unresolved P0/P1 0건
- Product, Architecture, Security owner 승인

## 22. 현재 완료 선언 규칙

현재 환경에서 F0~F3를 완료하면 다음 표현만 사용한다.

> Foundation Core, MCP contract, PostgreSQL 17.10 local durability/RLS와 OAuth/Membership local integration이 검증됐다. 실제 기관 IdP와 remote Host conformance는 아직 검증되지 않았다.

다음 표현은 G6 전 금지한다.

- production ready
- public-sector deployment ready
- production durable queue verified
- secure multi-tenant service verified
- MCP Host compatible

## 23. 검증 결과 기록 양식

```text
Validation ID:
Environment/commit:
Command or procedure:
Expected:
Observed:
Evidence artifact:
Pass/Fail/Blocked:
Reviewer:
Date:
```

자동 test 결과는 CI artifact에, 수동 Host/security 검토는 versioned report에 남긴다.

---

검증의 목적은 test 개수를 늘리는 것이 아니라 **공공업무 사용자가 잘못된 권한·상태·근거를 정상 결과로 오인하지 않게 하는 것**이다.
