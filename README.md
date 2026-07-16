# Public Sector Research MCP

공공분야 업무종사자가 MCP 호환 AI 클라이언트에서 공식 자료 중심의 조사를 계획하고, 원문 근거를 검토·재사용하며, 감사 가능한 보고서를 만들 수 있게 하는 Evidence-First Research MCP입니다.

> 상태: Foundation F0~F4 구현을 완료했습니다. PostgreSQL 17.10 local `G3`, OAuth/Membership local `G4`, 공식 SDK·MCP Inspector 전체 conformance와 Codex Tool 호환성을 검증해 capability-aware `G5`를 통과했습니다. 실제 기관 환경과 독립 owner 승인이 필요한 `G6`는 열려 있습니다.

## 왜 별도 저장소인가

이 프로젝트는 범용 탐색·수집 성능을 지향하는 기존 [`planned-web-crawling-skill`](https://github.com/Kminer2053/planned-web-crawling-skill)과 목적, 사용자, 위험 모델이 다릅니다.

- 기존 저장소: 단일 사용자의 유연한 조사형 크롤링 Skill
- 이 저장소: 공공분야 다중 사용자를 위한 공식자료 우선 Research MCP 서비스

기존 `crawlkit.py`의 fetch·parse·hash 원리는 검토 후 선택적으로 재사용하지만, 코드를 그대로 복제하거나 기존 Skill의 정책을 제품 정책으로 간주하지 않습니다.

## 핵심 문서

- [VISION](./docs/VISION.md): 제품 정체성과 공공분야 가치
- [PRD](./docs/PRD.md): 사용자·기능·MCP 계약·Acceptance Criteria
- [ARCHITECTURE](./docs/ARCHITECTURE.md): 원격 MCP, 다중 사용자, 증거 저장·보안 설계
- [ROADMAP](./docs/ROADMAP.md): MVP부터 공공분야 운영 확장까지의 구현 순서
- [DETAILED DESIGN](./docs/DETAILED_DESIGN.md): Foundation vertical slice의 실행 가능한 상세설계
- [IMPLEMENTATION PLAN](./docs/IMPLEMENTATION_PLAN.md): 작업 패키지·순서·완료 정의
- [VALIDATION CRITERIA](./docs/VALIDATION_CRITERIA.md): 테스트·보안·호환성 검증 게이트
- [FOUNDATION VALIDATION REPORT](./docs/validation/2026-07-16-foundation-core.md): `G0~G2` 실행 결과와 미검증 범위
- [POSTGRESQL G3 REPORT](./docs/validation/2026-07-16-postgresql-g3.md): RLS·동시성·복구·backup/restore 검증
- [POSTGRESQL RUNBOOK](./docs/runbooks/postgresql.md): role·migration·backup·restore 운영 절차
- [OAUTH G4 REPORT](./docs/validation/2026-07-16-oauth-g4.md): JWT·Membership·RFC 9728 검증
- [OAUTH RUNBOOK](./docs/runbooks/oauth-resource-server.md): IdP 설정·key rotation·폐기·장애 대응
- [REMOTE MCP RUNBOOK](./docs/runbooks/remote-mcp.md): TLS proxy·Host conformance·원격 장애 대응
- [HOST MATRIX](./docs/compatibility/host-matrix.md): SDK·Inspector·Codex primitive별 실제 검증 결과
- [THREAT MODEL](./docs/security/THREAT_MODEL.md): Foundation 위협·통제·잔여위험
- [DATA DICTIONARY](./docs/data/DATA_DICTIONARY.md): 실제 PostgreSQL schema와 데이터 의미
- [REMOTE G5 REPORT](./docs/validation/2026-07-16-remote-g5.md): F4 실행 증적과 capability-aware G5 판정
- [COVERAGE GATE AUDIT](./docs/validation/2026-07-16-foundation-coverage-audit.md): statement·branch·critical module 독립 기준 검증
- [ADR](./docs/adr/): 구현 결정을 고정하는 Architecture Decision Records

## 프로토콜 기준

2026-07-16 현재 MCP 안정 사양인 `2025-11-25`를 기준으로 합니다. `2026-07-28` Release Candidate의 stateless transport 변화는 별도 adapter와 ADR로 추적하며, 안정 사양이 되기 전에는 운영 기준으로 고정하지 않습니다.

## 제품 원칙

```text
Official Sources First
Evidence Before Conclusions
Human Approval for Accountable Decisions
Tenant Isolation by Default
MCP-First, Client-Agnostic
Traceable, Reproducible, Reusable
```

## 현재 범위

저장소 분리와 제품설계를 마치고 Foundation의 `G0~G2`, PostgreSQL 17.10 local `G3`, OAuth/Membership local `G4`, capability-aware Host conformance `G5`를 통과했습니다. 현재 구현은 다음을 포함합니다.

- Organization 범위의 Project 조회와 authorization policy
- 승인된 Plan fixture를 통한 idempotent ResearchRun 생성·조회·취소
- lease·heartbeat·reclaim·retry exhaustion을 갖춘 in-memory Job model
- 5개 Tool, 2개 Resource template, 1개 Prompt를 제공하는 MCP Streamable HTTP server
- production에서 static auth 또는 memory storage를 거부하는 fail-closed configuration
- Psycopg 기반 PostgreSQL repository, tenant RLS, worker lease와 Alembic migration
- OIDC JWT 검증, RFC 9728 metadata, tenant Membership binding과 least-privilege runtime role
- bounded request size·timeout·rate limit, request ID, canonical Host/Origin policy
- official SDK TCP/TLS reverse-proxy conformance와 `psrctl conformance`
- OSV dependency audit, cross-platform license manifest, CI SBOM generation

로컬 검증은 다음 명령으로 재현할 수 있습니다.

```bash
uv sync --all-groups --frozen
uv run --frozen ruff check .
uv run --frozen mypy src tests scripts
uv audit --preview-features audit --frozen
uv run --frozen python scripts/dependency_licenses.py --check
uv run --frozen pytest --cov=psr_mcp --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json
uv run --frozen python scripts/coverage_gate.py --coverage-json coverage.json
uv run --frozen psrctl doctor --json
uv run --frozen psrctl serve mcp
```

서버가 실행된 상태에서 `psrctl conformance` 또는 `scripts/http_smoke.py`로 공식 Python SDK 기반 검증을 실행할 수 있습니다. OAuth/PostgreSQL 모드는 [OAuth runbook](./docs/runbooks/oauth-resource-server.md), TLS/Host 검증은 [Remote MCP runbook](./docs/runbooks/remote-mcp.md)을 따릅니다. Codex는 [ADR-0008](./docs/adr/0008-capability-aware-host-conformance.md)에 따라 Tool-first 지원 대상으로 판정합니다. 실제 기관 IdP/gateway와 독립 owner 승인이 끝나기 전에는 Foundation 전체 또는 production-ready로 선언하지 않습니다. 기존 crawler 코드의 이동·리팩터링은 Foundation 전체 gate 이후 작업 패키지에서 시작합니다.
