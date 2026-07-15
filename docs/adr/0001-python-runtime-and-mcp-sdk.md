# ADR-0001: Python Runtime and MCP SDK Baseline

- Status: Accepted
- Date: 2026-07-16
- Decision owners: Principal Architect, Product Lead

## Context

PSR MCP는 공공분야 다중 사용자용 Remote MCP다. 구현 시점의 공식 Python SDK main branch는 v2 pre-release 문서를 기본으로 보여주지만, 공식 저장소는 v1.x를 production 권장 안정선으로 명시한다. v2는 breaking change가 가능한 pre-release다.

## Decision

1. production runtime 기준은 Python 3.12다.
2. dependency 범위는 `mcp>=1.28,<2`다.
3. 최초 lock은 공식 최신 안정 v1 릴리스 `1.28.1`을 사용한다.
4. v2 pre-release를 production dependency로 사용하지 않는다.
5. MCP-specific code는 `psr_mcp.mcp` adapter에 격리한다.
6. protocol contract는 MCP `2025-11-25`를 기준으로 검증한다.
7. v2/future protocol spike는 별도 branch와 compatibility suite에서 수행한다.

## Consequences

- 안정 API로 구현을 시작할 수 있다.
- SDK v2 migration 비용이 생길 수 있으나 domain/application은 영향을 받지 않아야 한다.
- lockfile과 Dependabot/Renovate equivalent 정책이 필요하다.
- SDK type/model을 domain signature에 노출하면 ADR 위반이다.

## Validation

- `uv lock`에서 `mcp` major가 1인지 확인한다.
- import boundary test에서 `domain`과 `application`이 `mcp`를 import하지 않는지 검사한다.
- in-memory 또는 Streamable HTTP conformance test를 실행한다.

## References

- [Official MCP Python SDK v1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
- [MCP specification versioning](https://modelcontextprotocol.io/docs/learn/versioning)
