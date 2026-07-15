# ADR-0004: MCP Contract Boundary

- Status: Accepted
- Date: 2026-07-16

## Context

PSR MCP는 여러 Host에서 같은 Project Evidence를 사용해야 한다. MCP SDK decorator에 business logic을 직접 넣으면 protocol migration, test, authorization 일관성이 깨진다.

## Decision

1. MCP Gateway는 schema validation, auth context resolution, application 호출, result/error mapping만 담당한다.
2. Tool 이름은 versioned catalog의 `psr.<domain>.<action>`을 사용한다.
3. Pydantic input/output model은 MCP adapter에 두고 domain command/result로 변환한다.
4. Tool과 Resource는 같은 application authorization policy를 호출한다.
5. 모든 write는 idempotency key 또는 expected version을 요구한다.
6. MCP annotations는 UI hint이며 authorization에 사용하지 않는다.
7. application state는 explicit IDs와 store에 보존한다.
8. experimental MCP Tasks에 core flow가 의존하지 않는다.

## Consequences

- adapter boilerplate가 생기지만 business contract test를 protocol과 분리할 수 있다.
- SDK v2 migration은 `psr_mcp.mcp`에 집중된다.
- schema snapshot과 backward compatibility policy가 필요하다.

## Validation

- domain/application import boundary
- Tool input/output schema snapshot
- Tool/Resource authorization parity
- structuredContent와 text fallback
- Tasks 없이 plan/run/status flow
