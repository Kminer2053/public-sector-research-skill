# Process Daily Quick Budget 검증

> 기준일: 2026-07-16 · 판정: **Application Local PASS / Shared Cost Cap Pending**

[Architecture](../ARCHITECTURE.md) · [PRD](../PRD.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 목적

가입 없는 공개 MCP가 예상보다 많이 호출될 때 한 application process가 하루 동안 무제한으로
새 조사와 외부 provider 비용을 시작하지 않도록 보수적인 진입 상한을 둔다.

## 2. 구현한 경계

- `PSR_PUBLIC_DAILY_QUICK_BUDGET`으로 process·UTC 일자별 quick 진입 횟수를 제한한다.
- development의 0은 비활성화이며 production public mode는 1 이상의 명시값 없이는 startup에
  실패한다.
- profile과 Planner 입력 검증 뒤, ephemeral workspace와 외부 source network 전에 1회를
  원자적으로 차감한다.
- 잘못된 입력과 active quick 상한 초과 요청은 차감하지 않는다.
- backend가 시작된 뒤의 성공, 오류와 취소는 실제 비용 가능성이 있으므로 차감한다.
- 소진 시 retryable `PUBLIC_DAILY_BUDGET_EXHAUSTED`를 반환한다.
- 다음 UTC 날짜가 관찰되면 counter를 reset한다.
- 소진 상태에서 `psr.service.policy.research_available=false`가 되고 실제
  `limits.daily_quick_budget`을 공개한다.

## 3. 자동 검증

| 조건 | 기대값 | 결과 |
|---|---|---|
| production public + budget 미설정 | startup 실패 | PASS |
| 허용범위 | 0..1,000,000 | PASS |
| 잘못된 질문 | budget 미차감 | PASS |
| active quick 초과 | budget 미차감 | PASS |
| 성공한 quick | 1회 차감 | PASS |
| backend 오류가 난 시작된 quick | 1회 차감 | PASS |
| budget 소진 뒤 호출 | workspace 생성 전 typed error | PASS |
| budget 소진 뒤 service policy | `research_available=false` | PASS |
| UTC 날짜 변경 | counter reset, 다음 quick 성공 | PASS |
| 모든 성공·실패 경로 | ephemeral content 0건 | PASS |

전체 회귀:

```text
434 passed (409 non-PostgreSQL + 25 PostgreSQL)
```

Coverage:

```text
raw total: 95.10%
normalized statement: 96.19%
branch: 90.79%
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

이 budget은 공개 전 안전 하한이며 정확한 금액 기반 cost accounting이 아니다. quick 하나가
curated mode와 live Search mode에서 만드는 비용이 다르고, process restart 또는 replica 수에
따라 process-local counter 합계가 달라질 수 있다. 따라서 production에서는 초기값을 명시하되
provider dashboard의 hard cap, gateway/shared limiter와 비용 알림을 함께 사용해야 한다.

## 5. 남은 검증

- 실제 live Search credential로 quick당 query 수와 비용 분포 측정
- multi-replica 공유 daily/hourly budget backend
- process restart 뒤 counter 연속성 또는 gateway 기준 상한
- provider hard cap 도달 시 typed partial/fail-closed 동작
- operator runtime pause와 5분 내 kill switch rehearsal
- 부하·비용 관찰 뒤 production 초기값 확정

따라서 이 결과는 단일 process의 UTC 일일 진입 상한 통과이며, 실제 provider 청구액이나
배포 전체 비용 상한 통과를 의미하지 않는다.
