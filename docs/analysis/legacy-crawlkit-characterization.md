# Legacy `adaptive-web-research` / `crawlkit.py` Characterization

> 상태: Confirmed · 분석일: 2026-07-16 · 대상은 읽기 전용으로 분석했으며 수정하지 않았다.

[IMPLEMENTATION PLAN](../IMPLEMENTATION_PLAN.md) · [ARCHITECTURE](../ARCHITECTURE.md)

## 1. 확인 대상

| 파일 | SHA-256 |
|---|---|
| `SKILL.md` | `a690c2d5cad79ec322dc0d1383cf4832ba6a0f745793ea62796413a74b260ebb` |
| `scripts/crawlkit.py` | `ac68ab96463394db9a723a0eebea6717bcc6122aafba88a822675f58511011b6` |
| `scripts/run_collection_plan.py` | `01a71d28b93e8946e24c865d8dd34668eb0f17ccfca8fb0f505aac6a7212d8c4` |
| `references/collection-workflow.md` | `22e433ae479cc4a59fec0168a517993ed5fee76fd11994a39eefa04abb73b810` |
| `references/plan-schema.md` | `8e5d857853d09934af13e22c5d0aa687de2a8128f09b7e8a5aed00383170c04f` |

확인된 CLI:

```text
crawlkit.py probe <url> [--method] [--header] [--data] [--output-dir] [--save-body]
crawlkit.py fetch <url> --output-dir <dir> [--name]
run_collection_plan.py <plan.json> --output-dir <dir>
```

`run_collection_plan.py`의 step은 `request`, `paginate`, `follow_links` 세 종류다.

## 2. 확인된 출력

Snapshot metadata:

```json
{
  "url": "original URL",
  "final_url": "redirect 후 URL",
  "status": 200,
  "headers": {},
  "content_type": "text/html; charset=utf-8",
  "fetched_at": "RFC3339",
  "sha256": "hex",
  "body_path": "probe.html"
}
```

Probe는 공통 field `kind`, `status`, `url`, `final_url`, `content_type`, `bytes`,
`sha256`, `fetched_at`을 반환하고 kind별 요약을 추가한다.

- HTML: title, description, links, forms, tables, JSON-LD, pagination 후보, text sample
- JSON: top-level type, key, list count, sample key
- PDF: page 수와 첫 페이지 text sample
- Text: 최대 1,000자 sample

## 3. 실제 프로젝트 저장 사례

`AX2030` 프로젝트의 `work/**/research/` 아래에서 HTML·PDF·metadata snapshot, 추출 text,
rendered page와 evidence 문서가 다수 확인됐다. 이 구조는 다음 가치를 증명한다.

- 원문과 metadata를 함께 남겨 조사 재현성을 높였다.
- URL, 수집시점, hash를 통해 후속 검토가 가능했다.
- HTML과 PDF를 동일한 조사 디렉터리 규칙으로 관리했다.

동시에 다음 failure pattern도 실제 사례에서 확인됐다.

1. PDF download endpoint가 `application/octet-stream`을 반환해 `.bin`으로 저장됐다.
2. HTTP 200이지만 SHA-256이 빈 body hash인 HTML snapshot이 존재했다.
3. 403 응답은 별도 수동 header/body 파일로 남았고 typed failure schema에 들어가지 않았다.
4. response header snapshot에 `Set-Cookie`가 그대로 포함될 수 있다.

실제 프로젝트 파일은 characterization 근거로만 읽었고 이 저장소로 복사하지 않았다.

## 4. 재사용 판단

