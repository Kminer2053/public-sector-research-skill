# PG1 Useful Research — 로컬 수직 슬라이스·curated live smoke 검증 보고서

> 날짜: 2026-07-16 · 대상 branch: `codex/foundation-vertical-slice` ·
> 판정: **LOCAL IMPLEMENTATION PASS / LIVE FIXED-SOURCE EVIDENCE PASS /
> CURATED END-TO-END SMOKE PASS / HUMAN QA PENDING**

[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Implementation Plan](../IMPLEMENTATION_PLAN.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 판정

Planner→Search candidate→robots policy→SafeCollector→MIME sniff→HTML/JSON/PDF parser→
Evidence Score/Citation→Markdown/JSON→ephemeral purge의 로컬 결정론적 수직 슬라이스는
통과했다.

추가로, 고정된 실제 공식 URL을 probe-first 방식으로 수집한 뒤 저장 snapshot을 네트워크 없이
재파싱하여 법령·정부정책·조달·개인정보·국제표준·데이터권리·업체종속 7개 track의 Evidence
선택을 검증했다. 이 검증은 Search provider의 검색 품질이나 최종 정책 초안의 사람 검토를
대체하지 않는다.

또한 `PSR_SEARCH_PROVIDER=curated`의 실제 public composition으로 같은 질문을 실행해
reviewed seed→robots→수집→파싱→Evidence→Markdown/JSON→purge 전체 경로를 확인했다.

이 판정은 다음을 의미하지 않는다.

- 실제 공공 웹 검색부터 충분히 유용한 정책 답변 생성까지 전 과정을 승인했다.
- Brave 또는 다른 Search provider의 production credential을 검증했다.
- 모든 source 약관·저작권을 자동 판정한다.
- PG0, PG2, PG3 또는 public-ready 상태다.
- 외부 provider까지 포함한 Zero Data Retention이 검증됐다.

## 2. 구현 범위

### Search

- Government Profile track별 병렬 query
- official domain suffix를 보존하는 query builder
- 법령·조달·개인정보·정부·국제표준 official domain registry
- 한국 공공부문 AI 조달 질문에 한정된 no-key curated source provider
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
- 동일 URL이 여러 track에 쓰이면 network fetch·parse 1회 후 track provenance 재연결

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
- 하나의 원문이 여러 track을 지지할 때 track 연결을 보존하는 중복 제거
- Government Profile track별 한·영 Evidence 선택어와 구문 중심 passage 선택
- local stable citation ID와 locator/excerpt/SHA-256
- authority, primary source, direct relevance, original snapshot, specificity,
  freshness, independence component와 설명
- login/CAPTCHA/access-denied/error/too-short document 제외
- 국가법령정보센터 동적 shell처럼 본문이 빠진 페이지를
  `DYNAMIC_CONTENT_MISSING`으로 제외
- NIST 공식 publication 경로와 NIST가 단순 호스팅한 저자 미확인 문서를 보수적으로 구분
- citation 없는 FACT를 만들지 않는 output contract
- 사전 검토된 anchor group이 모두 있을 때만 조달 원칙 후보를 만드는 Writer
- Markdown/JSON에 동일 citation ID, `track_id`와 score
- workspace purge 확인 뒤 quick 결과 반환

## 3. 실제 공식 원문 검증

검증 질문:

```text
공공기관 AI 구매 원칙에 데이터 권리, 학습 재사용, 업체 종속,
개인정보와 사람의 감독 조건을 포함해줘
```

probe 결과는 `/tmp`에만 임시 저장했고 repository에는 원문을 복사하지 않았다.

| Track | 실제 source | 선택 결과 |
|---|---|---|
| 법령·규정 | 국가법령정보센터 인공지능기본법 제34조 조문정보 | `html:p[6]`, 사람의 관리·감독 |
| 정부 정책 | 개인정보보호위원회 안내서 공개 보도자료 | `html:td[7]`, 생애주기별 법적 고려·안전기준 |
| 개인정보 | 개인정보위 생성형 AI 개인정보 처리 안내서 PDF | `pdf:page:40`, 학습 고지·옵트아웃·보유·파기 |
| 데이터 권리 | 같은 개인정보위 PDF | `pdf:page:40`, 학습 재사용과 선택권·파기정책 |
| 국제표준 | NIST AI RMF 1.0 PDF | `pdf:page:20`, monitoring·shutdown·human intervention |
| 조달·계약 | WEF `AI Procurement in a Box` NIST-hosted copy | `pdf:page:19`, 데이터 삭제·접근·소유권 |
| 업체 종속 | 같은 WEF 문서 | `pdf:page:26:chunk-1`, interoperability·open licensing·vendor lock-in |

관찰 결과:

- 7개 필수 track 모두 최소 1개 citation을 확보했다.
- composer는 최대 12개 citation을 반환했고 gap은 0개였다.
- 한국어 질문으로 영문 PDF의 `data ownership`, `human intervention`,
  `vendor lock-in` 구간을 선택했다.
- 동일 PDF를 개인정보/데이터권리 또는 조달/업체종속에 재사용해도 한 track이 사라지지 않았다.
- `nist.gov/system/files/...`의 WEF 문서는 NIST 1차자료가 아니라
  `OFFICIAL_SECONDARY`와 “NIST 호스팅 자료” 경계로 취급한다.
- 국가법령정보센터 `lsInfoP.do`는 일반 HTTP 수집에서 조문 본문이 빠진 shell만 반환했다.
  해당 shell은 Evidence에서 제외하고, 정적 조문정보 URL은 정상 Evidence로 처리했다.

snapshot SHA-256:

```text
law article 34  e1e80c9f0d764e82c079641102a4e10e5c051b286e6a969758dabefd31f75fcc
PIPC press page 8242a64ed09f9ddaeaa9ba1deda0821b8d115206f921bbd57ae858e87249dbcb
PIPC guide PDF  e9b5b0f8bc1b93e473847597315fb84ff61b9c4f63ebd435b157cb869f8b06cb
NIST AI RMF     7576edb531d9848825814ee88e28b1795d3a84b435b4b797d3670eafdc4a89f1
WEF procurement a117707bb4dd6e5f3e7b798bef218dc58576b7a38e20356c257aacad39946e13
```

## 4. Curated 실제 quick smoke

실행 명령:

```bash
uv run --frozen python scripts/live_curated_smoke.py
```

관찰 결과:

```text
status: PARTIAL
source_discovery: curated_seed
tracks: 7
citations: 12
findings: FACT 12, RECOMMENDATION 5, INFERENCE 0
recommendation tracks: law-regulation, privacy, data-rights, international-standards, vendor-lock-in
citation track recall: 7/7
source hosts: law.go.kr, pipc.go.kr, nist.gov, tsapps.nist.gov
failure codes: 0
gaps: 1 (실시간 검색이 아닌 curated 범위 제한)
server_saved: false
purge_state: PURGED
ephemeral directory empty: true
```

`PARTIAL`은 수집 실패가 아니라 curated mode가 실시간·범용 검색이 아니라는 의도적 limitation
때문이다. 개인정보위 PDF와 WEF PDF는 각각 두 track에 쓰였지만 실제 network fetch는 URL당
한 번만 수행했다. 정부정책·조달 track은 이번에 선택된 excerpt가 Writer의 모든 anchor를
충족하지 않아 권고안을 만들지 않고 FACT만 보존했다.

사람이 읽는 형태의 내부 검토에서 법령 원문의 `사람의 관리ㆍ감독`에 쓰인 한글 아래아
가운데점(`ㆍ`)이 정규화되지 않아 법령 권고가 누락되는 문제를 찾았다. separator 정규화와
회귀 test를 추가한 뒤 law-regulation 권고가 생성되는 것을 실제 원문으로 재확인했다.

## 5. 자동 검증 결과

### 전체 회귀

```text
415 passed (390 non-PostgreSQL + 25 PostgreSQL)
```

여기에는 PostgreSQL 17 로컬 클러스터를 사용하는 25개 test가 포함된다. Public code 추가 뒤에도
OAuth, tenant RLS, durable Job과 Foundation contract가 유지됐다.

### Coverage

```text
pytest raw total coverage: 95.03%
coverage gate normalized statement: 96.16%
coverage gate branch: 90.54%
critical module statement minimum: 95.0%
status: pass
```

subprocess PDF worker는 별도 process에서 실행되므로 parent coverage 원시표에는 0%로 보이지만,
parent/worker 성공·timeout·exit·malformed payload와 PDF core failure는 직접 test한다.

### 정적·공급망

```text
ruff check: PASS
ruff format --check: PASS
mypy strict: PASS (140 checked Python files)
uv lock --check: PASS
dependency license manifest: PASS
uv audit: 53 packages, known vulnerability 0
uv build: wheel + source distribution PASS
clean wheel install + `psrctl --help` + Writer import: PASS
CycloneDX 1.5 SBOM: PASS (41 runtime components)
```

새 runtime dependency는 `pypdf==6.14.2`, license는 `BSD-3-Clause`로 manifest에 반영했다.

배포 산출물:

```text
public_sector_research_mcp-0.1.0.dev0-py3-none-any.whl
public_sector_research_mcp-0.1.0.dev0.tar.gz
sbom.cdx.json
```

세 산출물 모두 non-empty와 SHA-256 계산을 확인했다. 정확한 release hash는 최종 commit 뒤
외부 release manifest에서 생성한다. sdist 안에 포함되는 이 보고서에 sdist 자체 hash를
고정하면 self-reference로 즉시 낡기 때문이다. SBOM도 timestamp와 UUID를 포함하므로
repository에 고정하지 않고 release build에서 다시 생성한다.

## 6. Acceptance 증거

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
| 실제 공식 웹 | 고정 공식 URL 5종의 snapshot 수집·파싱·선택 | PASS/fixed-source |
| curated discovery | no-key 실제 quick, 7 track·12 citation·purge | PASS/live |
| constrained writer | anchor 충족 track만 recommendation 5건, citation 모두 연결 | PASS/baseline |
| 실제 검색 | production live Search credential로 실행하지 않음 | PENDING |
| 업무 답변 유용성 | 보수적 evidence bundle까지만 검증, domain synthesis human QA 없음 | PENDING |
| site terms | robots 외 사이트별 약관 자동판정 없음 | PENDING/operational |

## 7. External Provider 경계

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

## 8. 남은 위험

1. 실제 Search provider가 위 고정 URL과 동등한 source를 안정적으로 찾는지는 검증 전이다.
2. 국가법령정보센터 법령 본문/조문 URL을 일반화해 발견하는 adapter는 아직 없다.
3. 현재 Writer는 anchor 기반 조달 원칙 후보 5건을 만들지만 표현·적용범위의 사람 품질검증은
   아직 완료하지 않았다.
4. 의미 기반 conflict, 법령 현행성·법적 성격 판정은 구현되지 않았다.
5. site별 Terms/저작권 허용범위는 robots만으로 해결되지 않는다.
6. trusted edge IP, 일일 비용상한, multi-replica quota가 없다.
7. async result lifecycle과 feedback이 없다.

## 9. 다음 Gate

`CH-P1.8`의 curated source 구현과 actual-source smoke는 완료됐다. 다음 순서는
`CH-P1.9 Human Usefulness QA`다.

1. 공공업무 담당자가 citation·원문·gap과 결과 유용성을 검토
2. evidence bundle이 부족하면 citation-constrained Writer를 구현
3. 국가법령정보센터 source adapter 또는 공식 Open API 연결 결정
4. 승인된 live Search provider로 recall·비용·실패율을 curated와 비교
5. 이후 edge/비용 경계를 닫고 PG0·PG1의 정식 판정을 갱신

credential은 repository, validation report, log와 MCP output에 기록하지 않는다.
