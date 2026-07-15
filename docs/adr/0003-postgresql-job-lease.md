# ADR-0003: PostgreSQL-backed Job Lease

- Status: Accepted with implementation spike
- Date: 2026-07-16

## Context

ResearchRun은 HTTP request보다 오래 실행되며 부분실패와 worker crash를 견뎌야 한다. MCP Tasks는 current protocol에서 실험 기능이므로 core durability를 맡길 수 없다. MVP에서 별도 Redis/managed queue까지 도입하면 운영요소가 늘어난다.

## Decision

1. ResearchRun은 application entity이고 MCP session과 독립한다.
2. MVP queue는 PostgreSQL `jobs` table을 사용한다.
3. claim은 transaction, `FOR UPDATE SKIP LOCKED`, lease owner/expiry로 구현한다.
4. Run mutation, Job mutation, AuditEvent는 한 transaction으로 묶는다.
5. idempotency unique constraint가 중복 Run을 방지한다.
6. worker는 heartbeat하고 cooperative cancellation을 확인한다.
7. queue port를 분리해 scale trigger 발생 시 backend를 교체한다.

## Consequences

- 초기 운영요소와 transaction gap이 줄어든다.
- queue load가 primary DB와 경쟁할 수 있으므로 queue wait/lock metric이 필요하다.
- 장시간 side effect는 step idempotency가 필요하다.
- DB unavailable 시 start는 성공한 것처럼 응답하지 않는다.

## Scale trigger

- 4주 연속 P95 queue wait SLO 초과
- queue lock/maintenance가 DB CPU/lock wait의 주요 원인
- worker 50개 이상 또는 workload class 분리 필요
- managed queue가 복구·운영 복잡도를 실질적으로 낮춤

## Validation

- duplicate start race
- two-worker exclusive claim
- lease expiry/reclaim
- cancellation/completion race
- worker crash recovery
- max-attempt exhaustion
- Run/Job/Audit atomicity
