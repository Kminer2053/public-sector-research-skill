# ADR-0006: OAuth Resource Server and Membership Binding

- Status: Accepted
- Date: 2026-07-16

## Context

PSR MCP는 다수 기관 사용자를 수용하는 OAuth protected resource다. 외부 access token의 `organization_id`, Role 또는 Project 값을 그대로 신뢰하면 claim 조작, confused deputy, 전역 사용자 directory 노출이 발생할 수 있다. MCP SDK의 `TokenVerifier`는 transport authentication을 제공하지만 내부 Membership 권한까지 결정하지 않는다.

## Decision

1. Foundation은 OIDC Discovery와 JWT access token을 지원하며 opaque token introspection은 지원하지 않는다.
2. JWT는 기본적으로 RFC 9068 profile을 적용한다. `typ=at+jwt`, `kid`, `RS256`, exact issuer/audience, `sub`, `client_id`, `exp`, `iat`를 필수로 검증하고 `nbf`가 있으면 검증한다.
3. 허용 알고리즘은 설정 allowlist이며 `none`과 HMAC 계열은 거부한다.
4. OIDC Discovery의 issuer는 설정과 정확히 같아야 한다. JWKS URI는 issuer origin 또는 명시적 HTTPS origin allowlist에 있어야 한다.
5. Discovery/JWKS는 300초 cache하고 unknown `kid`에서 한 번 강제 refresh한다. 새 키를 가져오지 못하면 fail closed한다.
6. root issuer는 설정 계층에서 trailing slash를 canonicalize한다. verifier는 canonical 값을 다시 변형하지 않고 exact match한다.
7. token의 `organization_id` claim은 권한이 아니라 tenant 조회 힌트다. 이 claim은 필수이며 PostgreSQL의 활성 `external_identities + memberships + organizations` 조합과 일치해야 한다.
8. 외부 identity는 전역 `users.external_subject`가 아니라 RLS가 강제된 `external_identities(organization_id, issuer, external_subject)`에 저장한다.
9. `project_scope=ALL|RESTRICTED`와 `membership_projects`로 Project 제한을 표현한다. OAuth scope, 내부 Role, Project 제한을 모두 통과해야 한다.
10. runtime DB role은 전역 `users`를 조회할 수 없다. 필요한 tenant table의 최소 SELECT와 Run/Job/Audit DML만 부여한다.
11. raw bearer token은 MCP SDK request context 밖으로 전달하지 않는다. 내부 `AuthorizationContext`에는 allowlisted claim과 `jti` SHA-256만 저장한다.
12. RFC 9728 Protected Resource Metadata와 `WWW-Authenticate resource_metadata`는 SDK `AuthSettings`로 제공한다.
13. PostgreSQL pool과 OIDC client는 process-wide Starlette lifespan에서 관리한다. FastMCP의 request/session lifespan에서 열고 닫지 않는다.
14. runtime database credential은 `env://VARIABLE` secret reference로만 해석하며 `Settings`와 diagnostics에 secret 값을 저장하지 않는다.

## Rejected Alternatives

- token의 Organization·Role·Project claim을 직접 권한으로 사용: Membership 폐기와 내부 정책을 즉시 반영할 수 없다.
- 전역 `users` table을 runtime role에 공개: RLS tenant boundary를 우회하는 directory가 된다.
- unknown key에서 기존 키 또는 서명 없는 claim으로 계속 처리: key rotation 장애가 인증 우회가 된다.
- FastMCP lifespan에서 DB pool 관리: stateless HTTP 요청마다 pool이 닫혀 다음 요청이 실패한다.
- MVP에서 자체 Authorization Server 구현: 제품 범위를 벗어나며 기관 IdP 통합을 방해한다.

## Consequences

- 기관 IdP 또는 token broker는 canonical issuer, audience, `at+jwt`, `client_id`, `organization_id`를 제공해야 한다.
- 한 사용자가 여러 기관에 속해도 token이 선택한 기관의 활성 Membership만 사용한다.
- Membership 폐기는 cache 없이 다음 Tool/Resource 요청부터 반영된다.
- issuer별 claim 변환이나 opaque token이 필요하면 별도 verifier adapter와 ADR이 필요하다.
- Collector가 생길 때 inbound token이 outbound request에 포함되지 않는 검증을 추가해야 한다.

## Validation

- `tests/unit/test_oauth_tokens.py`
- `tests/unit/test_oauth_context_provider.py`
- `tests/integration/test_oauth_resource_server.py`
- `tests/postgres/test_oauth_membership.py`
- `tests/postgres/test_oauth_end_to_end.py`

## References

- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
- [RFC 9728: OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [MCP Python SDK v1 authorization](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
