# ADR-0002: Authentication and Tenant Boundary

- Status: Accepted
- Date: 2026-07-16

## Context

MCP Host confirmation은 기관 Identity나 업무승인을 증명하지 않는다. PSR MCP는 여러 Organization과 Project를 수용하며 IDOR, confused deputy, token passthrough를 방지해야 한다.

## Decision

1. Remote MCP는 OAuth 2.1 Resource Server로 동작한다.
2. 외부 Authorization Server가 token을 발급하고 MCP server가 issuer, audience, expiry, scope를 검증한다.
3. SDK `TokenVerifier`와 `AuthSettings`를 transport authentication adapter로 사용한다.
4. verified token claim과 internal Membership을 결합해 `AuthorizationContext`를 만든다.
5. 모든 repository operation은 `organization_id`를 명시적으로 받는다.
6. Project restriction, Role, OAuth scope를 모두 만족해야 한다.
7. PostgreSQL RLS와 object namespace를 defense in depth로 사용한다.
8. client bearer token을 upstream source/API로 전달하지 않는다.
9. development static context는 loopback 개발환경에서만 허용하며 production startup은 거부한다.

## Consequences

- Organization Admin이라도 token scope가 없으면 operation이 거부된다.
- Resource URI는 capability가 아니며 read마다 authorization을 수행한다.
- production OAuth adapter와 Membership cache invalidation이 Pilot 전 필수다.
- authorization negative test가 모든 interface에 필요하다.

## Validation

- cross-tenant Tool, Resource, service, repository contract test
- revoked/restricted Membership test
- wrong audience/scope token integration test
- production static auth fail-closed test
- downstream request token absence test는 Collector milestone에서 추가

## References

- [MCP Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [Python SDK Authorization](https://py.sdk.modelcontextprotocol.io/authorization/)
