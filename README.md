# Public Sector Research MCP

누구나 가입 없이 공신력 있는 공공자료를 조사하고, 원문 근거가 연결된 결과를 받은 뒤 서버에는 질문·원문·보고서가 남지 않도록 만드는 Evidence-First Public Research MCP입니다.

> 현재 상태: OAuth·PostgreSQL·Tenant 기반 Foundation과 Public Safety Core가 구현됐습니다. 익명 `psr.service.policy`, 개발 fixture 기반 `psr.research.quick`, Government Planner v0, IP-first quota, ephemeral purge, SSRF URL 정책과 검증 IP 고정 SafeCollector가 동작합니다. 검색 provider·HTML/PDF parser·실제 Evidence Composer는 아직 연결되지 않았으므로 공개 리서치 완성품으로 배포하면 안 됩니다.

## 제품 성장 순서

```text
Public Preview
가입 없음 · 기본 무보관 · 제한된 공식자료 조사

→ 실제 저장 수요가 확인되면

Opt-in Account Beta
선택 가입 · 저장을 켠 조사만 History·재사용

→ 비용과 지불 의사가 확인되면

Paid Persistent
저장공간 · 장기실행 · 높은 quota

→ 팀·기관 수요가 확인되면

Enterprise
기관 SSO · Organization · Review · 감사 · 보존정책
```

## 왜 별도 저장소인가

