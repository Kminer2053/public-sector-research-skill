# Remote MCP 운영 Runbook

> 적용 범위: Foundation F4 · 구현 기준: `c7064cd` · 운영 선언 전 [Threat Model](../security/THREAT_MODEL.md) 검토 필요

[OAuth Runbook](./oauth-resource-server.md) · [PostgreSQL Runbook](./postgresql.md) · [Host Matrix](../compatibility/host-matrix.md)

## 1. 목적과 운영 경계

이 문서는 PSR MCP를 TLS terminating reverse proxy 뒤에서 운영하고 Host conformance를 진단하는 절차다. application process는 TLS 인증서나 client forwarded header를 직접 신뢰하지 않는다.

```text
MCP Host
  └─ HTTPS + OAuth bearer
      └─ 기관 Gateway/WAF/TLS reverse proxy
          └─ HTTP loopback/private network
              └─ uvicorn(proxy_headers=False)
                  └─ Starlette HTTP policy
                      └─ FastMCP stateless Streamable HTTP
```

운영 불변조건:

- 외부 endpoint는 `https://<canonical-host>/mcp`다.
- backend는 public interface에 직접 bind하지 않는다.
- `PSR_PUBLIC_URL`과 `PSR_RESOURCE_SERVER_URL`은 proxy가 전달한 header가 아니라 배포 설정의 canonical URL이다.
- uvicorn `proxy_headers=False`를 유지한다. 임의 `X-Forwarded-*`를 application identity나 URL 생성에 사용하지 않는다.
- OAuth token은 log, conformance JSON, downstream request에 남기지 않는다.
- 다중 replica rate/quota는 gateway가 authoritative control이다.

## 2. 필수 구성

### 2.1 Application

| 변수 | 운영 요구 |
|---|---|
| `PSR_ENV` | `production` |
| `PSR_HOST` | loopback 또는 허용된 private address; 보안그룹으로 proxy만 접근 |
| `PSR_PORT` | backend 전용 port |
| `PSR_PUBLIC_URL` | `https://research.<institution-domain>`; path 없음 |
| `PSR_RESOURCE_SERVER_URL` | `${PSR_PUBLIC_URL}/mcp` |
| `PSR_AUTH_MODE` | `oauth` |
| `PSR_STORAGE_MODE` | `postgres` |
| `PSR_ISSUER_URL` | 기관 IdP의 exact HTTPS issuer |
| `PSR_REQUIRED_MCP_SCOPES` | 최소 `mcp:access` |
| `PSR_OAUTH_ALLOWED_ALGORITHMS` | 기본 `RS256`; `none`, HMAC 금지 |
| `PSR_OAUTH_ORGANIZATION_CLAIM` | IdP 계약과 합의된 claim 이름 |
| `PSR_OAUTH_JWKS_ORIGINS` | cross-origin JWKS가 필요한 경우에만 명시 |
| `PSR_DATABASE_URL_REF` | `env://<VARIABLE>` 형태의 secret reference |
| `PSR_CURSOR_SIGNING_KEY` | 개발 기본값이 아닌 32 byte 이상 secret |

### 2.2 Remote HTTP policy

| 변수 | 기본값 | 범위 | 의미 |
|---|---:|---:|---|
| `PSR_MAX_REQUEST_BYTES` | `1048576` | 1 KiB~10 MiB | `/mcp` request body hard limit |
| `PSR_REQUEST_TIMEOUT_SECONDS` | `30` | 1~300 | stateless JSON request deadline |
| `PSR_RATE_LIMIT_REQUESTS` | `120` | 1~10000 | process-local token/IP window 한도 |
| `PSR_RATE_LIMIT_WINDOW_SECONDS` | `60` | 1~3600 | fixed window |

응답 계약:

| 상황 | HTTP | body/header |
|---|---:|---|
| 잘못된 `Content-Length` | 400 | `invalid_content_length` |
| body 초과 | 413 | `request_too_large` |
| process-local rate 초과 | 429 | `rate_limited`, `Retry-After` |
| application deadline 초과 | 504 | `request_timeout`, `retryable=true` |
| token 없음/불량 | 401 | RFC 9728 metadata link가 있는 `WWW-Authenticate` |
| scope 부족 | 403 | `insufficient_scope` |

모든 HTTP response에는 검증된 또는 server 생성 `X-Request-ID`가 붙는다. client request ID는 ASCII `[A-Za-z0-9._:-]`, 8~128자만 수용한다.

## 3. Gateway/TLS 요구사항

