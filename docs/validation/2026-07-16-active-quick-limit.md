# Process Active Quick Limit 검증

> 기준일: 2026-07-16 · 판정: **Application Local PASS / Multi-Replica Limit Pending**

[Architecture](../ARCHITECTURE.md) · [PRD](../PRD.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 목적

서로 다른 IP의 익명 사용자가 동시에 `psr.research.quick`을 호출하더라도 한 application
process가 제한 없이 조사, 임시 파일과 외부 source 연결을 만들지 않도록 한다.

## 2. 구현한 경계

- `PSR_PUBLIC_MAX_ACTIVE_QUICK`으로 process당 동시 quick 상한을 설정한다.
- 기본값은 8, 허용범위는 1..100이며 범위 밖 설정은 startup 전에 실패한다.
- slot은 profile 확인 뒤, Planner·workspace·외부 network보다 먼저 확보한다.
- 상한에 도달한 요청은 retryable `PUBLIC_LIMIT_REACHED`로 거부한다.
- 거부된 요청은 ephemeral workspace를 만들거나 `ResearchBackend`를 호출하지 않는다.
- 성공, backend 오류와 task 취소의 `finally` 경로에서 slot을 반환한다.
- `psr.service.policy.limits.max_active_quick`은 실제 설정값을 공개한다.

## 3. 자동 검증

| 조건 | 기대값 | 결과 |
|---|---|---|
| 상한 1에서 첫 quick 실행 중 두 번째 호출 | `PUBLIC_LIMIT_REACHED` | PASS |
| 상한 초과 요청의 workspace 수 | 증가하지 않음 | PASS |
| 첫 quick 완료 뒤 다음 호출 | 성공 | PASS |
| backend 오류 뒤 다음 호출 | 성공 | PASS |
| task 취소 뒤 다음 호출 | 성공 | PASS |
| 성공·오류·취소 뒤 ephemeral root | content 0건 | PASS |
| 기본 설정 | 8 | PASS |
| 0 또는 101 설정 | startup validation 실패 | PASS |
| `service.policy` | `max_active_quick=8` | PASS |

전체 회귀:

```text
428 passed (403 non-PostgreSQL + 25 PostgreSQL)
```

Coverage:

```text
raw total: 95.05%
normalized statement: 96.15%
branch: 90.69%
critical module statement minimum: 95.0%
status: pass
```

정적 검증:

```text
ruff: pass
format: pass
strict mypy: pass (140 source files)
```

## 4. 운영 의미

이 제한은 비싼 조사가 시작되는 수를 제한하는 application 안전망이다. IP별 rate limit과
Search·Collector 내부 동시성 제한을 대체하지 않고 함께 적용한다. 상한에 도달했을 때 요청을
대기열에 오래 보관하지 않고 즉시 retryable error로 반환하므로 익명 요청 content가 서버
메모리나 workspace에서 대기하지 않는다.

## 5. 남은 검증

- 이 counter는 process-local이다. 여러 replica의 합계 상한은 gateway 또는 공유 limiter
  backend에서 별도로 구현해야 한다.
- 실제 부하에서 기본값 8의 CPU, 메모리, file descriptor와 외부 provider 비용을 측정해야 한다.
- HTTP 429와 `Retry-After`의 edge 계약은 gateway rehearsal에서 검증해야 한다.
- 일·시간 비용 budget과 자동 kill switch는 별도 작업이다.

따라서 이 결과는 단일 application process의 active quick 경계 통과이며, Public Preview
배포 전체 승인이나 multi-replica global quota 통과를 의미하지 않는다.
