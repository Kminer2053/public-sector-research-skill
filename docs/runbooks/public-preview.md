# Public Preview 실행 Runbook

> 대상: `PUBLIC_EPHEMERAL` · 기준일: 2026-07-16 · 상태: 로컬 개발/실증용

[README](../../README.md) · [Architecture](../ARCHITECTURE.md) ·
[Validation](../VALIDATION_CRITERIA.md) ·
[PG1 보고서](../validation/2026-07-16-pg1-useful-research.md)

## 1. 운영 원칙

- 공개 사용에는 로그인과 PostgreSQL content 저장을 요구하지 않는다.
- 질문·검색어·원문·추출문·결과는 memory 또는 제한된 임시 workspace에서만 처리한다.
- quick 결과를 만들기 전에 workspace 접근을 차단하고 purge가 확인된 경우에만 응답한다.
- source discovery는 기본적으로 꺼져 있다. 미구성 시 `research_available=false`다.
- 개발 fixture와 curated/live Search discovery는 동시에 켤 수 없다.
- `ACCOUNT_OPT_IN`, `PAID_PERSISTENT`, `ENTERPRISE`는 아직 startup에서 fail closed한다.

## 2. 개발 fixture 실행

외부 검색·수집 없이 MCP 계약과 purge lifecycle을 확인한다.

```bash
export PSR_SERVICE_MODE=public_ephemeral
export PSR_EPHEMERAL_ROOT=/tmp/psr-public-preview
export PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED=true
uv run --frozen psr-mcp
```

개발 fixture는 `TEST_FIXTURE` tier와 0점 Evidence Score를 사용하며 외부 사실 근거가 아니다.
production에서는 fixture 설정이 있으면 startup이 실패한다.

## 3. API key 없는 curated source 실행

초기 효용검증은 한국 공공부문 AI 조달 질문에 한정된 reviewed source catalog로 수행할 수 있다.
실시간 검색이 아니며, 지원 범위를 벗어난 질문은 관련 없는 source를 반환하지 않는다.

```bash
export PSR_SERVICE_MODE=public_ephemeral
export PSR_EPHEMERAL_ROOT=/tmp/psr-public-preview
export PSR_SEARCH_PROVIDER=curated
uv run --frozen psr-mcp
```

정책과 결과에서 다음 값을 확인한다.

```text
service.policy.source_discovery = curated_seed
research.quick.scope.source_discovery = curated_seed
```

실제 고정 질문, 원문 수집, citation track, 즉시 purge를 한 번에 점검한다.

```bash
uv run --frozen python scripts/live_curated_smoke.py
```

2026-07-16 관찰값은 7개 track, 12개 citation, failure 0, curated limitation gap 1,
`PURGED`, ephemeral directory empty였다. 이 수치는 source 변경에 따라 달라질 수 있으므로
release 전 다시 실행한다.

## 4. 실제 Search adapter 실행

현재 제공되는 production adapter는 선택형 Brave Search API다. Search 결과는 URL 후보일 뿐
Evidence가 아니다. 원문은 별도로 `SafeCollector`가 수집하고 parser와 Evidence Composer를
통과해야 citation이 된다.

```bash
export PSR_ENV=production
export PSR_SERVICE_MODE=public_ephemeral
export PSR_HOST=0.0.0.0
export PSR_PORT=8000
export PSR_PUBLIC_URL=https://research.example.org
export PSR_RESOURCE_SERVER_URL=https://research.example.org/mcp
export PSR_AUTH_MODE=static
export PSR_STORAGE_MODE=memory
export PSR_EPHEMERAL_ROOT=/restricted/psr-ephemeral

export PSR_ABUSE_HMAC_KEY_REF=env://PSR_ABUSE_HMAC_KEY
export PSR_ABUSE_HMAC_KEY='replace-with-at-least-32-random-bytes'

export PSR_SEARCH_PROVIDER=brave
export PSR_SEARCH_API_KEY_REF=env://BRAVE_SEARCH_API_KEY
export BRAVE_SEARCH_API_KEY='replace-with-server-side-key'

uv run --frozen psr-mcp
```

production에서는 reverse proxy의 TLS, trusted client IP normalization, raw-IP edge quota,
ephemeral volume permission과 outbound egress 정책을 별도로 구성해야 한다. 이 항목이 없는
단독 process는 Public Preview release 조건을 충족하지 않는다.

## 5. 외부 provider 고지

Brave adapter를 사용하면 다음 데이터가 provider에 전달된다.

- 사용자 질문에서 Government Profile이 생성한 검색어
- 한국 지역·한국어·strict safe-search와 결과 개수 parameter

PSR 서버는 검색어와 Search 결과를 영구 저장하지 않는다. 그러나 표준 Brave Search API는
provider 정책에 따라 질의를 최대 90일 보관할 수 있고 Enterprise Zero Data Retention은 별도
계약이다. 실제 배포는 `psr.service.policy`, 개인정보 고지와 연결 가이드에 이 경계를 표시해야
한다. 이 문서는 법률 의견이 아니며 배포자는 당시 provider 약관·가격·개인정보 정책을 다시
검토해야 한다.

검토 기준은 Brave의
[API privacy policy](https://api-dashboard.search.brave.com/privacy-policy),
[terms of service](https://api-dashboard.search.brave.com/terms-of-service),
[Web Search API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get)다.

## 6. 주요 설정

| 환경변수 | 기본값 | 허용범위/의미 |
|---|---:|---|
| `PSR_SEARCH_PROVIDER` | `disabled` | `disabled`, `curated`, `brave` |
| `PSR_SEARCH_TIMEOUT_SECONDS` | 5 | `>0..30` |
| `PSR_SEARCH_MAX_RESPONSE_BYTES` | 1 MiB | 1 KiB..10 MiB |
| `PSR_SEARCH_MAX_CONCURRENCY` | 7 | 1..10 |
| `PSR_COLLECTION_MAX_CONCURRENCY` | 4 | 1..20 |
| `PSR_QUICK_TIMEOUT_SECONDS` | 20 | 1..30, request timeout 이하 |
| `PSR_MAX_RUN_SOURCES` | 12 | 1..100 |
| `PSR_MAX_RUN_BYTES` | 30 MiB | 1..100 MiB |
| `PSR_PUBLIC_KILL_SWITCH` | `false` | 새 quick/start 중지 |

API key와 HMAC key는 diagnostics에서 값 대신 존재 여부만 표시된다.

## 7. 품질 검증

```bash
uv lock --check
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src tests scripts
uv audit --preview-features audit --frozen
uv run --frozen python scripts/dependency_licenses.py --check
uv run --frozen pytest --cov=psr_mcp --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json
uv run --frozen python scripts/coverage_gate.py --coverage-json coverage.json
uv run --frozen python scripts/live_curated_smoke.py
```

실제 PostgreSQL Foundation 회귀는
[PostgreSQL Runbook](./postgresql.md)의 test URL을 설정한 뒤 `pytest tests/postgres -q`로
별도 확인한다.

## 8. 공개 전 체크리스트

- curated 실제 source smoke와 사람이 읽는 결과 검토
- `psr.service.policy`가 provider·TTL·limit을 정확히 표시
- source별 `robots.txt` 결과와 수집 실패가 report에 표시
- 사이트별 약관·저작권 검토가 필요한 source registry 운영 절차
- edge IP spoof·quota, egress와 TLS 검증
- 질문·원문·결과·key canary의 log/DB/tmp 잔존 0건
- provider 일일 비용상한과 kill switch rehearsal
- project `LICENSE`와 `NOTICE` 결정
- PG0~PG3 승인
