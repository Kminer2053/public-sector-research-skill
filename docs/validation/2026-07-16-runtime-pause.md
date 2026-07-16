# Operator Runtime Pause 검증

> 기준일: 2026-07-16 · 판정: **Application Local PASS / Deployment Rehearsal Pending**

[Architecture](../ARCHITECTURE.md) · [PRD](../PRD.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 목적

비용 급증, source 장애나 보안사고가 의심될 때 운영자가 application을 재시작하거나 공개 관리
Tool을 만들지 않고 새 고비용 조사만 즉시 중단할 수 있게 한다.

## 2. 구현한 경계

- `PSR_PUBLIC_PAUSE_FILE`은 operator control plane이 관리하는 절대경로다.
- application은 file content를 읽거나 쓰지 않고 `lstat` metadata만 확인한다.
- regular file, directory, symlink, broken symlink와 예상하지 못한 stat 오류는 모두
  fail-closed pause다.
- pause 상태는 `psr.service.policy.kill_switch_active=true`,
  `research_available=false`로 즉시 표시된다.
- 새 quick은 retryable `PUBLIC_SERVICE_PAUSED`로 workspace 생성 전에 거부된다.
- 이미 실행 중인 quick은 취소하지 않고 access block과 purge까지 계속한다.
- sentinel을 제거하면 server restart 없이 새 quick이 다시 허용된다.
- Public MCP catalog에는 pause를 생성·제거하는 관리 Tool이 없다.

## 3. 자동 검증

| 조건 | 기대값 | 결과 |
|---|---|---|
| pause path 없음 | open | PASS |
| regular file 존재 | paused | PASS |
| file 제거 | restart 없이 resume | PASS |
| broken symlink | fail-closed paused | PASS |
| `lstat` PermissionError | fail-closed paused | PASS |
| 진행 중 quick 도중 pause | 기존 quick 완료·purge | PASS |
| pause 중 새 quick | workspace 추가 없이 typed error | PASS |
| service policy | pause 상태 즉시 반영 | PASS |
| resumed quick | 성공 후 ephemeral content 0건 | PASS |

전체 회귀:

```text
441 passed (416 non-PostgreSQL + 25 PostgreSQL)
```

Coverage:

```text
raw total: 95.12%
normalized statement: 96.22%
branch: 90.80%
critical module statement minimum: 95.0%
status: pass
```

정적 검증:

```text
ruff: pass
format: pass
strict mypy: pass (142 source files)
```

## 4. 운영 계약

pause 경로는 application 사용자와 외부 요청이 쓸 수 없어야 한다. Kubernetes라면 control
plane 또는 제한된 sidecar가 관리하는 volume/file, 단일 host라면 operator 전용 runtime
directory를 사용한다. pause file에 사용자 질문, 결과나 운영 메모를 저장하지 않는다.

runtime pause는 static `PSR_PUBLIC_KILL_SWITCH`, daily quick budget과 별개로 함께 적용된다.
어느 하나라도 닫혀 있으면 새 quick을 시작하지 않는다.

## 5. 남은 검증

- 실제 배포 control plane에서 pause 생성부터 policy 반영까지 5분 이내 rehearsal
- origin replica 전체에 동일 signal이 전파되는지 확인
- pause 중 진행 중인 장기 async Run의 status/result/purge 유지 검증
- alert → pause → 원인 확인 → resume 운영 절차와 권한 분리
- control path 권한·mount 장애 시 fail-closed 동작 staging 확인

따라서 이 결과는 application의 동적 admission 경계 통과이며, 실제 배포 환경의 control plane
전파와 5분 운영 rehearsal 통과를 의미하지 않는다.
