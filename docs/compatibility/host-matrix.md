# MCP Host Compatibility Matrix

> 기준일: 2026-07-16 · 구현 기준: `c7064cd` · 지원정책: ADR-0008 · Protocol: `2025-11-25`

[Remote MCP Runbook](../runbooks/remote-mcp.md) · [G5 Validation Report](../validation/2026-07-16-remote-g5.md) · [Validation Criteria](../VALIDATION_CRITERIA.md)

## 1. 판정 규칙

- `PASS`: 표시된 Host와 server의 실제 Streamable HTTP 세션에서 성공했다.
- `AUTOMATED`: repository test가 재현한다.
- `MANUAL`: version과 명령을 고정한 수동 실행 증적이다.
- `NOT EXPOSED`: server 결함이 아니라 해당 Host의 현재 사용자 표면에서 primitive를 직접 선택할 수 없거나 확인하지 못했다.
- `NOT REQUIRED`: 해당 Host의 Foundation 지원 계약에서 필수 primitive가 아니다.
- `BLOCKED`: 검증하려면 명시적인 보안 승인이나 외부 환경이 필요하다.
- 지원 판정은 Host가 실제로 노출하는 primitive별로 한다. 확인하지 않은 칸을 `PASS`로 추론하지 않는다.

## 2. 요약

| Client/Host | Version | Transport | Tool | Resource | Prompt | Reconnect | TLS | 판정 |
|---|---:|---|---|---|---|---|---|---|
| MCP Python SDK reference client | `mcp 1.28.1` | Streamable HTTP | PASS | PASS | PASS | PASS | PASS | PASS/AUTOMATED |
| MCP Inspector CLI | `0.18.0` | Streamable HTTP | PASS | PASS | PASS | PASS | 미실행 | PASS/MANUAL |
| Codex CLI bundled Host | `0.144.2` | Streamable HTTP | PASS | NOT REQUIRED | NOT REQUIRED | 미실행 | 미실행 | PASS/MANUAL |

[ADR-0008](../adr/0008-capability-aware-host-conformance.md)에 따라 전체 server Tool/Resource/Prompt 계약은 Reference client와 Inspector로 검증하고, 목표 AI Host는 실제 노출하는 필수 primitive로 판정한다. Codex Foundation 지원 계약은 Tool-first이며 실제 Tool call이 통과했다. 따라서 capability-aware `G5`는 **PASS**다. Codex Resource/Prompt는 검증하지 않았으며 PASS로 추론하지 않는다.

## 3. Reference Client

| 항목 | 결과 | 자동 증적 |
|---|---|---|
| initialize/capability | `2025-11-25`, serverInfo 확인 | `tests/integration/test_conformance_tcp.py` |
| Tool catalog | 검토된 5개 이름과 정확히 일치 | `src/psr_mcp/conformance.py` |
| Tool call | `project.list/get`, `run.start/status` | 동일 |
| structured/text | `structuredContent`와 text fallback 모두 필수 | 동일 |
| Resource | 2개 template catalog, Project/Run read | 동일 |
| Prompt | `public_policy_research` get, message 비어 있지 않음 | 동일 |
| reconnect | 첫 연결에서 Run 생성, 새 연결에서 동일 ID status/Resource 조회 | 동일 |
| TLS reverse proxy | 임시 기관 CA → HTTPS terminating proxy → loopback backend | `tests/integration/test_tls_reverse_proxy.py` |

Reference client는 end-user Host를 대신하지 않는다. protocol·TLS·재연결 회귀를 자동화하는 oracle이다.

## 4. MCP Inspector CLI

실행 환경은 Node `23.11.0`, Inspector `0.18.0`, endpoint `http://127.0.0.1:8765/mcp`다. 모든 invocation은 새 Inspector process이므로 후속 status/Resource 성공은 application state가 Host session에 종속되지 않음을 입증한다.

검증한 method:

```text
tools/list
tools/call psr.project.list
resources/templates/list
resources/read psr://projects/project-public-ai
prompts/list
prompts/get public_policy_research
tools/call psr.research.run.start
새 process: tools/call psr.research.run.status
새 process: resources/read psr://projects/<project-id>/runs/<run-id>
```

관찰 결과:

- Tool 5개, Resource template 2개, Prompt 1개가 canonical catalog와 일치했다.
- Tool 결과에서 `structuredContent`와 JSON text fallback이 함께 반환됐다.
- Prompt는 `project_id`, `question`, `as_of_date` argument로 실제 message를 반환했다.
- Run `0cd6eafa-4463-49ee-a156-1c8fffa79427`을 새 Inspector process에서 같은 ID와 `QUEUED` 상태로 조회했다.
- Inspector의 TLS client 동작은 이번 로컬 수동 검증에서 실행하지 않았다. server TLS 경로는 reference client test로 별도 통과했다.

재현 명령은 [Remote MCP Runbook](../runbooks/remote-mcp.md)에 있다.

## 5. Codex CLI bundled Host

글로벌 `/opt/homebrew/bin/codex` wrapper는 native binary 누락으로 실행되지 않아, 설치된 ChatGPT app bundle의 `/Applications/ChatGPT.app/Contents/Resources/codex`를 사용했다.

일회성·비영구 설정으로 다음을 검증했다.

- version: `codex-cli 0.144.2`
- `--ignore-user-config --ephemeral -s read-only`
- `mcp_servers.psr.url=http://127.0.0.1:8765/mcp`
- model이 `psr.project.list`를 실제 `mcp_tool_call` event로 호출
- structured/text 결과를 받은 뒤 `project-public-ai` 반환
- exit code `0`

Resource와 Prompt를 model-controlled Codex session에서 재검증하려는 실행은 로컬 내용을 외부 service로 보낼 수 있다는 approval review에 의해 거부됐다. 이 거부를 우회하지 않았다. ADR-0008 이후 두 primitive는 Codex Foundation 지원 계약의 필수 조건이 아니며 `NOT REQUIRED`로 기록한다. 향후 제품 필요가 생기면 별도 opt-in 보안 검토 후 검증한다.

## 6. 알려진 호환성 제한

1. Foundation은 `json_response=True`, `stateless_http=True`이며 SSE stream progress를 제공하지 않는다.
2. MCP experimental Tasks를 사용하지 않는다. durable `ResearchRun` ID가 application 수명주기를 담당한다.
3. process-local rate limiter는 단일 replica 방어선이다. 다중 replica의 global quota는 gateway에서 구현해야 한다.
4. Inspector CLI `--prompt-args`는 복수형 옵션이다. `--prompt-arg`는 URL target argument로 해석되어 실패한다.
5. 기관 IdP, 기관 신뢰 CA, WAF 제품에서의 실환경 검증은 Pilot onboarding 범위다.
6. 현재 Tool catalog는 Foundation 5개뿐이다. Evidence/Report Tool은 아직 구현되지 않았다.

## 7. 변경 시 재검증 조건

- `mcp`, `starlette`, `uvicorn`, OAuth middleware major/minor upgrade
- protocol version 또는 `stateless_http`/`json_response` 변경
- Tool/Resource/Prompt 이름·schema·annotation 변경
- gateway, TLS termination, public URL, Origin/Host policy 변경
- target Host version 변경

재검증 결과는 기존 행을 덮어쓰지 않고 날짜가 포함된 validation report와 함께 갱신한다.