Gateway 설정은 제품별 문법보다 다음 결과를 충족해야 한다.

1. TLS 1.2 이상과 기관 정책 cipher를 적용한다.
2. 기관이 승인한 공개 또는 private CA certificate chain 전체를 제공한다.
3. backend 연결은 loopback/private network만 사용한다.
4. request method, body, `Authorization`, `Accept`, `Content-Type`, `Mcp-*`, `Origin`, canonical `Host`를 보존한다.
5. hop-by-hop header와 외부 사용자의 `X-Forwarded-*`는 제거하거나 gateway가 재작성한다.
6. gateway request body limit은 application limit 이하로 맞춘다.
7. gateway timeout은 application timeout보다 약간 길게 둬 application의 구조화된 504가 먼저 반환되게 한다.
8. WAF log에서 `Authorization`, cookie, query secret을 redact한다.
9. anonymous/global rate와 token/client quota를 gateway에서 적용한다.
10. backend에서 public hostname에 대한 DNS resolution이나 TLS termination을 요구하지 않는다.

Foundation test는 임시 CA certificate로 `HTTPS proxy → HTTP backend`를 실제 실행한다. `X-Forwarded-Host/Proto` spoof가 canonical Host 검증을 변경하지 않는 integration test도 포함한다.

## 4. 배포 전 절차

```bash
uv sync --all-groups --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src tests scripts
uv audit --preview-features audit --frozen
uv run --frozen python scripts/dependency_licenses.py --check
uv run --frozen pytest --cov=psr_mcp --cov-branch --cov-report=term-missing
uv build
```

PostgreSQL migration은 web process와 분리된 operator identity로 수행한다.

```bash
PSR_MIGRATION_DATABASE_URL='<owner-url>' uv run --frozen psrctl db current
PSR_MIGRATION_DATABASE_URL='<owner-url>' uv run --frozen psrctl db upgrade
```

runtime role이 table owner 또는 `BYPASSRLS`인지 확인하고, [PostgreSQL Runbook](./postgresql.md)의 backup/restore rehearsal이 유효한지 확인한다.

배포 전 `doctor` 출력에는 secret value가 없어야 한다.

```bash
uv run --frozen psrctl doctor --json
```

## 5. 기동과 종료

```bash
uv run --frozen psrctl serve mcp
```

- production service manager가 SIGTERM을 보내면 uvicorn lifespan이 MCP session manager, OIDC HTTP client, PostgreSQL pool 순서로 닫힌다.
- readiness는 process port open만으로 판단하지 않는다. migration revision, DB pool, IdP discovery/JWKS 접근, authenticated conformance를 별도 확인한다.
- Foundation에는 별도의 unauthenticated health endpoint가 없다. gateway가 필요한 경우 process probe와 authenticated synthetic probe를 분리한다.

## 6. 공식 SDK conformance

Bearer는 command line argument로 넣지 않고 환경변수에서만 읽는다.

```bash
export PSR_CONFORMANCE_BEARER_TOKEN='<short-lived-token>'
uv run --frozen psrctl conformance \
  --endpoint 'https://research.example.gov/mcp' \
  --token-env PSR_CONFORMANCE_BEARER_TOKEN \
  --project-id '<project-id>' \
  --approved-plan-id '<approved-plan-id>' \
  --idempotency-key 'release-conformance-0001'
unset PSR_CONFORMANCE_BEARER_TOKEN
```

기관 private CA를 쓰면:

```bash
uv run --frozen psrctl conformance \
  --endpoint 'https://research.institution/mcp' \
  --ca-bundle '/etc/ssl/institution-ca.pem'
```

PASS JSON에는 token이 아니라 `bearer_token_used: true|false`만 나온다. 실패는 exit code `4`와 일반화된 문구만 stdout에 출력한다. 제한된 operator log에서 `X-Request-ID`로 조사한다.

## 7. MCP Inspector 재현

검증 version은 `@modelcontextprotocol/inspector@0.18.0`, Node 요구조건은 `^22.7.5`다.

