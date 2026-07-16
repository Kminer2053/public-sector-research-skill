# PostgreSQL 운영 Runbook

> 적용 범위: Foundation F2 · 기준 버전: PostgreSQL 17 · 관련 결정: [ADR-0005](../adr/0005-postgresql-persistence-stack.md)

## 1. 역할 분리

| Role | 목적 | 필수 속성 | 금지 |
|---|---|---|---|
| deployment owner | Alembic migration, object ownership | `NOSUPERUSER`, object owner | Gateway 로그인 공유 |
| runtime | MCP Gateway와 worker query | `NOSUPERUSER NOBYPASSRLS`, table DML | object ownership, migration, backup |
| backup | 제한된 logical backup 또는 복구 agent | 별도 credential, 필요 시 승인된 `BYPASSRLS` | application traffic, 상시 공용 credential |
| platform admin | DB 생성·role 관리·긴급복구 | 플랫폼 정책에 따름 | 일상 application query |

`FORCE ROW LEVEL SECURITY` 때문에 deployment owner도 tenant context 없이 전체 table을 dump할 수 없다. 전체 logical backup이 필요하면 네트워크와 사용시간이 제한된 backup role 또는 관리형 database snapshot을 사용한다. backup role의 `BYPASSRLS`는 runtime role에 절대 부여하지 않는다.

## 2. 지원 기준

- Primary validation: PostgreSQL 17.10
- Runtime driver: Psycopg 3.3.x async pool
- Migration: Alembic 1.18.x
- Application timezone: UTC
- transaction-local tenant setting: `app.organization_id`

운영 major/minor version은 배포 manifest에 기록한다. PostgreSQL minor security update를 적용한 뒤 migration, RLS matrix, worker concurrency suite를 다시 실행한다.

## 3. Migration

database URL을 명령행에 쓰지 않는다. deployment secret injection으로 다음 환경변수에 제공한다.

```bash
export PSR_MIGRATION_DATABASE_URL='postgresql://<deployment-role>@<host>/<database>'
psrctl db current
psrctl db upgrade
```

단일 revision downgrade는 별도 change approval과 backup 이후에만 수행한다.

```bash
psrctl db downgrade --confirm-downgrade
```

운영에서는 destructive downgrade보다 forward-fix migration을 우선한다. downgrade가 data loss를 포함하면 명령을 사용하지 않고 restore 절차로 전환한다.

## 4. Runtime grant 확인

배포 후 platform-admin connection에서 role과 RLS를 검증한다. runtime role은 `rolsuper=false`, `rolbypassrls=false`여야 하며 8개 tenant table은 `relrowsecurity=true`, `relforcerowsecurity=true`여야 한다.

```sql
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname IN ('<deployment-role>', '<runtime-role>', '<backup-role>');

SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relname IN (
  'organizations', 'memberships', 'projects', 'membership_projects',
  'research_plans', 'research_runs', 'jobs', 'audit_events'
)
ORDER BY relname;
```

## 5. Logical backup

관리형 snapshot이 조직의 RPO/RTO와 암호화·보존정책을 만족하면 이를 우선한다. logical backup이 필요하면 승인된 backup role로 custom format을 생성한다.

```bash
pg_dump --format=custom --file=<restricted-path>/psr-<timestamp>.dump <database>
```

backup manifest에는 다음을 기록한다.

- PostgreSQL server version과 Alembic revision
- 생성시각과 담당 operation ID
- dump SHA-256와 byte size
- 암호화 key reference와 보존기한
- tenant table별 row count 또는 승인된 대체 검증값
- restore 검증일과 결과

manifest와 dump에는 raw credential을 기록하지 않는다. row count도 기관 정책상 민감할 수 있으므로 restricted artifact로 분류한다.

## 6. Restore drill

1. 운영 traffic과 분리된 새 database를 만든다.
2. target role과 extension/version을 source manifest에 맞춘다.
3. custom dump를 `pg_restore --no-owner --role=<deployment-owner>`로 복원한다.
4. Alembic revision과 핵심 row count를 source manifest와 비교한다.
5. 8개 tenant table의 RLS enable/force flag를 확인한다.
6. runtime role로 no-context row 0, Org A/B 격리, pool A→B 재사용 test를 수행한다.
7. audit trigger가 UPDATE/DELETE를 거부하는지 확인한다.
8. 결과를 versioned validation report로 남기고 test database를 폐기한다.

## 7. 장애 복구

- commit 전 connection loss: 요청은 실패하고 transaction row가 없어야 한다.
- commit 후 response loss: 같은 idempotency key로 재호출해 기존 Run을 반환한다.
- worker loss: lease expiry 후 다른 worker가 reclaim한다.
- max attempts: Run과 Job을 `FAILED/RETRY_EXHAUSTED`로 원자적으로 변경한다.
- pool reset: transaction-local tenant setting이 남지 않아야 한다.

DB 장애를 성공 응답으로 숨기지 않는다. Gateway는 `DEPENDENCY_UNAVAILABLE`과 operation ID를 반환하고 연결 문자열·SQL·기관 ID를 사용자 오류에 포함하지 않는다.

## 8. 2026-07-16 로컬 복원 증적

PostgreSQL 17.10 임시 cluster에서 다음을 확인했다.

```text
source:   0001_foundation | organizations=2 | projects=3 | runs=1 | jobs=1 | audits=4
restored: 0001_foundation | organizations=2 | projects=3 | runs=1 | jobs=1 | audits=4
restored RLS enabled+forced across 8 tenant tables: true
```

이 증적은 개발환경 검증이며 기관별 운영 RPO/RTO 승인이나 managed database 복구시험을 대체하지 않는다.
