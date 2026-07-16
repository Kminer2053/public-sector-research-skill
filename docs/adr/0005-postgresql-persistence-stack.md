# ADR-0005: PostgreSQL Persistence Stack

- Status: Accepted
- Date: 2026-07-16
- Decision owners: Architecture, Security

## Context

Foundation Core의 domain과 repository port는 storage framework에 독립적이다. F2에서는 다음을 동시에 만족해야 한다.

- transaction마다 tenant context를 설정하고 pool 재사용 시 누출하지 않는다.
- `FOR UPDATE SKIP LOCKED`, optimistic update, idempotency unique race를 명시적으로 제어한다.
- domain object를 ORM persistence model로 사용하지 않는다.
- schema upgrade와 downgrade를 검토 가능한 표준 migration 도구로 관리한다.
- 운영 의존성과 추상화 계층을 불필요하게 늘리지 않는다.

검토한 선택지는 SQLAlchemy 2 async ORM/Core와 Psycopg 3 typed SQL이다.

## Decision

1. 지원 기준 DB는 PostgreSQL 17이며 PostgreSQL 18 호환성을 CI matrix에서 추가한다.
2. 운영 runtime adapter는 `psycopg 3`와 `psycopg_pool.AsyncConnectionPool`을 사용한다.
3. query는 parameterized SQL로 명시하고 `dict_row`를 domain mapper로 변환한다.
4. SQLAlchemy ORM/Core는 runtime query path에 사용하지 않는다.
5. Alembic은 migration control plane에만 사용한다. Alembic이 요구하는 SQLAlchemy는 application runtime repository에서 import하지 않는다.
6. pool은 `open=False`로 만들고 application lifecycle에서 명시적으로 `open()`, `wait()`, `close()`한다.
7. PostgreSQL UnitOfWork는 connection을 checkout한 뒤 첫 repository 호출에서 organization을 한 번만 bind한다.
8. bind는 transaction 안에서 `SELECT set_config('app.organization_id', $1, true)`와 동등한 parameterized query를 실행한다. 같은 UnitOfWork에서 다른 organization을 요구하면 SQL 실행 전에 거부한다.
9. UnitOfWork 종료 시 commit되지 않은 transaction을 rollback한 뒤 connection을 pool에 반환한다. pool reset callback도 non-idle transaction을 방어적으로 rollback한다.
10. migration role은 table owner이고 runtime role은 `NOSUPERUSER NOBYPASSRLS`이며 table을 소유하지 않는다.
11. application이 ID를 생성하므로 database sequence를 사용하지 않는다.

## Why not SQLAlchemy runtime

- 현재 aggregate와 query 수가 작고 SQL이 PostgreSQL 기능에 강하게 의존한다.
- RLS context, `SKIP LOCKED`, conditional update의 실제 SQL을 security review에서 바로 확인할 수 있다.
- 별도 ORM model과 domain mapping을 동시에 유지하는 비용을 피한다.
- storage port가 이미 framework boundary를 제공하므로 ORM 교체 가능성이 핵심 요구가 아니다.

SQLAlchemy를 전면 금지하는 결정은 아니다. Evidence 검색처럼 query composition 복잡도가 크게 증가하면 별도 ADR로 Core 사용을 재검토한다.

## Consequences

- SQL과 row mapper를 직접 테스트해야 한다.
- PostgreSQL 고유 동작을 숨기지 않으므로 다른 RDBMS로의 투명한 교체는 목표가 아니다.
- Alembic과 SQLAlchemy가 migration dependency로 설치되지만 Gateway query path에는 들어오지 않는다.
- pool lifecycle과 transaction 상태를 application bootstrap/runbook에서 명시적으로 관리해야 한다.

## Validation

- PostgreSQL 17 fresh upgrade와 downgrade/upgrade 재실행
- no-context default deny
- Org A→pool return→Org B 순서에서 row leakage 0
- transaction 이후 `current_setting('app.organization_id', true)`가 빈 값
- runtime role의 `rolsuper=false`, `rolbypassrls=false`
- memory/PostgreSQL repository contract parity
- 두 worker의 exclusive claim과 lease reclaim
- failed AuditEvent insert 시 Run과 Job rollback

## References

- [Psycopg transaction management](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Psycopg async pool](https://www.psycopg.org/psycopg3/docs/api/pool.html)
- [Alembic async cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html)
- [PostgreSQL 17 Row Security Policies](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)
- [PostgreSQL versioning policy](https://www.postgresql.org/support/versioning/)