```bash
npx -y @modelcontextprotocol/inspector@0.18.0 --cli \
  'https://research.example.gov/mcp' --transport http --method tools/list

npx -y @modelcontextprotocol/inspector@0.18.0 --cli \
  'https://research.example.gov/mcp' --transport http \
  --method tools/call --tool-name psr.project.list --tool-arg limit=20

npx -y @modelcontextprotocol/inspector@0.18.0 --cli \
  'https://research.example.gov/mcp' --transport http \
  --method resources/templates/list

npx -y @modelcontextprotocol/inspector@0.18.0 --cli \
  'https://research.example.gov/mcp' --transport http \
  --method resources/read --uri 'psr://projects/<project-id>'

npx -y @modelcontextprotocol/inspector@0.18.0 --cli \
  'https://research.example.gov/mcp' --transport http \
  --method prompts/get --prompt-name public_policy_research \
  --prompt-args project_id='<project-id>' question='조사 질문' as_of_date='2026-07-16'
```

인증 endpoint는 `--header "Authorization: Bearer $TOKEN"`을 사용할 수 있지만 shell history와 process listing 노출 위험이 있다. 기관 검증에서는 짧은 수명 token, 격리된 runner, history 비활성화, 실행 직후 폐기를 적용한다.

## 8. 장애 진단

### 8.1 401/403

1. token 원문을 log에 붙이지 않는다.
2. `iss`, `aud`, `typ=at+jwt`, `alg`, `kid`, `exp/iat/nbf`, base scope를 확인한다.
3. discovery issuer exact match와 JWKS origin allowlist를 확인한다.
4. organization claim은 tenant 선택 힌트일 뿐 membership 증명이 아님을 확인한다.
5. `(issuer, sub, organization_id)` external identity, active Organization/Membership, Project restriction을 확인한다.
6. revoked membership cache가 없으므로 즉시 DB 상태가 반영되어야 한다.

### 8.2 400/403/421 Host 또는 Origin 거부

- Host가 `PSR_PUBLIC_URL` canonical hostname인지 확인한다.
- browser/Inspector UI Origin이 허용 origin인지 확인한다.
- gateway가 canonical Host를 backend에 전달하는지 확인한다.
- `X-Forwarded-Host`로 우회하려 하지 않는다.

### 8.3 429

- 단일 token+source IP인지 확인한다.
- process-local window와 gateway quota를 구분한다.
- replica별 limiter를 global quota로 오인하지 않는다.
- `Retry-After` 이후 idempotent read 또는 같은 idempotency key write만 재시도한다.

### 8.4 504

- `operation_id`가 반환되기 전 timeout이면 write 성공을 추정하지 않는다.
- 같은 idempotency key로 `run.start`를 재시도한다.
- DB audit와 Run Resource를 확인한다.
- 단순히 timeout을 늘리기 전에 pool exhaustion, IdP latency, DB lock을 점검한다.

### 8.5 Host disconnect

- application state는 Host session이 아니라 `run_id`로 조회한다.
- 새 Host session에서 `psr.research.run.status`와 Run Resource를 호출한다.
- 동일 Run ID가 없으면 tenant/scope/project restriction과 DB durability를 확인한다.

## 9. 추적과 감사

| ID | 생성 위치 | 용도 |
|---|---|---|
| `X-Request-ID` | HTTP boundary | gateway/application request log 상관관계 |
| `operation_id` | application service | Tool/Resource 응답과 audit row 연결 |
| `run_id` | ResearchRun | Host reconnect와 job 수명주기 |
| `audit_event.id` | PostgreSQL | append-only actor/action record |

OAuth→MCP→PostgreSQL integration test는 `run.start` 응답의 `operation_id`, `run_id`, audit row의 actor, operation, target, outcome이 일치함을 확인한다. HTTP request ID와 application operation ID는 목적이 다르므로 같은 값일 필요가 없다.

## 10. Rollback

1. 새 traffic을 차단하고 in-flight request deadline까지 기다린다.
2. application image를 직전 검증 artifact로 되돌린다.
3. DB schema는 자동 downgrade하지 않는다. 이전 binary의 schema compatibility를 먼저 확인한다.
4. migration rollback이 필요하면 backup을 확인하고 `--confirm-downgrade`가 있는 operator 절차를 사용한다.
5. IdP/JWKS 변경을 rollback할 때 유효 token과 폐기 token을 각각 재검증한다.
6. incident timeline에 request ID, operation ID, deployment revision을 기록한다.

## 11. 운영 전 남은 승인

- 실제 기관 IdP와 기관 CA onboarding
- gateway/WAF 제품 설정 review와 penetration test
- Codex Resource/Prompt 외부 model 전송 범위에 대한 사용자·보안 승인
- Project source license와 distribution policy 결정
- Product, Architecture, Security owner의 G6 서명

이 항목이 닫히기 전에는 `production-ready` 또는 `public-sector deployment-ready`로 표현하지 않는다.
