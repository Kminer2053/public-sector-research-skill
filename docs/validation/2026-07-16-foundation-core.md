# Foundation Core 검증 보고서 — 2026-07-16

> 대상: `D0`, `F0`, `F1` · 환경: macOS, Python 3.12.13, uv 0.11.14, `mcp==1.28.1`

> 이 환경 표기는 당시 실행 증적이다. 후속 공급망 감사에서 `uv 0.11.14`의
> `GHSA-4gg8-gxpx-9rph`를 확인해 현재 builder와 CI는 patched `uv 0.11.15`로 교체했다.
> [후속 검증](./2026-07-16-direct-gateway-and-build-reproducibility.md)을 따른다.

> 후속 상태: 이 보고서는 G0~G2 시점의 증적이다. 이후 [PostgreSQL G3](./2026-07-16-postgresql-g3.md), [OAuth G4](./2026-07-16-oauth-g4.md), [Remote G5](./2026-07-16-remote-g5.md)가 각각 통과했다.

[검증 기준](../VALIDATION_CRITERIA.md) · [구현 계획](../IMPLEMENTATION_PLAN.md) · [상세설계](../DETAILED_DESIGN.md)

## 1. 결론

Foundation Core와 MCP contract가 in-memory 환경에서 검증됐다. 아래 G3 상태는 이 보고서 작성시점의 결과이며 후속 PostgreSQL 보고서에서 갱신됐다.

| Gate | 결과 | 근거 | 제한 |
|---|---|---|---|
| G0 Buildable | PASS | locked sync, lint, format, strict mypy, test, wheel/sdist build | CI 원격 실행은 첫 PR에서 확인 |
| G1 Domain Safe | PASS | tenant negative, state, idempotency, rollback, lease test | PostgreSQL concurrency/RLS는 G3 |
| G2 MCP Contract | PASS | 공식 SDK in-memory session과 loopback Streamable HTTP smoke | Host 2종/TLS는 G5 |
| G3 PostgreSQL Durable | NOT VERIFIED | migration 초안의 구조 test만 존재 | 실제 DB adapter·RLS·recovery 없음 |
| G4 OAuth Secure | NOT VERIFIED | production fail-closed guard만 존재 | TokenVerifier·Membership resolution 없음 |
| G5 Remote Compatible | NOT VERIFIED | loopback Python SDK client만 확인 | TLS 및 목표 Host 2종 미확인 |
| G6 Foundation Exit | NOT MET | G3~G5가 열려 있음 | production-ready 선언 금지 |

## 2. 재현 명령과 결과

작업 디렉터리의 clean checkout에서 아래 명령을 실행한다.

```bash
uv sync --all-groups --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src tests scripts
uv run --frozen pytest --cov=psr_mcp --cov-branch --cov-report=term-missing
uv run --frozen psrctl doctor --json
uv build
```

2026-07-16 로컬 결과:

- dependency resolution: `mcp==1.28.1`, Python 3.12.13
- Ruff lint/format: PASS
- mypy strict: PASS
- pytest: 62 tests PASS
- combined line+branch coverage: 93.38%
- wheel/sdist: PASS; wheel에 `storage/migrations/0001_foundation.sql` 포함
- doctor: development static auth와 memory storage를 표시하고 미검증 항목을 명시

실제 HTTP 경로는 server와 client를 별도 process로 실행해 확인한다.

```bash
uv run --frozen psrctl serve mcp
uv run --frozen python scripts/http_smoke.py
```

기대 결과는 endpoint `http://127.0.0.1:8000/mcp`, seed Project, 5개 Tool 이름, 새 HTTP session에서 다시 조회한 Run ID를 포함하는 JSON 한 줄과 exit code 0이다. 이는 loopback transport smoke이며 F4의 two-host conformance를 대체하지 않는다.

## 3. 검증된 핵심 행위

- Organization A의 actor는 Organization B의 Project/Run을 조회할 수 없다.
- Project restriction이 있는 actor는 허용된 Project만 목록과 상세에서 볼 수 있다.
- 미존재와 권한 없음은 동일한 `NOT_FOUND_OR_FORBIDDEN` 응답으로 외부에 노출된다.
- 동일 idempotency key와 동일 approved Plan은 같은 Run을 반환한다.
- 같은 key를 다른 Plan에 사용하면 `IDEMPOTENCY_CONFLICT`가 발생한다.
- Run·Job·Audit 중 audit write가 실패하면 in-memory transaction 전체가 rollback된다.
- worker lease는 owner와 expiry를 검사하며 expired lease를 다른 worker가 reclaim할 수 있다.
- unexpected exception은 MCP 응답에서 내부 상세를 제거한다.
- canonical Tool catalog가 바뀌면 reviewed digest test가 실패한다.
- malformed JSON body는 JSON-RPC parse error로 응답한다.
- HTTP session을 종료하고 다시 연결해도 explicit Run ID로 상태를 조회할 수 있다.
- production 설정은 OAuth와 PostgreSQL이 아니면 process start 전에 거부된다.

## 4. 아직 증명하지 않은 사항

- migration이 지원 PostgreSQL version에서 실제 적용·rollback 가능한지
- RLS가 connection pool reuse와 transaction boundary에서도 tenant를 격리하는지
- `SKIP LOCKED` 기반 여러 worker의 실제 claim 경쟁과 crash recovery
- OIDC issuer, audience, expiry, scope, JWKS rotation 검증
- reverse proxy/TLS 아래 protected resource metadata와 challenge
- Codex 계열 Host와 추가 MCP Host의 원격 상호운용성
- collector의 robots.txt, 이용약관, 개인정보, 저작권 정책 집행

## 5. 다음 검증 진입 조건

G3 착수 전 다음을 완료한다.

1. ADR-0005로 PostgreSQL driver와 migration 도구를 선택한다.
2. CI service container 또는 전용 test DB의 지원 version을 고정한다.
3. least-privilege owner/runtime role을 분리한다.
4. memory/PostgreSQL 공통 port contract suite를 만든다.
5. RLS tenant matrix와 worker concurrency test를 먼저 red 상태로 추가한다.

이 조건을 충족하기 전 migration SQL 존재만으로 F2 완료 또는 데이터 내구성을 주장하지 않는다.
