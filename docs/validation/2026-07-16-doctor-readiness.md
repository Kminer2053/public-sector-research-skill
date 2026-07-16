# Public Doctor Readiness Gate 검증

> 기준일: 2026-07-16 · 판정: **Local Configuration Gate PASS / External Deployment Gates Pending**

[Architecture](../ARCHITECTURE.md) · [PRD](../PRD.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 목적

설정 문법만 유효한 상태를 “공개 준비 완료”로 오인하지 않도록, 운영자가 로컬 smoke 가능 여부와
production 공개 설정 준비 여부를 구분해 확인하고 CI/pre-deploy에서 미달을 차단할 수 있게 한다.

## 2. 구현한 판정

`psrctl doctor --json`은 다음을 redacted JSON으로 출력한다.

- `local_smoke_ready`: fixture를 포함한 로컬 lifecycle smoke 최소조건
- `public_deployment_config_ready`: production source mode, restricted ephemeral root,
  실제 secret 존재, trusted proxy, daily quick budget과 runtime pause control 준비 여부
- `accepting_new_research`: config가 실행 가능하고 static/runtime pause가 열려 있는지
- check별 `pass`, `warn`, `fail`과 content-free 설명
- 로컬 설정으로 승인할 수 없는 `external_gates_pending`

`psrctl doctor --json --require-public-ready`는 공개 설정 준비 시 exit 0, 미달 시 exit 5다.
server, workspace와 network를 시작하지 않는 read-only 검사다.

## 3. 자동 검증

| 조건 | 기대값 | 결과 |
|---|---|---|
| development fixture | local smoke true, public config false | PASS |
| backend disabled | source discovery fail | PASS |
| curated production complete config | public config true | PASS |
| Brave Search key 누락·공백 | search secret fail | PASS |
| abuse HMAC secret 누락·짧음 | abuse secret fail | PASS |
| ephemeral root missing in development | warn | PASS |
| ephemeral root missing in production | fail | PASS |
| ephemeral root file·symlink·0755·stat error | fail | PASS |
| pause parent missing·file·group/world writable | fail | PASS |
| runtime pause active | config true 유지, accepting false | PASS |
| `--require-public-ready` 미달 | exit 5 | PASS |
| complete production config | exit 0 | PASS |
| doctor output secret canary | 0건 | PASS |
| Foundation doctor | public readiness `null` | PASS |

전체 회귀:

```text
455 passed (430 non-PostgreSQL + 25 PostgreSQL)
```

Coverage:

```text
raw total: 95.25%
normalized statement: 96.31%
branch: 91.09%
critical module statement minimum: 95.0%
public readiness module statement/branch: 100% / 100%
status: pass
```

정적 검증:

```text
ruff: pass
format: pass
strict mypy: pass (144 source files)
```

## 4. 판정의 한계

`public_deployment_config_ready=true`는 application과 operator local configuration이
준비됐다는 뜻이다. 다음 항목은 의도적으로 자동 승인하지 않고
`external_gates_pending`에 남긴다.

- 실제 gateway의 client-IP overwrite와 spoof rehearsal
- multi-replica shared quota와 Search provider billing hard cap
- staging retention canary, purge failure game day와 rollback
- 지원 Host 연결 smoke
- 실제 사용자의 helpful과 save-feature-interest 검증

따라서 doctor exit 0만으로 PG3 또는 Public Preview 공개 승인을 선언할 수 없다.
