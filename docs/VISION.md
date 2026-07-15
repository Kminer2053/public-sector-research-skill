# Public Sector Research MCP — 제품 비전

> 문서 상태: Proposed · 기준일: 2026-07-16 · 제품 약칭: **PSR MCP**

구체 요구사항은 [PRD](./PRD.md), 기술 설계는 [ARCHITECTURE](./ARCHITECTURE.md), 구현 단계는 [ROADMAP](./ROADMAP.md)을 따른다.

## 1. 한 줄 정의

**PSR MCP는 공공분야 업무종사자가 MCP 호환 AI 클라이언트에서 공식 원문을 우선 조사하고, 주장과 근거를 검토·재사용하며, 변경과 책임을 추적할 수 있게 하는 다중 사용자 Evidence Research Service다.**

## 2. 저장소와 제품 경계

이 제품은 기존 `planned-web-crawling-skill`의 v2가 아니다. 별도의 사용자와 운영 책임을 가진 신규 제품이다.

| 구분 | 기존 `planned-web-crawling-skill` | 신규 `public-sector-research-mcp` |
|---|---|---|
| 핵심 목표 | 처음 보는 웹 소스를 유연하게 탐색·수집 | 공공업무 판단에 쓸 수 있는 검토 가능한 근거 제공 |
| 주요 사용자 | 개인 연구자·Codex 사용자 | 중앙·지방정부, 공공기관, 지원기관의 업무담당자와 Reviewer |
| 기본 형태 | 로컬 Codex Skill·스크립트 | 원격 다중 사용자 MCP 서비스 + 최소 Review Console |
| 우선 가치 | 탐색 범위와 수집 성능 | 공신력, 현행성, 추적성, 권한분리, 감사가능성 |
| 저장 | 임의 프로젝트 폴더 snapshot | Tenant 격리 Evidence Store와 immutable object |
| 실행 책임 | 사용자 개인 | 기관·Project·사용자·Reviewer 단위 책임 |
| Protocol | Skill instruction과 CLI | MCP Tools·Resources·Prompts, Streamable HTTP |

기존 코드에서 재사용할 수 있는 것은 fetch·parse·hash 같은 저수준 원리다. 접근 우회, 민감 header 보존, 이름 기반 덮어쓰기, 실패 격리 없는 실행 방식은 신규 제품으로 가져오지 않는다.

## 3. 문제 배경

공공분야의 정책, 규정, 조달, 평가, 감사, 사업기획 업무는 다음 특성을 가진다.

- 결론보다 “어느 기관의 어떤 원문을 근거로 했는가”가 중요하다.
- 법령·지침·계획·보도자료는 시행일, 적용대상, 관할과 개정상태가 다르다.
- 같은 보도자료를 여러 기사와 블로그가 재인용해 근거 수가 부풀려질 수 있다.
- 보고서가 완성된 뒤 원문이 개정되면 기존 판단도 다시 검토해야 한다.
- 여러 담당자와 외부 수행자가 같은 자료를 반복 검색하지만 조사 이력은 남지 않는다.
- 생성형 AI가 빠르게 초안을 만들 수 있어도 사실, 해석, 권고, 최종 의사결정의 책임은 사람에게 있다.
- 기관 자료와 Project 산출물은 사용자·조직·업무별 접근통제가 필요하다.

일반 검색 서비스는 자료 발견에는 유용하지만 Project Memory, 원문 snapshot, passage-level citation, 검토 상태, 변경 영향을 제공하지 않는다. 범용 크롤러는 더 많은 자료를 모을 수 있지만 공공업무에 필요한 출처 위계와 책임 경계를 기본 제공하지 않는다.

## 4. 제품 비전

PSR MCP는 사용자가 이미 쓰는 AI 클라이언트에서 다음 흐름을 제공한다.

```text
업무 질문
→ 공공업무 Research Profile 적용
→ 조사 쟁점·관할·기준시점·완료조건 작성
→ 담당자 계획 승인
→ 공식 출처 Registry와 검색 결과에서 후보 탐색
→ 정책을 지킨 수집과 immutable snapshot
→ Passage·Claim·EvidenceLink·Score
→ 상충·공백·추론 표시
→ Reviewer 승인 또는 보완
→ 보고서·인용자료·업무메모 생성
→ Project Memory 축적
→ 원문 변경과 영향받는 보고서 재검토
```

MCP는 단순한 wrapper가 아니라 제품의 공식 계약이다.

- **Tools:** 조사 계획, 실행, 근거 검색, Review, 보고서 생성 같은 동작
- **Resources:** plan, run, evidence, document, report, change를 안정적인 URI로 제공
- **Prompts:** 공공정책 조사, 현행성 검토, 공식사례 벤치마킹 등 사용자 주도 workflow template
- **Authorization:** 기관 Identity Provider와 연결된 사용자·Project·scope 경계

AI 클라이언트가 바뀌어도 동일한 Evidence ID와 Review 이력이 유지되는 것이 제품의 핵심이다.

## 5. 핵심 철학

### Official Sources First

