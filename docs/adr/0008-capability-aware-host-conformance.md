# ADR-0008 — Capability-Aware Host Conformance

> 상태: Accepted · 날짜: 2026-07-16 · 결정자: Product owner

## Context

PSR MCP server는 Tool·Resource·Prompt 계약을 모두 제공한다. 공식 Python SDK와 MCP Inspector에서는 세 primitive의 catalog와 실제 호출을 검증했다. Codex CLI에서는 Tool 호출을 검증했지만, Resource·Prompt를 model-controlled session에서 강제로 호출하는 검증은 로컬 MCP 내용을 외부 model service로 전송할 수 있다.

기존 G5 문구인 “목표 Host 2종에서 Tool/Resource/Prompt”는 Host가 실제 사용자 표면에서 어떤 primitive를 독립적으로 노출하는지와 무관하게 모든 primitive 호출을 요구했다. 이 기준은 server contract 검증과 Host UX capability 검증을 혼합하고, 지원 판정을 위해 불필요한 데이터 전송을 유도한다.

## Decision

1. PSR MCP server의 Tool·Resource·Prompt 계약은 공식 SDK 자동 conformance와 세 primitive를 노출하는 Inspector에서 모두 검증한다.
2. 목표 AI Host의 필수 호환 기준은 해당 Host가 지원·노출하는 **필수 primitive의 실제 호출**이다.
3. Codex의 Foundation 필수 primitive는 Tool이다. 실제 Tool catalog 접근과 Tool call이 성공하면 Codex Host compatibility를 PASS로 판정한다.
4. Codex Resource·Prompt model-mediated 검증은 G5 또는 G6의 필수 조건이 아니다. 향후 명시적 사용자·보안 승인과 제품 필요가 있을 때만 별도 opt-in 검증한다.
5. Resource·Prompt를 직접 노출하는 목표 Host에서는 해당 primitive도 실제 호출해 compatibility matrix에 기록한다.
6. 확인하지 않은 primitive를 PASS로 추론하지 않는다. `NOT REQUIRED` 또는 `NOT EXPOSED`로 표시한다.
7. G5는 다음을 모두 만족하면 PASS다.
   - current stable protocol의 Tool·Resource·Prompt server contract
   - 목표 Host 2종에서 각 Host의 필수 primitive 실제 호출
   - durable Run의 disconnect/reconnect 검증
   - versioned compatibility matrix
8. 이 결정은 server의 Resource·Prompt 기능을 삭제하거나 품질 기준을 낮추지 않는다.

## Consequences

- Codex 지원은 Tool-first로 명확해지고 불필요한 model-mediated 데이터 전송을 피한다.
- Inspector와 reference client가 전체 server primitive contract의 회귀 oracle 역할을 유지한다.
- Host별 지원 표면의 차이를 제품 결함과 구분할 수 있다.
- 향후 Codex가 Resource·Prompt를 명시적으로 노출하거나 제품이 이를 필요로 하면 별도 보안 검토와 validation report가 필요하다.
- 본 결정에 따라 F4의 G5는 PASS지만, 실제 기관 IdP/gateway와 독립 owner 승인 등 G6 조건은 별개다.

## Rejected alternatives

- Codex Resource·Prompt 외부 전송을 G5 필수로 유지: 제품 기능과 무관한 전송 승인을 Foundation blocker로 만든다.
- Resource·Prompt를 server에서 제거: Inspector와 다른 MCP Host가 사용할 수 있는 표준 계약을 불필요하게 축소한다.
- 검증하지 않은 Codex primitive를 PASS 처리: 실제 증거가 없으므로 traceability 원칙에 위배된다.

## Validation

- `tests/integration/test_conformance_tcp.py`
- `tests/integration/test_tls_reverse_proxy.py`
- MCP Inspector `0.18.0` Tool·Resource·Prompt 실제 호출
- Codex CLI `0.144.2` Tool 실제 호출
- [Host compatibility matrix](../compatibility/host-matrix.md)
- [Remote G5 report](../validation/2026-07-16-remote-g5.md)

## Revisit triggers

- Codex가 Resource·Prompt를 명시적인 사용자 표면으로 노출
- 공공기관 업무 flow가 Codex Resource·Prompt를 필수로 요구
- 목표 Host 목록 변경
- MCP primitive 또는 capability negotiation의 안정 사양 변경
