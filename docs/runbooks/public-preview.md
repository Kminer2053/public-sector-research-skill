# Public Preview 실행 Runbook

> 대상: `PUBLIC_EPHEMERAL` · 기준일: 2026-07-16 · 상태: 로컬 개발/실증용

[README](../../README.md) · [Architecture](../ARCHITECTURE.md) ·
[Validation](../VALIDATION_CRITERIA.md) ·
[PG1 보고서](../validation/2026-07-16-pg1-useful-research.md) ·
[Trusted Proxy 검증](../validation/2026-07-16-trusted-proxy-boundary.md)

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

사람이 읽는 전체 결과와 표준 검토표를 stdout으로 생성한다.

```bash
uv run --frozen python scripts/live_curated_review.py
```

review script는 질문과 결과를 포함하므로 production access log나 CI artifact에 자동 업로드하지
않는다. 서버·DB에는 저장하지 않으며, 보존이 필요하면 검토자가 승인된 로컬 문서공간에
명시적으로 저장한다. feedback token과 operation ID는 packet에 포함하지 않는다.

2026-07-16 관찰값은 7개 track, 12개 citation, recommendation 5건, failure 0이었다.
gap은 curated 범위 제한 1건과 government-policy·procurement missing-anchor 2건이며,
`PURGED`, ephemeral directory empty를 확인했다. 이 수치는 source 변경에 따라 달라질 수
있으므로 release 전 다시 실행한다.

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
export PSR_TRUSTED_PROXY_CIDRS='127.0.0.1/32'

export PSR_SEARCH_PROVIDER=brave
export PSR_SEARCH_API_KEY_REF=env://BRAVE_SEARCH_API_KEY
export BRAVE_SEARCH_API_KEY='replace-with-server-side-key'