법령, 정부·공공기관, 국제기구, 표준기관, 공식 공시·기술문서를 우선한다. 기사·블로그·커뮤니티는 발견과 맥락 보조로 사용할 수 있지만 원 출처와 구분한다.

### Evidence Before Conclusions

모든 주요 FACT Claim은 Snapshot의 Passage와 연결한다. 출처에 없는 해석·예측·제안은 `INFERENCE` 또는 `RECOMMENDATION`으로 표시한다.

### Currentness Is Part of Truth

문서의 존재만으로 충분하지 않다. 현행 여부, 시행일, 기준시점, 적용대상과 개정 관계를 함께 관리한다.

### Human Approval for Accountable Decisions

Model-controlled MCP Tool이라는 이유로 계획 승인이나 의사결정을 자동화하지 않는다. 조사계획, Evidence Review, 보고서 승인, destructive operation은 제품 수준의 사람 확인을 요구한다.

### Research Once, Reuse Institutionally

검색어, 출처, 제외 이유, Claim, Report, Review를 Project 자산으로 남겨 담당자가 바뀌어도 검증된 근거를 재사용한다.

### Tenant Isolation by Default

모든 Project, Job, Resource, Object, Audit Event는 Organization과 사용자 authorization context에 묶인다. 추측 가능한 ID만으로 다른 조직 자료에 접근할 수 없어야 한다.

### MCP-First, Client-Agnostic

Codex, ChatGPT, Claude 계열 등 특정 AI UI에 제품 로직을 종속시키지 않는다. MCP adapter와 application service를 분리한다.

### Explain Automation

자동 점수, 중복 판정, 변경 분류, 후속 질문에는 판단 근거, rule version, confidence와 override 이력을 남긴다.

## 6. 주요 사용자

| 사용자 | 대표 업무 | 필요한 제품 가치 |
|---|---|---|
| 정책·기획 담당자 | 정책동향, 사업계획, 기본계획, 업무보고 | 공식자료 우선, 빠른 briefing, 재사용 |
| 법무·규정 담당자 | 법령·지침 현행성, 적용대상, 의무/권고 검토 | 조항 locator, 시행일, 개정 영향 |
| 조달·계약 담당자 | 제안요청서, 구매원칙, 계약 요구사항 | 공공조달 근거, 데이터권리, 업체종속 검토 |
| 감사·평가 담당자 | 경영평가, 감사기준, 지표 근거 | 기준 문서 계보, 수치 정의, Review 이력 |
| 디지털·AI 담당자 | AI·데이터 정책, 기술기준, 국내외 사례 | 공식 기술문서, 표준, 사례의 적용조건 |
| 연구·용역 수행자 | 조사보고서와 정책연구 | Project 공유, citation bundle, provenance |
| 관리자 | 사용자·Project·출처정책·보존관리 | Tenant/RBAC, audit, quota, source registry |
| Reviewer·결재권자 | 계획·근거·보고서 승인 | 상충·공백·변경 diff, 책임 있는 승인 |

## 7. 사용자 가치

1. **업무시간 단축:** 이미 검토한 공식자료와 Claim을 다시 사용한다.
2. **보고서 신뢰 향상:** 문장마다 원문 구간과 수집시점을 확인한다.
3. **인수인계 가능성:** 개인 브라우저 기록이 아니라 Organization Project에 조사 맥락이 남는다.
4. **변경 대응:** 기준 문서 개정 시 영향받는 Claim과 Report를 찾는다.
5. **기관 통제:** AI 클라이언트와 무관하게 동일한 권한·Review·감사정책을 적용한다.
6. **선택권:** 특정 LLM 또는 업무 UI를 교체해도 Evidence Store와 MCP 계약을 유지한다.

## 8. 성공한 상태의 모습

공공기관 담당자가 “AI 서비스 구매 원칙 초안”을 요청하면 다음이 일어난다.

1. MCP Prompt 또는 Tool이 관할, 기준일, 적용조직, 산출물을 확인한다.
2. Planner가 법령, 개인정보, 공공조달, 데이터 권리, 기록 반환, 학습 재사용, 업체 종속을 분해한다.
3. 담당자가 Review Console 또는 승인 가능한 MCP flow에서 계획을 확인한다.
4. Server가 승인된 공식 출처 track을 대상으로 job을 시작하고 `research_run_id`를 반환한다.
5. AI 클라이언트는 status tool과 run resource로 진행상태를 확인한다.
6. 공식 원문, Snapshot, Passage, Score, 상충·공백이 Organization Evidence Store에 저장된다.
7. Claim과 보고서가 Passage locator에 연결되고 원문 미확보 자료는 명시된다.
8. Reviewer가 핵심 Claim을 승인한 뒤 보고서가 생성된다.
9. 다른 담당자의 유사 과제는 기존 Evidence를 freshness와 함께 재사용한다.
10. 기준 가이드가 개정되면 관련 Resource update와 Review queue가 생성된다.

## 9. 공공성의 의미

“공식자료 우선”은 정부 자료를 무조건 진실로 간주한다는 뜻이 아니다.

