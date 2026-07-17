# ROADMAP — Product Stages and Branches

[VISION](VISION.md) · [PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [BRANCH STRATEGY](BRANCH_STRATEGY.md)

## Stage 1 — Universal Local Skill

브랜치: `main`

- Agent Skills 표준 폴더
- Codex·Claude metadata
- 로컬 Python Core/CLI
- Government profile
- SQLite·filesystem Evidence Store
- HTML·JSON·TEXT·PDF 처리
- Evidence Score와 citation-safe `brief.json`
- 한국어 Markdown + self-contained interactive HTML report
- 근거 팝업·상호링크·원문 이동·반응형·인쇄 레이아웃
- 메뉴·푸터·폼 등 비본문 근거 제외
- 로컬 Memory와 snapshot 재사용

완료 기준은 [VALIDATION](VALIDATION.md)의 Main Gate다.

## Stage 2 — Local MCP Adapter

브랜치: `product/local-mcp-adapter`

- stdio 또는 localhost MCP adapter
- 중앙 서버 저장 없음
- 동일 `.psr/` 프로젝트 사용
- MCP Tool/Resource schema
- 최소 2개 호스트 conformance

Core 로직을 복제하지 않고 `main`을 정기 병합한다.

## Stage 3 — Hosted Public Preview

브랜치: `product/hosted-public-preview`

- 가입 없는 제한적 공개 MCP/API
- 서버 기본 무보관
- 임시 workspace와 purge
- abuse·cost·SSRF·quota·kill switch
- 공식자료 범위와 사람 유용성 검증

이전 구현은 `archive/mcp-public-preview-2026-07-16`에서 선택적으로 이식한다.

## Stage 4 — Account Beta

브랜치: `product/account-beta`

- 선택 가입
- 사용자 저장 동의
- 조사 History와 freshness-aware reuse
- 삭제·export·보존정책
- 계정 장애와 익명 공개 기능 분리

## Stage 5 — Paid Persistent

브랜치: `product/paid-persistent`

- 저장공간·장기실행·높은 quota
- 비용·결제·복구·백업
- Living Report와 Diff Detection
- 팀 공유 전 개인 저장의 보안성 검증

## Stage 6 — Enterprise

브랜치: `product/enterprise`

- 기관 SSO
- Organization·RBAC
- Review·Audit
- 기관 보존정책
- 고급 Knowledge Graph와 영향분석

## 승격 원칙

사용자 수요와 검증 증거가 확인되기 전에는 다음 단계 코드를 `main`에 병합하지 않는다. 공통 Core 개선만 `main`에서 개발하고, 서비스·저장·과금·기관 기능은 해당 제품 브랜치가 소유한다.
