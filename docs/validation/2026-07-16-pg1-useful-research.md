# PG1 Useful Research — 로컬 수직 슬라이스 검증 보고서

> 날짜: 2026-07-16 · 대상 branch: `codex/foundation-vertical-slice` ·
> 판정: **LOCAL IMPLEMENTATION PASS / LIVE OFFICIAL-SOURCE VALIDATION PENDING**

[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Implementation Plan](../IMPLEMENTATION_PLAN.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 판정

Planner→Search candidate→robots policy→SafeCollector→MIME sniff→HTML/JSON/PDF parser→
Evidence Score/Citation→Markdown/JSON→ephemeral purge의 로컬 결정론적 수직 슬라이스는
통과했다.

이 판정은 다음을 의미하지 않는다.

- 실제 공공 웹에서 충분히 유용한 정책 답변을 생성했다.
- Brave 또는 다른 Search provider의 production credential을 검증했다.
- 모든 source 약관·저작권을 자동 판정한다.
- PG0, PG2, PG3 또는 public-ready 상태다.
- 외부 provider까지 포함한 Zero Data Retention이 검증됐다.

## 2. 구현 범위

### Search

- Government Profile track별 병렬 query
- official domain suffix를 보존하는 query builder
- 법령·조달·개인정보·정부·국제표준 official domain registry
- 선택형 Brave adapter
- query 길이·결과 수·timeout·response byte·동시성 제한
- auth/rate/network/malformed response typed failure
- Search result를 Evidence가 아닌 candidate로 유지

### Source access와 collection

- HTTPS, 443, no-userinfo, public DNS/IP, redirect 재검증
- 검증된 IP로 TCP를 고정하고 원래 domain으로 TLS SNI/Host 유지
- client bearer/cookie 미전달
- response byte·timeout·redirect·encoding 상한
- `robots.txt`를 동일 SafeCollector로 먼저 수집
- 404/410 robots는 allow, 401/403은 disallow, 기타 실패는 unavailable
- 일부 source 실패를 Run 전체 실패로 승격하지 않는 partial semantics

### Parser

- magic/MIME sniff와 declared mismatch warning
- HTML active content 무시와 heading/element locator
- JSON bounded traversal과 JSON Pointer
- text line-range locator
- PDF subprocess 격리와 page locator
- scanned PDF `OCR_REQUIRED`
- password PDF `ENCRYPTED_DOCUMENT`
- malformed/empty/resource-limit typed failure

### Evidence와 출력

- URL, passage, document SHA-256 중복 제거
- track-balanced citation 선택
- local stable citation ID와 locator/excerpt/SHA-256
- authority, primary source, direct relevance, original snapshot, specificity,
  freshness, independence component와 설명
- login/CAPTCHA/access-denied/error/too-short document 제외
- citation 없는 FACT를 만들지 않는 output contract
- Markdown/JSON에 동일 citation ID와 score
- workspace purge 확인 뒤 quick 결과 반환

## 3. 자동 검증 결과

### 전체 회귀

```text
397 passed in 13.61s
```

여기에는 PostgreSQL 17 로컬 클러스터를 사용하는 25개 test가 포함된다. Public code 추가 뒤에도
OAuth, tenant RLS, durable Job과 Foundation contract가 유지됐다.

### Coverage

```text
pytest raw total coverage: 94.95%
coverage gate normalized statement: 96.11%
coverage gate branch: 90.31%
critical module statement minimum: 95.0%
status: pass
```

subprocess PDF worker는 별도 process에서 실행되므로 parent coverage 원시표에는 0%로 보이지만,
parent/worker 성공·timeout·exit·malformed payload와 PDF core failure는 직접 test한다.

### 정적·공급망

```text
ruff check: PASS
ruff format --check: PASS
mypy strict: PASS (135 source files)
uv lock --check: PASS
dependency license manifest: PASS
uv audit: 53 packages, known vulnerability 0
```

새 runtime dependency는 `pypdf==6.14.2`, license는 `BSD-3-Clause`로 manifest에 반영했다.

## 4. Acceptance 증거

| 영역 | 관찰 결과 | 판정 |
|---|---|---|
| 필수 track | AI 구매 질문의 모든 Planner track에 candidate·citation fixture 제공 | PASS/local |
| 공식 source 우선 | `OFFICIAL_PRIMARY`가 같은 track의 낮은 tier보다 우선 | PASS |
| citation | 모든 FACT가 citation 1개 이상 보유 | PASS |
| locator | HTML, JSON, text, PDF locator fixture 일치 | PASS |
| score | total 단독이 아닌 7개 component와 설명 | PASS |
| dedup | canonical URL, passage, document hash 중복 제외 | PASS |
| 부분 실패 | Search timeout, private IP, invalid PDF, login page를 보고하고 성공 근거 보존 | PASS |
| robots | disallow, no-file, restricted, unavailable 정책 | PASS/local |
| purge | quick workspace 접근 차단·삭제 뒤 결과 반환 | PASS/local |
| 실제 공식 웹 | production provider credential로 실행하지 않음 | PENDING |
| 업무 답변 유용성 | 보수적 evidence bundle까지만 검증, domain synthesis human QA 없음 | PENDING |
| site terms | robots 외 사이트별 약관 자동판정 없음 | PENDING/operational |

## 5. External Provider 경계

Brave adapter는 기본 `disabled`이며 이 검증에서 실제 외부 호출을 하지 않았다. 활성화하면
질문에서 생성한 검색어를 Brave Search API로 보낸다. PSR은 그 검색어와 Search result를 저장하지
않지만 표준 provider 정책은 query를 최대 90일 보관할 수 있다. 따라서 현재 제품 표현은
`PSR server zero-retention`으로 제한하고, end-to-end ZDR을 주장하지 않는다.

Search result는 memory의 candidate로만 사용하고 원문 URL을 SafeCollector로 다시 수집한다.
provider 결과 자체를 persistent index나 재배포 bundle에 저장하지 않는다.

운영 승인 전에는
[Brave API privacy policy](https://api-dashboard.search.brave.com/privacy-policy)와
[terms of service](https://api-dashboard.search.brave.com/terms-of-service)를 당시 버전으로
다시 검토한다.

## 6. 남은 위험

1. 실제 source는 fixture보다 URL 구조, 403, robots, PDF 품질과 개정표시가 복잡하다.
2. 현재 finding은 원문 구간을 확인했다는 보수적 문장이다. 정책 초안으로 바로 쓸 수 있는
   claim/recommendation synthesis는 아직 품질검증하지 않았다.
3. 의미 기반 conflict, 법령 현행성·법적 성격 판정은 구현되지 않았다.
4. site별 Terms/저작권 허용범위는 robots만으로 해결되지 않는다.
5. trusted edge IP, 일일 비용상한, multi-replica quota가 없다.
6. async result lifecycle과 feedback이 없다.

## 7. 다음 Gate

다음 순서는 `CH-P1.8 Live Official-Source Validation`이다.

1. 운영자가 승인한 Search provider credential 또는 official-source seed adapter 준비
2. GR-001~004를 실제 공식 source로 실행
3. 공공업무 담당자가 citation·원문·gap과 결과 유용성을 검토
4. generic evidence bundle이 부족하면 citation-constrained Writer를 먼저 구현
5. 이후 edge/비용 경계를 닫고 PG0·PG1의 정식 판정을 갱신

credential은 repository, validation report, log와 MCP output에 기록하지 않는다.