uv run --frozen psr-mcp
```

production에서는 reverse proxy가 외부의 `X-PSR-Client-IP`를 제거한 뒤 자신이 확인한 단일
canonical IP로 overwrite해야 한다. application은 `PSR_TRUSTED_PROXY_CIDRS` 안의 peer가 보낸
이 header만 소비한다. TLS, raw-IP edge quota, ephemeral volume permission과 outbound egress
정책도 별도로 구성해야 한다. 이 항목이 없는 단독 process는 Public Preview release 조건을
충족하지 않는다.

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
| `PSR_OUTBOUND_MAX_CONCURRENCY` | 8 | Search·robots·원문 fetch를 합친 process 동시 외부요청, 1..32 |
| `PSR_SOURCE_HOST_MAX_CONCURRENCY` | 2 | 정규화된 source host별 동시 외부요청, 1..8이며 global 이하 |
| `PSR_SOURCE_HOST_RATE_REQUESTS` | 2 | source host별 token-bucket capacity, 1..60 |
| `PSR_SOURCE_HOST_RATE_WINDOW_SECONDS` | 1 | capacity refill window, 0.1..60초 |
| `PSR_TRUSTED_PROXY_CIDRS` | 빈 값 | production public mode 필수, comma-separated CIDR |
| `PSR_QUICK_TIMEOUT_SECONDS` | 20 | 1..30, request timeout 이하 |
| `PSR_PUBLIC_MAX_ACTIVE_QUICK` | 8 | process당 동시 quick 상한, 1..100 |
| `PSR_PUBLIC_DAILY_QUICK_BUDGET` | 0 | process·UTC 일자별 quick 진입 상한, 0은 development 비활성; production은 1 이상 필수 |
| `PSR_PUBLIC_PAUSE_FILE` | 빈 값 | operator가 관리하는 절대경로 sentinel; 존재하면 새 quick 중지 |
| `PSR_FEEDBACK_TOKEN_TTL_SECONDS` | 86400 | feedback capability TTL, 300..604800 |
| `PSR_MAX_RUN_SOURCES` | 12 | 1..100 |
| `PSR_MAX_RUN_BYTES` | 30 MiB | 1..100 MiB |
| `PSR_PUBLIC_KILL_SWITCH` | `false` | 새 quick/start 중지 |

API key와 HMAC key는 diagnostics에서 값 대신 존재 여부만 표시된다.

`PSR_PUBLIC_DAILY_QUICK_BUDGET`은 정확한 provider 청구액 상한이 아니라 단일 process의
보수적 진입 안전망이다. production 초기값은 load·provider quota를 검토해 명시해야 하며,
예시 500은 제품 보장값이 아니다. replica가 여러 개면 gateway/shared limiter와 provider
dashboard hard cap을 함께 설정한다.

`PSR_SEARCH_MAX_CONCURRENCY`와 `PSR_COLLECTION_MAX_CONCURRENCY`는 각 작업 단계의 상한이고,
`PSR_OUTBOUND_MAX_CONCURRENCY`는 두 단계를 합친 실제 network 상한이다. source host 제한은
robots, 원문과 redirect마다 적용된다. token bucket은 기본적으로 host별 2회를 즉시 허용한 뒤
1초 창 속도로 refill한다. Search provider host에도 같은 정책이 적용된다. 여러 replica의
합산 rate와 upstream failure circuit breaker는 배포 source 정책에서 별도로 정한다.

## 6.1 Runtime pause

예시 설정:

```bash
export PSR_PUBLIC_PAUSE_FILE=/run/psr/public.pause
```

새 조사 중지:

```bash
touch /run/psr/public.pause
```

`psr.service.policy`에서 `kill_switch_active=true`,
`research_available=false`를 확인한다. 이미 실행 중인 조사의 access block과 purge는
계속된다.

새 조사 재개:

```bash
rm /run/psr/public.pause
```

pause 파일은 application이 만들거나 삭제하지 않는다. control plane 또는 권한이 제한된
운영자가 관리하고, 외부 사용자가 해당 경로를 쓸 수 없어야 한다. file 내용은 읽지 않으므로
운영 메모나 사용자 content를 넣지 않는다.

## 6.2 Pre-deploy doctor

일반 진단:

```bash
psrctl doctor --json
```

CI 또는 배포 직전 configuration gate:

```bash
psrctl doctor --json --require-public-ready
```

종료코드 0은 production 공개 설정에 필요한 source mode, restricted ephemeral root, 실제
secret 존재, trusted proxy, daily quick budget과 runtime pause control이 준비됐다는 뜻이다.
미달이면 종료코드 5다. 출력의 `external_gates_pending`은 이 명령이 확인할 수 없는 실제
gateway spoof rehearsal, shared quota/provider hard cap, staging purge와 사용자 효용 검증을
나열한다. 따라서 exit 0만으로 Public Preview 배포 승인을 선언하지 않는다.

## 6.3 Content-free feedback

성공한 quick 결과에는 workspace purge 뒤 생성된 `feedback_token`과
`feedback_expires_at`이 포함된다. Host는 사용자가 선택한 경우에만 다음 Tool을 호출한다.

```text
psr.feedback.submit(
  feedback_token,
  helpful: bool,
  save_feature_interest: bool
)
```

feedback Tool payload는 free text, 질문, 결과, 사용자·IP·Host ID를 받지 않는다. raw
token도 저장·로그하지 않고 만료 전 replay 방지를 위한 SHA-256 digest와 aggregate count만
process memory에 둔다. digest는 만료 뒤 `PSR_PURGE_SWEEP_SECONDS` 이내에 제거된다. 현재
dedup과 count는 process restart와 multi-replica를 넘지 않으므로 제한 공개는 single-node 또는
sticky routing에서 시작하고, 표본 보존이 필요하면 content-free shared metric backend를 별도
승인한다.

reverse proxy, WAF와 MCP Host telemetry에서도 request/response body와 Tool argument logging을
꺼야 한다. access log는 허용된 status·duration·byte bucket만 남기며 raw feedback token이나
boolean 응답을 기록하지 않는다. 공개 전 gateway canary scan으로 이 설정을 다시 확인한다.

## 6.4 Public MCP conformance

실제 공개 endpoint의 익명 catalog, policy, quick 결과 구조·품질, purge 표시와 재연결을 공식
MCP SDK client로 확인한다.

```bash
psrctl conformance-public \
  --endpoint 'https://research.example.org/mcp'
```

PASS JSON은 질문·검색어·인용 URL·excerpt·feedback token·operation ID를 포함하지 않고 count,
ratio, source mode, purge와 reconnect 상태만 출력한다. release gate는 `disabled`,
`development_fixture`, `test_static` source mode와 구조 품질 기준 미달을 거부한다.

이 명령은 고정된 공공기관 AI 구매 질문으로 실제 quick을 한 번 실행하므로 daily budget과
provider 비용을 소비한다. Brave mode에서는 이 고정 질문에서 생성한 검색어가 provider에
전송된다. readiness/health probe로 자주 호출하지 말고 pre-deploy, release rehearsal과 장애
확인 시에만 사용한다.

기관 private CA는 `--ca-bundle`로 지정한다.

```bash
psrctl conformance-public \
  --endpoint 'https://research.institution/mcp' \
  --ca-bundle '/etc/ssl/institution-ca.pem'
```

`--verify-feedback`은 false/false synthetic 응답 한 건을 실제 aggregate에 추가한다. 실제
사용자 helpful 지표를 오염시키므로 초기화 가능한 staging에서만 사용하고 production
정기 probe에는 사용하지 않는다. 기본 conformance는 quick 결과의 feedback capability
존재와 만료시각만 검사한다.

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
