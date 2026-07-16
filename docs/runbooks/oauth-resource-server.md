# OAuth Resource Server Runbook

> 적용 범위: Foundation F3 · 관련 결정: [ADR-0006](../adr/0006-oauth-resource-server-and-membership-binding.md)

## 1. 지원 계약

현재 구현은 외부 OIDC issuer가 발급한 서명된 JWT access token을 검증한다. 자체 Authorization Server, opaque token introspection, refresh token 저장은 지원하지 않는다.

필수 token/header 항목:

| 항목 | 조건 |
|---|---|
| `typ` | `at+jwt` 또는 `application/at+jwt` |
| `alg` | 기본 `RS256`, 설정 allowlist에 포함 |
| `kid` | JWKS의 서명 key와 일치 |
| `iss` | canonical `PSR_ISSUER_URL`과 exact match |
| `aud` | `PSR_RESOURCE_SERVER_URL` 포함 |
| `sub` | tenant external identity와 일치 |
| `client_id` | 비어 있지 않음 |
| `exp`, `iat`, optional `nbf` | 현재 시각과 허용 skew 내 유효 |
| `scope`/`scp` | `mcp:access`와 operation scope |
| `organization_id` | 내부 Membership을 조회할 기관 UUID |

## 2. 필수 환경변수

```bash
export PSR_ENV=production
export PSR_HOST=127.0.0.1
export PSR_PORT=8000
export PSR_PUBLIC_URL=https://research.example.gov
export PSR_RESOURCE_SERVER_URL=https://research.example.gov/mcp
export PSR_AUTH_MODE=oauth
export PSR_STORAGE_MODE=postgres
export PSR_ISSUER_URL=https://idp.example.gov/
export PSR_REQUIRED_MCP_SCOPES='mcp:access'
export PSR_OAUTH_ALLOWED_ALGORITHMS='RS256'
export PSR_OAUTH_ORGANIZATION_CLAIM=organization_id
export PSR_DATABASE_URL_REF=env://PSR_DATABASE_URL
export PSR_DATABASE_URL='<runtime PostgreSQL URL>'
export PSR_CURSOR_SIGNING_KEY='<32-byte 이상 별도 secret>'
```

JWKS가 issuer와 다른 origin이면 사전 검토한 origin만 추가한다.

```bash
export PSR_OAUTH_JWKS_ORIGINS='https://keys.example.gov'
```

`PSR_PUBLIC_URL`과 `PSR_RESOURCE_SERVER_URL`은 같은 origin이어야 한다. reverse proxy header는 현재 신뢰하지 않으므로 외부 canonical URL을 명시적으로 설정한다.

## 3. 기동 전 점검

1. [PostgreSQL runbook](./postgresql.md)에 따라 migration head와 runtime 최소권한을 적용한다.
2. `external_identities`에 `(organization_id, internal user_id, canonical issuer, external subject)` mapping을 등록한다.
3. Membership과 Organization이 `ACTIVE`인지 확인한다.
4. restricted Membership이면 `project_scope='RESTRICTED'`와 `membership_projects`를 함께 설정한다.
5. IdP discovery의 `issuer`가 `PSR_ISSUER_URL`과 문자 단위로 같은지 확인한다.
6. token의 `aud`, `typ`, `client_id`, organization claim을 test token으로 확인한다.
7. `psrctl doctor --json` 출력에 credential 또는 token이 없는지 확인한다.
8. RFC 9728 endpoint를 조회한다.

```bash
curl -sS https://research.example.gov/.well-known/oauth-protected-resource/mcp
```

## 4. 정상 판정

- token 없는 `/mcp` 요청: `401`, `WWW-Authenticate`에 `resource_metadata`
- `mcp:access` 없는 유효 token: `403 insufficient_scope`
- 유효 token과 활성 Membership: MCP request 처리
- 잘못된 issuer/audience/algorithm/expired token: `401`
- 잘못된 Organization, 폐기 Membership, 허용되지 않은 Project: opaque `NOT_FOUND_OR_FORBIDDEN`
- raw token, external subject, credential: 일반 application log에 없음

## 5. Key Rotation

1. IdP가 기존 key와 새 key를 겹쳐 게시한다.
2. 새 `kid` token을 canary로 호출한다.
3. 서버는 cache miss에서 JWKS를 한 번 refresh하고 검증한다.
4. 성공률과 401 비율을 관찰한다.
5. 모든 기존 token 만료 후 이전 key를 제거한다.

새 `kid`인데 IdP/JWKS가 응답하지 않으면 요청은 401로 실패한다. 장애 중 서명 검증을 생략하거나 cached 다른 key를 사용하지 않는다. 이미 cache된 알려진 key는 cache TTL 동안 계속 검증할 수 있다.

## 6. Membership 폐기

1. deployment/admin 경로에서 해당 Membership을 `REVOKED`로 변경한다.
2. 같은 token으로 다음 Tool 호출이 거부되는지 확인한다.
3. 필요하면 IdP에서도 session/token을 revoke한다.
4. 감사 event에 operator, reason, time을 기록한다. Membership 관리 Tool은 아직 구현되지 않았으므로 직접 SQL 변경은 승인된 운영 절차에서만 수행한다.

## 7. 장애 대응

| 증상 | 확인 | 대응 |
|---|---|---|
| 모든 token 401 | issuer/audience canonical 값, clock, discovery | 설정 rollback, IdP 상태 확인 |
| 새 key만 401 | JWKS origin allowlist, `kid`, cache refresh | IdP overlap 확인, allowlist 승인 검토 |
| 403 insufficient scope | `mcp:access`, client consent | IdP scope policy 수정 |
| Tool만 거부 | Membership status, issuer+subject mapping, project restriction | 내부 mapping 검토 |
| DB resolver unavailable | pool, runtime grant, migration `0002_external_identity` | DB runbook 수행 |

401 응답을 줄이기 위해 검증을 완화하지 않는다. token 원문을 ticket, chat, log에 첨부하지 않는다.

## 8. 현재 제한

- 실제 기관 IdP onboarding drill은 아직 수행하지 않았다.
- rate limit, reverse proxy/TLS, 두 종류 Host 호환성은 F4에서 검증한다.
- inbound token의 downstream 부재는 Collector가 추가되는 C0 gate에서 검증한다.
