# Ephemeral Purge Retry 검증 보고서

> 기준일: 2026-07-16 · 판정:
> **QUICK LOCAL RETRY/BACKOFF/CONTENT-FREE ALERT PASS · STAGING GAME DAY PENDING**

[Architecture](../ARCHITECTURE.md) · [Implementation Plan](../IMPLEMENTATION_PLAN.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 목적

quick 결과 삭제가 일시적으로 실패했을 때 content가 다시 노출되거나 정상 TTL까지 방치되는
공백을 닫는다. 한 workspace의 실패 때문에 같은 scan의 다른 만료 workspace가 남는 문제도
함께 방지한다.

## 2. 확인한 기존 공백

- quick service는 삭제 전 access block을 수행하고 `finally`에서 한 번 더 purge했지만, 두 번
  모두 실패하면 workspace가 정상 expiry까지 sweep 대상이 아닐 수 있었다.
- filesystem scan은 한 삭제의 예외가 전체 batch를 중단시켰다.
- sweeper는 정규 주기마다 다시 실행됐지만 exponential retry state와 alert threshold가 없었다.
- 예외 traceback을 남기는 log는 exception message에 운영경로나 content가 섞일 가능성을
  완전히 배제하지 못했다.

## 3. 구현

- `purge.marker`가 있는 workspace는 expiry 전이라도 즉시 purge 후보로 처리
- 삭제 시도 전 access block을 idempotent하게 보장
- `PurgeBatchError(failure_count, successful_results)`로 부분성공 보존
- 실패 workspace ID와 원본 exception message는 aggregate error에 포함하지 않음
- 연속 실패 retry: 1→2→4초, 최대 정규 sweep 주기
- 3회 연속 실패부터 `ephemeral_purge_alert`
- 성공 회복 시 `ephemeral_purge_recovered`
- structured log allowlist:
  - `purge_failure_count`
  - `purge_consecutive_failures`
  - `purge_retry_seconds`
  - `purge_alert_active`
  - `purge_duration_bucket`

## 4. 자동 검증

| 조건 | 기대 | 결과 |
|---|---|---|
| unexpired + blocked marker | 다음 scan에서 즉시 삭제 | PASS |
| 두 workspace 중 한 삭제 실패 | 다른 workspace 삭제 성공 보존 | PASS |
| transient permission failure | marker로 read 차단 후 다음 scan 삭제 | PASS |
| 일반 sweep failure | 1→2→4초 backoff | PASS |
| 연속 3회 실패 | content-free alert 활성화 | PASS |
| 이후 성공 | 정규 60초 주기 복귀, recovered event | PASS |
| exception type/message에 canary/path | log 미포함 | PASS |
| successful result의 workspace ID | log 미포함 | PASS |
| startup/stop | 기존 startup/final sweep 유지 | PASS |

Targeted:

```text
ephemeral coverage suite: 18 passed
ephemeral combined coverage: 97.01%
PurgeSweeper statement/branch: 100% / 100%
PurgeBatchError statement/branch: 100% / 100%

public lifecycle/config/MCP regression: 116 passed
ruff check/format: PASS
mypy strict: PASS
```

전체 회귀:

```text
PostgreSQL 17·OAuth·TCP/TLS 포함: 535 passed
raw coverage: 95.31%
normalized statement coverage: 96.38%
branch coverage: 91.19%
critical module statement minimum: 95.00%
ruff/format: PASS
mypy strict: PASS (156 files)
```

## 5. 보존·개인정보

- retry state는 process memory의 실패 횟수와 delay뿐이며 workspace 식별자를 보유하지 않는다.
- failure log에는 질문, 검색어, URL, 원문, 결과, workspace ID/path, exception type/message가 없다.
- 삭제 성공 목록은 내부 batch 결과로만 전달되며 log에는 count만 남긴다.
- 재시도 중 content는 `purge.marker` 때문에 application read/write가 불가능하다.

## 6. 남은 외부 게이트

- 실제 container volume에서 permission/mount/disk 장애를 주입하는 staging game day
- 운영 log pipeline이 allowlist 외 field와 traceback을 추가하지 않는지 확인
- alert routing과 당직 대응시간 검증
- 향후 async 상태별 delivered/undelivered/failed TTL과 동일 정책 통합
- multi-replica에서 한 replica 장애·재시작 뒤 orphan 회수 검증

따라서 quick의 local `VAL-PUB-RET-007~009`, `014`는 PASS지만, 이 문서만으로 Public Preview
배포 승인이나 PG3 통과를 선언하지 않는다.
