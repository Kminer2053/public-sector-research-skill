# Anonymous Public MCP Conformance 검증

> 기준일: 2026-07-16 · 판정:
> **Official SDK Local PASS / HTTPS Gateway and Target Hosts Pending**

[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md) ·
[Host Matrix](../compatibility/host-matrix.md)

## 1. 목적

Foundation용 원격 conformance는 Project, Resource, Prompt와 선택적 Run을 검사한다. Public
Preview는 가입 없는 policy, quick과 feedback만 노출하므로 별도 계약이 필요하다.
`psrctl conformance-public`은 공개 endpoint에서 content를 출력·저장하지 않고 release 직전
핵심 계약을 반복 확인한다.

## 2. 검사 항목

- bearer 없이 MCP initialize
- exact Tool catalog:
  - `psr.service.policy`
  - `psr.research.quick`
  - `psr.feedback.submit`
- Resource template 0개, Prompt 0개
- `public_ephemeral`, `authentication_required=false`
- `research_available=true`, runtime pause false
- `server_saved=false`, `feedback_content_linked=false`
- `government-v0` profile
- quick output의 reviewed Pydantic schema
- policy와 quick의 source discovery 일치
- citation 존재와 feedback capability 만료시각
- FACT·RECOMMENDATION citation coverage
- locator completeness
- unique document 기준 공식 1차자료 비율
- 필수 source track recall
- `PURGED`, `server_saved=false`
- 새 MCP session에서 policy 재호출

release gate는 실제 source mode와 구조 품질 PASS를 요구한다. 개발 fixture transport test는
programmatic `release_gate=false`에서만 허용되며 CLI는 완화 옵션을 제공하지 않는다.

## 3. Feedback 지표 보호

기본 conformance는 token의 존재와 expiry만 확인하고 제출하지 않는다. 따라서 실제 사용자
helpful·저장기능 관심 지표를 오염시키지 않는다.

`--verify-feedback`은 false/false synthetic feedback을 한 건 제출한다. 이 옵션은 local
integration 또는 초기화 가능한 staging 전용이다. production synthetic probe에서 사용하지
않는다.

conformance 자체는 실제 quick 한 건이므로 daily budget과 provider 비용을 소비한다. Brave
mode에서는 고정된 synthetic 질문에서 생성한 검색어가 provider로 전달될 수 있다. 이 명령을
상시 healthcheck나 고빈도 monitor로 사용하지 않는다.

## 4. 실제 curated loopback 실행

실행:

```text
psrctl conformance-public --endpoint http://127.0.0.1:8877/mcp
```

관찰:

```text
status: PASS
protocol: 2025-11-25
authentication_required: false
source_discovery: curated_seed
research_status: PARTIAL
tools: 3
resources/prompts: 0/0
citations/unique documents: 12/5
FACT citation coverage: 100%
RECOMMENDATION citation coverage: 100%
locator completeness: 100%
official primary document ratio: 80%
required track recall: 100%
purge_verified: true
feedback_token_present: true
feedback_submission_verified: false
reconnect_verified: true
```

result JSON에는 조사 질문, 검색어, citation ID·URL·excerpt, document hash, feedback token,
operation ID가 없었다. server output은 HTTP method/status와 MCP request type만 표시했고
질문·원문·결과·token은 표시하지 않았다. 종료 뒤 ephemeral root는 비어 있었다.

## 5. 자동 검증

추가 test:

- Public conformance URL, HTTPS와 timeout fail-closed
- CLI content-free PASS JSON과 redacted failure
- 실제 TCP에서 anonymous policy→quick→feedback opt-in→reconnect
- fixture transport PASS와 default release gate 거부
- result summary에 질문과 raw feedback token 0건

전체 회귀:

```text
490 passed (465 non-PostgreSQL + 25 PostgreSQL)
```

Coverage:

```text
raw total: 95.13%
normalized statement: 96.24%
branch: 90.75%
critical module statement minimum: 95.0%
status: pass
```

정적·공급망 검증:

```text
ruff: pass
format: pass
strict mypy: pass (149 source files)
dependency license manifest: current
```

실제 TCP reconnect, TLS terminating reverse proxy와 PostgreSQL RLS 회귀를 포함했다.

## 6. 남은 외부 gate

- 공개 CA 또는 기관 CA의 실제 HTTPS endpoint
- gateway의 canonical client IP overwrite와 spoof rehearsal
- gateway/WAF request·response body logging 비활성 canary scan
- Codex와 두 번째 목표 MCP Host의 anonymous quick
- edge/shared quota와 provider billing hard cap
- staging purge failure·rollback·runtime pause rehearsal

따라서 이 판정은 official SDK application contract 통과이며 Public Preview 배포 승인이나
목표 Host 호환성 완료를 뜻하지 않는다.
