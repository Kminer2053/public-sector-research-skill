# Public Quick / Planner / SafeCollector 기반 검증 보고서

> 날짜: 2026-07-16 · 상태: PASS for implemented scope · Public Preview release는 아직 불가

[Implementation Plan](../IMPLEMENTATION_PLAN.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Legacy Characterization](../analysis/legacy-crawlkit-characterization.md)

## 1. 구현 범위

- 익명 `psr.research.quick` Tool schema
- deterministic Government Planner v0
- source, byte, time stop condition
- 개발 전용 fixture research backend
- question/source/extracted/result ephemeral artifact lifecycle
- 결과 반환 전 access block과 purge 확인
- timeout, unavailable backend, purge failure, kill switch typed error
- question/source/result content canary log·결과 비노출
- HTTPS-only `UrlPolicy`
- userinfo, non-443 port, internal hostname, private/link-local/metadata IP 차단
- redirect별 URL·DNS·IP 재검증
- 검증된 IP에만 연결하는 `PinnedNetworkBackend`
- 원 domain TLS SNI와 HTTP Host 유지
- response byte/time/content-encoding limit와 header allowlist
- legacy crawlkit source hash와 reuse/refactor/replace characterization
- 선택 가입·opt-in persistence ADR-0010
- 미구현 Account/Paid/Enterprise mode startup fail-closed

## 2. 검증 결과

| 검증 | 결과 |
|---|---|
| Ruff | PASS |
| Mypy strict | PASS, 103 source files |
| 전체 test | PASS, 281 |
| PostgreSQL 17 / OAuth regression | PASS |
| MCP local TCP/TLS regression | PASS |
| 새 collector/planner/public targeted coverage | statement·branch 100% |
| 전체 statement coverage gate | 96.31% |
| 전체 branch coverage gate | 88.69% |
| critical statement minimum | 모든 critical module 95% 이상 |
| `uv.lock --check` | PASS |
| `git diff --check` | PASS |

전체 회귀에는 UTF-8 임시 PostgreSQL cluster, OAuth/JWKS fixture, MCP SDK reconnect와 TLS
terminating reverse proxy test가 포함됐다. 임시 PostgreSQL process는 검증 후 중지했다.

## 3. 확인한 보안·무보관 동작

- quick 결과는 workspace purge 성공 뒤에만 반환된다.
- purge가 예외 또는 불확정 결과를 내면 `PURGE_PENDING`을 반환하고 access를 차단한다.
- timeout, backend exception과 unavailable 상태에서도 workspace cleanup을 시도한다.
- production public mode는 fixture backend를 활성화할 수 없다.
- backend가 없는 production policy는 `research_available=false`다.
- 질문 canary와 source/result canary가 structured result와 log에 나타나지 않는다.
- redirect 대상이 private address면 두 번째 HTTP request 전에 차단한다.
- DNS answer에 public/private IP가 섞여 있어도 전체 host를 거부한다.
- TCP connection은 승인된 IP로 고정되고 TLS SNI/Host는 원 domain을 유지한다.
- `Set-Cookie`는 collector output에 포함되지 않는다.
- response length header와 streaming body 모두 byte limit을 적용한다.

## 4. 현재 제품 동작

### Development

`PSR_PUBLIC_FIXTURE_RESEARCH_ENABLED=true`일 때 quick lifecycle을 실행할 수 있다. 반환 결과는
외부 사실이 아닌 fixture임을 `FIXTURE_ONLY`, `PARTIAL`, gap으로 명시한다.

### Production

fixture는 startup validation에서 금지된다. 실제 Search·Parser·Evidence backend가 아직 없으므로
`psr.service.policy.research_available=false`이며 quick 호출은 `RESEARCH_NOT_AVAILABLE`로 실패한다.
따라서 현재 상태를 실제 공개 조사 서비스로 배포하지 않는다.

## 5. 미완료 범위

- official-first SearchProvider와 query generation
- source authority/profile registry
- magic-byte document kind sniff
- bounded HTML/JSON parser
- PDF parser 격리, page/time/memory limit, OCR 상태
- Evidence Composer, citation locator와 FACT coverage
- SafeCollector를 실제 quick backend에 연결
- edge client IP normalization과 spoof 방지
- deletion retry backoff/alert
- public async start/status/result/cancel
- 실제 공식자료 golden scenario와 외부 canary

## 6. Content Retained

- 사용자 실제 질문·원문·보고서: 없음
- test fixture content: 임시 pytest directory와 workspace에서 test 종료 시 제거
- persistent application DB content: synthetic Foundation test data만 임시 PostgreSQL에 생성
- 임시 PostgreSQL process: 중지 완료
- 일반 log: content canary 미검출

## 7. 다음 Gate

1. SearchProvider port와 official candidate fixture
2. MIME/magic-byte sniff와 HTML/JSON parser
3. Evidence Composer v0
4. SafeCollector-backed quick backend
5. 공공기관 AI 구매 원칙 golden scenario

이 다섯 항목을 완료한 뒤 `PG1 Useful Research`를 판정한다.
