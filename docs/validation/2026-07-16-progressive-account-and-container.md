# Progressive Account Design and Public OCI Validation

> 날짜: 2026-07-16 · 환경: macOS arm64 local · 판정: **LOCAL PASS / OCI BUILD PENDING**

[ADR-0010](../adr/0010-progressive-identity-and-opt-in-persistence.md) ·
[Architecture](../ARCHITECTURE.md) · [Implementation Plan](../IMPLEMENTATION_PLAN.md) ·
[Container Runbook](../runbooks/container-public-preview.md)

## 1. 변경 목적

제품 방향을 다음 순서로 고정했다.

```text
영구 익명 Public Preview
→ 실제 반복·저장 수요
→ 무료 선택 Account Beta
→ opt-in save + freshness-aware Evidence reuse
→ 비용·지불의사·보안 검증
→ Paid Persistent
```

Account는 공개 MCP 사용권이 아니며, Public endpoint와 별도 deployment/data sink로 둔다.
가입·저장·reuse 구현은 R4 Product Validation Gate 전 시작하지 않는다.

## 2. 설계 검증

반영한 계약:

- 신규 계정 기본 `retention_mode=ephemeral`, `reuse_mode=off`
- `reuse_mode=off|prefer_fresh|saved_only`
- fresh/stale/unknown 판정과 reused/new Evidence provenance
- 삭제한 Evidence와 cross-user Evidence의 재사용 금지
- 익명 결과 자동 소급 귀속 금지, 명시적 `user_imported` provenance
- 초기 무료·제한 quota의 관심 사용자 Beta
- Account 장애 중 anonymous Public conformance 유지

문서 점검:

- Markdown 파일 44개 상대링크 누락 0
- unbalanced code fence 0
- `git diff --check` PASS
- PRD `FR-ACC-001~015` → A0.1~A0.3 → `VAL-ACC-001~023` 추적

## 3. OCI Artifact

추가:

- pinned multi-stage `Dockerfile`
- `.dockerignore`
- `scripts/verify_container_contract.py`
- `scripts/container_smoke.py`
- GitHub Actions `Public Preview OCI gate`
- [Container Runbook](../runbooks/container-public-preview.md)

정적 계약:

- official Python 3.12.13 slim Bookworm digest pin
- final runtime user `10001:10001`
- production/public/static/memory fail-closed 기본값
- Account DB/OAuth/persistent storage env 미포함
- `VOLUME`, `HEALTHCHECK`, `ADD`, whole-repository `COPY` 금지
- CI read-only root, all capabilities drop, no-new-privileges, tmpfs only
- network-none development fixture conformance
- smoke 뒤 ephemeral root empty

## 4. 실행 결과

```text
container contract: PASS
targeted tests: 72 passed
non-PostgreSQL regression: 467 passed
full regression: 492 passed
raw coverage: 95.13%
normalized statement coverage: 96.24%
branch coverage: 90.75%
critical module statement minimum: 95.00%
ruff: PASS
format: PASS
mypy: PASS (152 files)
dependency audit: 53 packages, known vulnerability 0
dependency license manifest: current
wheel/sdist offline build: PASS
wheel entrypoints: psr-mcp, psrctl
workflow YAML parse: PASS
```

PostgreSQL 17.10 임시 cluster로 25개 PostgreSQL test를 포함해 실행했고 종료 후 cluster process가
남지 않도록 정리했다.

## 5. Content Retained

- 사용자 질문·검색어·원문·결과: 저장 0
- 테스트 DB: fixture만 사용
- `/tmp/psr-container-dist`: source code wheel/sdist만 존재, User Content 없음
- container runtime content: 로컬 Docker engine이 없어 생성되지 않음

## 6. 아직 검증하지 않은 것

현재 로컬 환경에는 Docker, Podman, nerdctl과 buildctl이 없다. 따라서 다음은 코드와 CI 계약만
작성됐고 실제 PASS가 아니다.

- OCI test/runtime image build
- Linux numeric user와 tmpfs mount 실제 동작
- read-only root write denial
- container 내부 official SDK smoke
- image architecture별 amd64/arm64 build
- image vulnerability/SBOM scan

이 항목은 GitHub Actions의 `Public Preview OCI gate`가 실제로 통과한 뒤
`VAL-PUB-EDGE-012 PASS`로 승격한다.

또한 다음 외부 gate는 계속 PENDING이다.

- TLS reverse proxy/WAF
- canonical client IP overwrite와 spoof rehearsal
- egress/private-route 검증
- provider hard cap
- staging purge canary와 kill-switch game day
- 공공업무 담당자 human usefulness QA
- 두 MCP Host
- 프로젝트 LICENSE/NOTICE 결정

## 7. 판정

설계와 로컬 Python artifact는 PASS다. Account 기능은 구현하지 않았고 Public 경로에 Account
dependency를 추가하지 않았다. OCI artifact는 구현됐지만 실제 engine/CI 실행 전이므로
Public Preview 배포 완료 또는 `VAL-PUB-EDGE-012 PASS`로 표현하지 않는다.