| 구성요소 | 결정 | 이유 |
|---|---|---|
| `RequestSpec`, `ResponseRecord` 개념 | Refactor | typed port/model로 유용하나 credential·budget·redirect 정책 필요 |
| SHA-256 body hash | Reuse | dedup·snapshot integrity의 기본 primitive로 적합 |
| `normalize_space` | Reuse | parser 공통 순수 함수로 적합 |
| HTML link/form/table 탐색 heuristic | Refactor | discovery에는 유용하나 bounded parser와 selector 제한 필요 |
| JSON top-level probe | Refactor | depth·item·byte 제한과 JSON Pointer locator 필요 |
| PDF page/text sample | Refactor | parser process 제한, page cap, OCR 상태가 필요 |
| snapshot metadata 개념 | Refactor | cookie·authorization redaction과 ephemeral sink 필요 |
| `request/paginate/follow_links` plan 개념 | Refactor | schema, source budget, host policy, approval rule 필요 |
| `urllib` Fetcher | Replace | SSRF·redirect·size·timeout·DNS pinning 요구를 만족하지 못함 |
| CookieJar 기본 세션 | Replace | 공개 서비스는 사용자·source cookie를 기본 보존하지 않음 |
| local path와 `file://` 지원 | Replace/Public 금지 | MCP 입력을 통한 서버 파일 읽기 위험 |
| 임의 method/header/form data | Replace/Public 금지 | credential 전달·CSRF·비의도 변경 요청 위험 |
| 자동 redirect | Replace | 매 hop URL·DNS·IP 재검증 필요 |
| `response.read()` | Replace | compressed/raw/decompressed byte 상한이 없음 |
| raw response headers 저장 | Replace | cookie·credential·개인정보 유출 가능 |
| suffix/content-type만으로 kind 판별 | Replace | magic-byte sniff와 불일치 상태 필요 |
| 예외 기반 전체 실패 | Replace | source별 typed failure와 partial success 필요 |

## 5. 공개 서비스에 그대로 사용할 수 없는 이유

### Network

- HTTP도 허용하며 HTTPS-only 정책이 없다.
- localhost, private, link-local, metadata IP를 차단하지 않는다.
- redirect가 opener 내부에서 자동 처리돼 hop별 검증이 불가능하다.
- DNS rebinding 방어와 resolved-address pinning이 없다.
- response size, redirect count, retry budget과 host concurrency 상한이 없다.

### Input and State

- local path와 `file://`를 읽을 수 있다.
- 임의 header, POST form, cookie session을 허용한다.
- `run_collection_plan.py`가 schema validation 없이 arbitrary template과 selector를 실행한다.
- source별 robots/terms/access policy 상태를 표현하지 않는다.

### Parsing and Evidence

- MIME header와 URL suffix에 의존해 PDF download endpoint를 오분류할 수 있다.
- empty/login/error page를 정상 document와 구분하지 않는다.
- PDF, HTML, JSON parser의 CPU, memory, page, depth 제한이 없다.
- locator, source tier, claim relation과 evidence score가 없다.

### Failure and Observability

- HTTP error, timeout, decode, parse failure가 안정적인 code로 정규화되지 않는다.
- retry와 partial success 정책이 없다.
- header snapshot에 secret-bearing field가 포함될 수 있다.
- 원래 Skill 디렉터리에는 automated test가 확인되지 않았다.

## 6. Dependency 확인

Legacy parser의 optional dependency는 `beautifulsoup4`, `pypdf`다. 현재 PSR MCP virtual
environment에는 둘 다 설치돼 있지 않다. dependency 도입은 Safe Parser fixture와 resource
budget을 정의한 뒤 별도 change로 수행한다.

## 7. 이식 순서

1. `UrlPolicy`와 resolver contract를 먼저 구현한다.
2. synthetic SSRF/redirect corpus로 public address만 허용하는지 검증한다.
3. bounded streaming HTTP adapter를 추가한다.
4. magic-byte 기반 document kind 판별을 추가한다.
5. HTML/JSON parser를 작은 fixture로 구현한다.
6. PDF dependency와 parser 격리 전략을 결정한다.
7. 마지막에 hash, normalize, probe heuristic을 새 model에 맞춰 이식한다.

## 8. 결론

기존 Skill은 “처음 보는 source를 probe하고 원문을 남긴다”는 조사 workflow와 hash/snapshot
개념을 성공적으로 입증했다. 그러나 공개 다중 사용자 MCP의 네트워크 실행기로는 사용할 수 없다.

**결정:** 기존 파일은 보존하고, 순수·결정적 primitive만 선택적으로 재사용한다. Fetcher,
redirect, cookie, local file, persistence는 Public SafeCollector에서 새로 구현한다.