이 프로젝트는 범용 탐색·수집 성능을 지향하는 기존 [`planned-web-crawling-skill`](https://github.com/Kminer2053/planned-web-crawling-skill)과 목적과 위험 모델이 다릅니다.

- 기존 저장소: 단일 사용자의 유연하고 강력한 조사형 크롤링 Skill
- 이 저장소: 다수 사용자가 안전하게 접근하는 공식자료 우선 공개 Research MCP

기존 `crawlkit.py`는 폐기하지 않습니다. command, output, PDF·HTML 처리, 실패 특성을 fixture로 고정한 뒤 fetch·parse·hash 중 안전하게 재사용할 부분만 `SafeCollector`와 parser adapter 뒤로 옮깁니다.

## 핵심 문서

- [VISION](./docs/VISION.md): 왜 만들며 어떤 순서로 성장하는가
- [PRD](./docs/PRD.md): Public Tool, 무보관, 선택 가입 요구사항
- [ARCHITECTURE](./docs/ARCHITECTURE.md): public/account/paid/enterprise mode와 구성요소
- [ROADMAP](./docs/ROADMAP.md): 공개 안전 기반부터 유료·기관 기능까지의 단계
- [IMPLEMENTATION PLAN](./docs/IMPLEMENTATION_PLAN.md): 다음 change set과 파일·interface·DoD
- [VALIDATION CRITERIA](./docs/VALIDATION_CRITERIA.md): PG0~PG3 공개 검증 게이트
- [FOUNDATION DETAILED DESIGN](./docs/DETAILED_DESIGN.md): 이미 구현된 로그인·Tenant 기반 상세설계
- [THREAT MODEL](./docs/security/THREAT_MODEL.md): Foundation과 Public Preview 위협
- [ADR](./docs/adr/): 주요 제품·아키텍처 결정

## 현재 구현된 Foundation

- Python 3.12와 MCP `2025-11-25` Streamable HTTP
- 5개 Project/Run Tool, 2개 Resource template, 1개 Prompt
- domain/application/storage adapter 분리
- PostgreSQL 17.10 migration, RLS, durable Job
- OAuth/OIDC JWT·JWKS·Membership
- request size·timeout·process-local rate boundary
- official SDK, MCP Inspector, Codex Tool conformance
- statement 95.02%, branch 87.10%, critical module 최소 95% coverage gate

이 기능은 Account Beta와 Enterprise의 자산으로 유지합니다. Public Preview 요청에는 OAuth 로그인, Organization, persistent content storage를 사용하지 않습니다.

## 현재 구현된 Public Safety Core

- `ServiceMode.PUBLIC_EPHEMERAL`
- OAuth·Membership·PostgreSQL content sink를 구성하지 않는 public container
- token 없이 호출하는 `psr.service.policy`
- token을 바꿔도 같은 IP 한도를 새로 얻지 못하는 HMAC IP-first limiter
- public production의 HTTPS·absolute ephemeral root·abuse key fail-closed 설정
- random workspace ID, directory `0700`, file `0600`
- path traversal·symlink·만료 workspace 접근 차단
- startup/periodic/final purge sweeper
- fake-clock 만료·corrupt lease·삭제·재시작 기반 test
- question/source/result canary를 쓰는 quick 실행 후 즉시 purge
- Government Profile v0의 법령·정책·조달·개인정보·국제표준 track
- HTTPS-only URL, userinfo·비표준 port·내부 DNS/IP 차단
- redirect별 DNS 재검증과 검증된 IP로 고정하는 HTTP/1.1 transport
- response byte·timeout·content-encoding 상한과 cookie header 제거

[S0 검증 보고서](./docs/validation/2026-07-16-public-s0.md)에 210개 전체 회귀와 coverage 증적을 기록했습니다.
[P1 기반 검증 보고서](./docs/validation/2026-07-16-public-p1-foundation.md)에 최신 281개 전체 회귀와 collector 검증을 기록했습니다.

## 다음 구현 범위

첫 구현은 crawler 연결이 아니라 공개 안전경계입니다.

1. official-first SearchProvider 1종과 source candidate model
2. HTML/JSON bounded parser와 document kind sniff
3. PDF parser 격리·page/byte/time budget
4. Evidence Composer와 SafeCollector를 실제 quick backend에 연결
5. edge client IP normalization과 end-to-end content leakage scan
6. start/status/result/cancel async flow

상세 순서는 [IMPLEMENTATION PLAN](./docs/IMPLEMENTATION_PLAN.md)을 따릅니다.

## Public Preview Tool 목표

```text
psr.research.quick
psr.research.start
psr.research.run.status
psr.research.run.result
psr.research.run.cancel
psr.service.policy
psr.feedback.submit
```

위 catalog는 목표 계약입니다. 현재 public server에는 `psr.service.policy`와
`psr.research.quick`만 구현돼 있습니다. quick은 개발 fixture를 명시적으로 켠 경우에만 동작하고,
production에서는 실제 backend가 연결될 때까지 `research_available=false`로 fail closed합니다.

## 무보관 약속

Public Preview에서 User Content는 다음을 뜻합니다.

- 사용자 질문과 검색어
- 수집한 HTML·PDF·JSON 원문
- 추출 Passage와 중간 분석
- 최종 보고서 본문

이 content는 결과 전달에 필요한 동안만 memory 또는 제한된 임시 작업공간에서 처리합니다. 결과 수령 후 60초, 미수령 결과 60분, orphan 작업공간 2시간을 절대 상한으로 하며 PostgreSQL과 일반 log에는 저장하지 않습니다.

## 공개 전 필수 게이트

- IP quota를 bearer·handle 회전으로 우회할 수 없음
- private/link-local/metadata endpoint와 redirect SSRF 차단
- request·download·parser·run·cost budget
- raw content 없는 log·trace·metric
- crash/restart/delete failure를 포함한 TTL purge
- 운영 kill switch
- citation 없는 FACT 0개
- 두 MCP Host에서 anonymous flow 검증

[VALIDATION CRITERIA](./docs/VALIDATION_CRITERIA.md)의 `PG0~PG3`가 모두 통과하기 전에는 public-ready 또는 zero-retention verified로 표현하지 않습니다.

## Foundation 로컬 검증

```bash
uv sync --all-groups --frozen
uv run --frozen ruff check .
uv run --frozen mypy src tests scripts
uv audit --preview-features audit --frozen
uv run --frozen pytest --cov=psr_mcp --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json
uv run --frozen python scripts/coverage_gate.py --coverage-json coverage.json
uv run --frozen psrctl doctor --json
```

이 명령은 현재 Foundation regression을 검증합니다. Public Preview 기능 완료를 증명하지 않습니다.

## 제품 판단 기준

가입자 수보다 다음을 먼저 봅니다.

- 완료 결과 수령률
- helpful 긍정률
- 공식 1차자료 비율
- FACT citation coverage
- TTL 이후 content 잔존 여부
- 조사당 비용
- 저장·History·재사용을 원하는 실제 사용자 수

사용자가 반복해서 저장을 원할 때만 선택 가입을 열고, 저장과 장기실행에 지불 의사가 확인된 뒤 유료화합니다.
