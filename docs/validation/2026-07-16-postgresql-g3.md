# PostgreSQL G3 검증 보고서 — 2026-07-16

> 대상: F2 PostgreSQL Durability · 환경: PostgreSQL 17.10, Psycopg 3.3.4, Psycopg Pool 3.3.1, Alembic 1.18.5

[검증 기준](../VALIDATION_CRITERIA.md) · [구현 계획](../IMPLEMENTATION_PLAN.md) · [PostgreSQL Runbook](../runbooks/postgresql.md) · [ADR-0005](../adr/0005-postgresql-persistence-stack.md)

## 1. 판정

`G3 Durable`은 PostgreSQL 17.10 로컬 실증에서 PASS다. CI의 PostgreSQL service 검증은 feature branch PR에서 동일 명령으로 재실행해야 한다. PostgreSQL 18 compatibility와 기관 managed database restore drill은 release gate에서 추가한다.

이 판정은 OAuth, 실제 원격 Host, 수집·Evidence 기능을 포함하지 않는다. 따라서 G4~G6과 production-ready 상태는 여전히 열려 있다.

## 2. 구현 결과

- Psycopg async pool과 명시적 SQL repository
- first-use transaction tenant binding과 same-UoW tenant switch 거부
- `SET LOCAL`과 동등한 `set_config(..., true)`
- Project/Plan/Run/Job/Audit repository와 domain mapper
- optimistic Run update
- idempotency advisory lock와 unique constraint
- `FOR UPDATE SKIP LOCKED` claim
- Alembic upgrade/downgrade와 operator CLI
- least-privilege runtime role 검증
- PostgreSQL 17 CI service와 test database bootstrap

## 3. 자동 검증

실제 DB suite는 다음 환경변수를 요구한다.

```bash
export PSR_TEST_ADMIN_DATABASE_URL='<admin test URL>'
export PSR_TEST_OWNER_DATABASE_URL='<owner test URL>'
export PSR_TEST_RUNTIME_DATABASE_URL='<runtime test URL>'
export PSR_TEST_RUNTIME_ROLE='<runtime role>'
pytest tests/postgres -q
```

로컬 결과: PostgreSQL test 15개 PASS.

검증 항목:

- no tenant context default deny
- Org A/B row isolation과 pool reuse
- transaction 종료 후 tenant setting 제거
- runtime `NOSUPERUSER NOBYPASSRLS`
- 8개 table RLS enabled+forced
- composite FK cross-tenant insert 거부
- Run/Job/Audit idempotent 생성과 재호출
- 동시 같은 요청이 같은 Run ID 반환
- 두 worker 중 한 worker만 claim과 deterministic queue order
- lease expiry/reclaim과 pool restart 후 attempts 유지
- retry exhaustion persistence
- optimistic cancel race와 cancel/complete race의 Run·Job 일치
- AuditEvent insert 실패 시 Run·Job rollback
- backend 강제 종료 전 미커밋 Run 부재와 pool 회복
- commit 후 response loss를 새 pool에서 idempotent replay

## 4. Migration과 Restore

실제 PostgreSQL에서 다음 순서를 검증했다.

```text
fresh upgrade → 0001_foundation
downgrade base → application table 0
upgrade head → 0001_foundation
custom-format backup → isolated database restore
```

| 항목 | 원본 | 복원 |
|---|---:|---:|
| Alembic revision | `0001_foundation` | `0001_foundation` |
| Organization | 2 | 2 |
| Project | 3 | 3 |
| ResearchRun | 1 | 1 |
| Job | 1 | 1 |
| AuditEvent | 4 | 4 |
| 8개 tenant table RLS forced | true | true |

## 5. 발견사항

1. `FORCE ROW LEVEL SECURITY`는 table owner의 전체 logical dump도 차단한다.
2. 전체 backup은 runtime/owner credential이 아닌 별도 제한 backup role 또는 managed snapshot이 필요하다.
3. idempotency unique constraint만 사용하면 실제 경합에서 한 요청이 conflict를 받을 수 있으므로 transaction advisory lock을 선행한다.
4. broken connection에서 UoW가 rollback 예외로 원래 commit 오류를 가리지 않도록 pool context에 원래 exception을 전달해야 한다.

## 6. 남은 release 검증

- GitHub Actions PostgreSQL service에서 동일 suite 통과
- PostgreSQL 18 compatibility matrix
- 기관 managed database의 snapshot encryption·retention·restore drill
- 실제 production secret resolver와 pool lifecycle composition
- 운영 부하에서 queue wait, lock wait, pool saturation 측정

이 항목은 G3의 local implementation 판정을 무효화하지 않지만 G6 production readiness 전에 닫아야 한다.
