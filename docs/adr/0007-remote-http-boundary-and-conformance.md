# ADR-0007 — Remote HTTP Boundary and Conformance

> 상태: Accepted for Foundation implementation · 날짜: 2026-07-16

## Context

PSR MCP는 public-sector multi-user remote service이므로 loopback SDK smoke만으로는 Host 호환성, TLS trust, resource exhaustion, disconnect recovery를 검증할 수 없다. 반대로 application이 TLS certificate, proxy product, distributed quota까지 직접 소유하면 Foundation 범위가 과도하게 커진다.

## Decision

1. application은 MCP `2025-11-25` Streamable HTTP를 `json_response=True`, `stateless_http=True`로 제공한다.
2. TLS는 기관 gateway/reverse proxy에서 종료하며 uvicorn은 `proxy_headers=False`로 실행한다.
3. canonical public/resource URL은 forwarded header가 아니라 validated configuration에서만 얻는다.
4. SDK DNS rebinding protection과 canonical Host/Origin allowlist를 유지한다.
5. application boundary는 request body, deadline, process-local token/IP rate, request ID를 제한한다.
6. global/multi-replica quota와 slowloris protection은 gateway 책임이다.
7. official SDK conformance probe를 repository CLI로 제공하고 Tool/Resource/Prompt catalog를 reviewed contract와 정확히 비교한다.
8. durable application `run_id`로 새 connection에서 상태와 Resource를 재조회한다. MCP session이나 experimental Tasks에 application state를 두지 않는다.
9. private institution CA 검증을 위해 conformance CLI에 HTTPS-only `--ca-bundle`을 제공한다.
10. Host별 primitive를 실제 실행한 항목만 compatibility matrix에서 PASS로 표시한다.

## Consequences

- TLS proxy와 Host reconnect를 자동 통합 테스트할 수 있다.
- forged forwarded header가 public identity를 바꾸지 않는다.
- process-local limiter는 단독으로 distributed quota를 보장하지 않는다.
- JSON response buffering은 Foundation의 작은 response에 적합하지만 대용량/streaming output 도입 전에 재설계가 필요하다.
- Host가 Resource/Prompt를 UI에서 노출하지 않으면 server contract PASS와 Host UX 지원을 분리 기록한다.

## Rejected alternatives

- uvicorn native TLS를 production topology로 사용: 기관 WAF, certificate rotation, global quota와 분리된다.
- forwarded header를 자동 신뢰: proxy 경계 오구성 시 Host/URL spoof 위험이 있다.
- Redis rate limiter를 Foundation에 도입: 아직 multi-replica 운영이 아니며 새로운 state dependency가 된다.
- generic crawler/network retry를 MCP boundary에 사용: write replay와 protocol retry 의미가 다르다.

## Validation

- `tests/integration/test_tls_reverse_proxy.py`
- `tests/integration/test_conformance_tcp.py`
- `tests/integration/test_remote_transport.py`
- `tests/unit/test_http_policy.py`
- [Remote G5 report](../validation/2026-07-16-remote-g5.md)

## Revisit triggers

- streaming/large response 도입
- 두 개 이상 application replica
- gateway가 authenticated subject quota를 제공
- MCP protocol/SDK transport major change
- target Host가 sessionful behavior를 요구