- 발행 권한과 법적 지위가 높은가?
- 기준시점에 현행인가?
- 질문의 관할과 대상에 적용되는가?
- 원문이 직접 해당 Claim을 지지하는가?
- 성과수치의 분모와 조건이 공개돼 있는가?
- 다른 독립 자료와 충돌하는가?

PSR MCP는 이 질문을 구조화하고 사람이 검토할 수 있게 한다. 제품이 정책적 정답이나 법적 결론을 대신하지 않는다.

## 10. 하지 않을 것

- 범용 검색엔진·대규모 분산 crawler 자체 개발
- 캡차, 로그인, paywall, 접근제한의 무단 우회
- 유료·비공개 데이터에 대한 권한 없는 접근
- 사용자 승인 없는 외부 network 수집과 destructive operation
- AI에 의한 최종 법률·감사·조달 판단
- 출처 없는 보고서 문장을 Evidence로 승격
- 공공기관 자료라는 이유만으로 상충·오류 가능성을 숨김
- MCP Tool 수를 늘리는 것을 제품 성과로 간주
- AI 클라이언트 token을 downstream source에 전달
- 초기부터 모든 기관 요구를 수용하는 거대한 SaaS 구축
- 복잡한 graph DB와 시각화부터 구현

## 11. 제품 원칙

1. Organization과 Project가 모든 데이터의 소유 경계다.
2. MCP Resource URI는 authorization context 안에서만 해석한다.
3. Tool input/output은 versioned JSON Schema를 갖는다.
4. 장기 작업은 짧은 Tool call과 명시적 application job으로 분리한다.
5. 현재 실험 기능인 MCP Tasks는 핵심 의존성이 아니다.
6. 원문은 immutable object, 관계와 상태는 transaction DB에 저장한다.
7. HTTP 성공과 Evidence 성공을 구분한다.
8. Claim, Evidence, Review, Report, Decision을 분리한다.
9. Reviewer override는 원 판단을 삭제하지 않고 supersede한다.
10. credential과 source token은 MCP client token과 분리한다.
11. partial success를 보존하고 완전하지 않음을 명시한다.
12. 한국어 업무 산출물과 영문 원문의 의미를 함께 보존한다.
13. Project export는 raw 원문 제외를 기본으로 한다.
14. protocol transport와 application service를 분리한다.
15. client compatibility는 conformance test로 증명한다.

## 12. 1년 후 목표상태

- 최소 2개 공공분야 조직이 pilot에서 반복 사용한다.
- Codex 계열을 포함한 2개 이상의 MCP Host에서 같은 Project Evidence를 조회한다.
- 원격 Streamable HTTP, 기관 IdP 연동, Tenant/RBAC, audit가 운영된다.
- Government, Regulation, Procurement, Technology, Strategy Profile이 제공된다.
- 공식 source registry와 source owner review workflow가 있다.
- Project Memory, Evidence Score, Claim Review, Markdown/HTML/JSON export가 운영된다.
- 기준문서 변경과 보고서 영향 검토가 가능하다.
- Protocol 안정 버전과 차기 버전 adapter가 분리돼 있다.
- 수집·보고서 생성보다 Evidence reuse, Review turnaround, stale resolution을 주요 metric으로 본다.

## 13. 핵심 용어

| 용어 | 정의 |
|---|---|
| Organization | 사용자, Project, 정책, quota, 보존기간을 공유하는 Tenant 경계 |
| Project | 특정 업무·정책·사업의 조사 자산과 권한을 공유하는 공간 |
| Membership | User와 Organization/Project Role의 연결 |
| ResearchPlan | 질문, source track, 완료·중단조건, 비용, 승인상태를 가진 조사계획 |
| ResearchRun | 승인된 Plan을 실행한 application job과 결과 단위 |
| Source Registry | 공식 기관·domain·source type·검토상태를 관리하는 조직별/공통 registry |
| Document | 제목·발행기관·식별자를 가진 논리 원문 |
| Snapshot | 특정 시점에 확보한 immutable 원문 bytes와 수집 metadata |
| Passage | Snapshot의 page·section·JSON Pointer 등 locator가 있는 근거 구간 |
| Claim | 업무 산출물에서 검토할 사실·추론·권고 진술 |
| EvidenceLink | Claim과 Passage의 지지·반박·한정·맥락 관계 |
| Review | Plan, Evidence, Claim, Report를 승인·반려·보완 요청한 append-only 기록 |
| MCP Tool | Model이 호출할 수 있는 versioned action contract |
| MCP Resource | Host가 context로 읽는 URI 기반 Project data |
| MCP Prompt | 사용자가 선택해 시작하는 공공업무 workflow template |
| Scope | OAuth authorization이 허용하는 최소 capability |
| Authorization Context | Organization, User, Role, Scope, Project restriction을 결합한 실행 경계 |

---

이 제품은 “더 많이 긁는 crawler”가 아니라 “공공업무에서 다시 확인할 수 있는 근거를 안전하게 제공하는 MCP”로 성공 여부를 판단한다.
