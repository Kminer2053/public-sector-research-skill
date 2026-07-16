# Branch Strategy

## 영구 브랜치

| 브랜치 | 책임 |
|---|---|
| `main` | 범용 Agent Skill과 provider-neutral local Core |
| `product/local-mcp-adapter` | 사용자 PC에서 실행되는 MCP adapter |
| `product/hosted-public-preview` | 익명 공개·무보관 서버 |
| `product/account-beta` | 선택 가입·저장·재사용 |
| `product/paid-persistent` | 유료 저장·장기실행 |
| `product/enterprise` | 기관 SSO·조직·감사 |
| `archive/mcp-public-preview-2026-07-16` | 기존 원격 MCP 구현 보존 |

## 개발 규칙

1. 범용 Core 변경은 `codex/<topic>` 또는 `feature/<topic>`을 `main`에서 분기한다.
2. 제품 기능은 해당 `product/*` 브랜치에서 feature branch를 만든다.
3. `main`은 제품 브랜치로 정기 forward-merge한다.
4. 서버·인증·PostgreSQL·과금 dependency를 `main`으로 back-merge하지 않는다.
5. Core가 제품 브랜치에서 먼저 개선됐으면 provider-neutral 부분만 별도 commit으로 `main`에 cherry-pick한다.
6. release tag는 `skill-vX.Y.Z`, `local-mcp-vX.Y.Z`, `hosted-vX.Y.Z`처럼 제품을 구분한다.
7. archive 브랜치는 새 개발을 받지 않는다.

## 승격 Gate

- `main`: Skill validation, CLI E2E, offline reuse, partial failure
- `product/local-mcp-adapter`: MCP schema와 2-host conformance
- `product/hosted-public-preview`: purge·abuse·cost·security·human usefulness
- `product/account-beta`: consent·deletion·isolation·freshness reuse
- `product/paid-persistent`: backup·restore·billing·retention
- `product/enterprise`: SSO·RBAC·audit·institutional review
