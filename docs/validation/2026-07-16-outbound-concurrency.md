# Shared Outbound Concurrency Validation

> 기준일: 2026-07-16 · 판정:
> **PROCESS-LOCAL GLOBAL/SOURCE-HOST CONCURRENCY PASS · DISTRIBUTED RATE PENDING**

[Architecture](../ARCHITECTURE.md) · [PRD](../PRD.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 목적

검색과 수집이 각각 별도 semaphore만 사용해 동시에 실행될 때 process 전체 외부요청 상한을
합산 보장하지 못하던 공백을 닫는다. 또한 한 source host의 느린 요청 대기열이 다른 공식기관
source가 사용할 global capacity를 독점하지 않게 한다.

## 2. 구현

- `OutboundConcurrencyLimiter`
- `PSR_OUTBOUND_MAX_CONCURRENCY`, 기본 8, 허용 1..32
- `PSR_SOURCE_HOST_MAX_CONCURRENCY`, 기본 2, 허용 1..8이면서 global 이하
- Brave Search와 `SafeCollector`에 같은 limiter instance 주입
- robots 확인과 원문 수집이 같은 `SafeCollector`를 사용
- redirect마다 검증된 target host로 capacity 재획득
- host gate 선획득 후 global gate 획득
- 성공·typed failure·timeout·task cancellation의 `finally`에서 slot 반환
- active/waiting borrower가 0이면 host gate 제거
- `psr.service.policy.limits`에 실제 두 설정값 공개

`PSR_SEARCH_MAX_CONCURRENCY`와 `PSR_COLLECTION_MAX_CONCURRENCY`는 단계별 작업 상한으로
유지한다. 새 limiter는 두 단계를 합친 실제 HTTP 요청의 process 상한이다.

## 3. 자동 검증

| 조건 | 기대 | 결과 |
|---|---|---|
| 서로 다른 여러 host | active outbound가 global 이하 | PASS |
| 같은 host 병렬 요청 | active가 source-host 이하 | PASS |
| 같은 host waiter + 다른 host | waiter가 global slot을 선점하지 않음 | PASS |
| 대기 task 취소 | slot 반환, host tracking 정리 | PASS |
| host 대소문자·trailing dot | 같은 host gate | PASS |
| invalid host·limit config | network 전 fail closed | PASS |
| SafeCollector redirect | start/final host 각각 재획득 | PASS |
| Brave Search | fixed provider host로 limiter 진입 | PASS |
| `service.policy` | 실제 기본값 8/2 공개 | PASS |

변경 직후 targeted regression:

```text
135 passed
ruff check: PASS
ruff format: PASS
mypy strict: PASS
git diff --check: PASS
```

최종 전체 회귀:

```text
PostgreSQL 17·OAuth·TCP/TLS 포함: 519 passed
raw coverage: 95.21%
normalized statement coverage: 96.30%
branch coverage: 90.94%
critical module statement minimum: 95.00%
OutboundConcurrencyLimiter statement/branch: 100% / 100%
ruff/format: PASS
mypy strict: PASS (156 files)
container/gateway static contract: PASS
dependency license manifest: PASS
Markdown links/fences: 48 files, missing/unbalanced 0
```

## 4. 보존·개인정보

- limiter key는 실행 중 정규화 hostname만 memory에 둔다.
- active/waiting 요청이 없어지면 해당 key를 즉시 제거한다.
- hostname, URL, 질문, 검색어를 log·DB·metric에 쓰는 기능을 추가하지 않았다.
- 공개하는 진단값은 host 이름이 아닌 현재 설정 상한뿐이다.

## 5. 남은 외부 게이트

이 change는 단일 process 동시성 안전망이다. 다음은 아직 PASS가 아니다.

- 시간당 source-host rate와 upstream circuit breaker
- 여러 replica를 합친 global/source quota
- Search provider dashboard billing hard cap
- 실제 느린 공공 source를 포함한 staging saturation
- gateway와 provider를 합친 비용·latency 측정

따라서 이 문서만으로 PG3 또는 Public Preview Ready를 선언하지 않는다.
