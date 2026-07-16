# Public Sector Research MCP — 제품 비전

> 문서 상태: Accepted · 기준일: 2026-07-16 · 현재 제품단계: **Public Preview 설계**

[PRD](./PRD.md) · [ARCHITECTURE](./ARCHITECTURE.md) · [ROADMAP](./ROADMAP.md) · [ADR-0009](./adr/0009-public-zero-retention-first.md)

## 1. 한 줄 정의

**PSR MCP는 누구나 가입 없이 사용할 수 있고, 공신력 있는 공공자료를 우선 조사해 근거가 연결된 결과를 즉시 돌려준 뒤 사용자 content를 보관하지 않는 Privacy-First Public Research MCP다.**

## 2. 지금 해결할 문제

공공정책·법령·제도·조달·기술기준을 조사하려는 사람은 다음 어려움을 겪는다.

- 검색 결과가 많아도 어떤 자료가 공식 원문인지 판단하기 어렵다.
- 기사와 블로그가 같은 보도자료를 반복 인용해 근거가 많아 보인다.
- 법령·지침의 시행일, 관할, 적용대상과 현재 상태를 놓치기 쉽다.
- 생성형 AI 답변은 빠르지만 어느 원문 구간을 근거로 했는지 불명확할 수 있다.
- 전문 조사도구를 시험하려면 가입, 조직설정, 결제, 저장정책을 먼저 결정해야 한다.

현재 단계에서 가장 중요한 질문은 “기관용 Evidence Platform을 완성할 수 있는가?”가 아니다.

> **실제 사람들이 이 MCP를 연결해 유용한 공공자료 조사 결과를 반복해서 받는가?**

## 3. 제품 전략

제품은 수요가 증명되는 순서대로 성장한다.

```text
Stage A Public Preview
가입 없음 · 기본 무보관 · 즉시 결과 · 제한된 공개자료 조사

        ↓ 저장·History에 대한 실제 사용자 수요

Stage B Opt-in Account Beta
선택 가입 · Personal Workspace · 저장을 켠 조사만 History·재사용

        ↓ 반복 사용과 운영비 지불 의사

Stage C Paid Persistent Service
저장공간 · 높은 quota · 장기 조사 · 고급 Profile · export

        ↓ 팀·기관 운영 수요

Stage D Team / Public-Sector Enterprise
기관 SSO · Organization · Review · 감사 · 보존정책 · 협업
```

OAuth, PostgreSQL, RLS와 durable Job foundation은 이미 구현된 미래 확장 자산이다. Public Preview에서는 사용자 content를 영구 저장하는 이유로 사용하지 않는다.

## 4. Public Preview 경험

사용자는 MCP를 연결한 뒤 바로 질문한다.

```text
사용자 질문
→ 질문 범위와 기준일 확인
→ 공식 출처 우선 검색
→ 안전한 임시 작업공간에서 수집·분석
→ 주장·출처 URL·원문 구간·한계가 포함된 결과 생성
→ 같은 Tool 응답 또는 임시 result handle로 전달
→ 원문·중간자료·결과 content 삭제
```

짧은 조사는 한 번의 `research.quick` 호출로 끝난다. 긴 조사는 `research.start → status → result`로 진행하지만 결과는 수령 후 또는 짧은 TTL 뒤 사라진다.

## 5. 핵심 철학

### Useful Before Elaborate

가입·대시보드·조직관리보다 조사 결과가 실제 업무에 도움이 되는지 먼저 검증한다.

### Official Sources First

법령, 정부·공공기관, 국제기구, 표준기관, 공식 공시와 공식 기술문서를 우선한다. 비공식 자료는 발견과 맥락 보조로 구분한다.

### Evidence Before Conclusions

주요 사실은 출처 URL과 원문 구간을 함께 제시한다. 출처가 직접 말하지 않은 내용은 추론·제안으로 표시한다.

### Zero Retention by Default

사용자의 질문, 검색어, 수집 원문, 추출문과 보고서 본문은 기본적으로 서비스 자산이 아니다. 결과 전달을 위해 필요한 동안만 임시 처리한다.

### User Owns the Result

결과는 사용자의 AI Host, 로컬 파일, Git 또는 사용자가 선택한 외부 저장소로 전달된다. 서비스가 자동으로 소유하거나 재사용하지 않는다.

### Safety Is the Public Price of Admission

가입이 없기 때문에 IP quota, 비용 상한, SSRF 방어, parser 제한, TTL purge와 긴급 차단은 공개 전 필수다.

### Persistence Must Be Earned

History와 Evidence reuse는 내부 기대가 아니라 사용자의 명시적인 요청이 확인됐을 때만 만든다. 가입 후에도 저장은 opt-in이다.

### MCP-First, Client-Agnostic

특정 AI UI에 제품 로직을 종속시키지 않는다. Codex는 Tool-first로 지원하고, 다른 Host에서도 동일한 Tool schema와 결과 형식을 사용한다.

## 6. 주요 사용자

Public Preview는 직업이나 소속으로 가입을 제한하지 않는다.

| 사용자 | 대표 질문 | 제공 가치 |
|---|---|---|
| 공공기관·정부 업무담당자 | 정책·조달·평가·감사 기준 | 공식 원문과 적용조건 |
| 기업·비영리 정책담당자 | 공공정책과 규제 동향 | 관할·시행일·공식자료 |
| 연구자·학생 | 정책·제도 비교 | 재인용을 줄인 출처 묶음 |
| 개발자·기획자 | 공공 AI·데이터 기준 | 공식 기술·정책문서 비교 |
| 일반 시민 | 제도와 정부정책 이해 | 근거가 보이는 쉬운 설명 |

Stage B 이후에는 반복 사용자, Stage D에서는 팀·기관 관리자와 Reviewer가 추가된다.

## 7. 사용자에게 주는 현재 가치

1. 가입 없이 바로 시험할 수 있다.
2. 일반 검색보다 공식 원문 비중이 높다.
3. 답변과 함께 근거 URL·구간·기준일을 확인할 수 있다.
4. 공식 원문 미확보, 상충, 불확실성을 숨기지 않는다.
5. 질문과 조사 결과가 서비스에 장기 축적되지 않는다.
6. 사용자는 받은 Markdown/JSON을 원하는 곳에 직접 저장한다.

## 8. 성공한 상태

Public Preview의 성공은 기능 수가 아니라 실제 사용으로 판단한다.

- MCP 연결 후 첫 유용한 결과까지 5분 이내다.
- 완료된 조사 중 결과 수령률이 60% 이상이다.
- 자발적 피드백에서 “업무에 도움이 됐다”가 60% 이상이다.
- 채택한 근거의 공식 1차자료 비율이 70% 이상이다.
- 주요 FACT 문장의 출처 연결률이 95% 이상이다.
- 질문·원문·보고서 content가 TTL 이후 서버에 남은 사례가 0건이다.
- 실제 사용자가 History·저장·재사용 기능을 자발적으로 요청한다.

수치는 초기 가설이며 운영 데이터를 통해 조정한다. 단, content 무보관과 안전 기준은 성장지표를 위해 낮추지 않는다.

## 9. 지금 하지 않을 것

- 최초 사용 전에 회원가입·기관승인 요구
- 사용자 질문과 조사결과의 자동 영구 저장
- Project Memory와 Living Report를 Public Preview에 구현
- 팀·기관용 관리자 Console
- 결제·요금제·저장공간 판매
- 사용자 private document upload와 credential 수집
- 캡차·로그인·paywall·접근제한 우회
- 범용 검색엔진 또는 대규모 분산 crawler 개발
- 완전 자동 법률·감사·조달 판단
- 화려한 대시보드로 조사 품질을 대체

## 10. Public Preview 제품 원칙

1. 공개 사용 경로에는 계정과 Organization이 필요하지 않다.
2. 질문·원문·보고서 본문은 PostgreSQL과 일반 log에 저장하지 않는다.
3. 짧은 작업은 응답 즉시 반환하고 content를 폐기한다.
4. 긴 작업은 opaque handle과 TTL이 있는 임시 저장만 사용한다.
5. 성공적으로 결과를 전달하면 60초 이내 purge 대상으로 전환한다.
6. 미수령 결과와 orphan 작업공간에는 강제 TTL이 있다.
7. 검색·수집은 공개 HTTPS source에 한정하고 내부망 접근을 차단한다.
8. 비용·시간·다운로드·결과 크기 상한을 넘으면 부분 결과와 한계를 반환한다.
9. 사용량·보안 관찰은 content 없는 aggregate와 회전 HMAC counter로 제한한다.
10. 사용자가 명시적으로 저장을 선택하기 전까지 서비스는 과거 조사를 재사용하지 않는다.
11. OAuth·Tenant·영구저장은 선택 가입 단계의 adapter로 유지한다.
12. 새 기능보다 결과의 유용성·근거 품질·삭제 신뢰성을 먼저 측정한다.

## 11. 성장 단계별 가치

| 단계 | 사용자가 얻는 것 | 서비스가 저장하는 것 |
|---|---|---|
| Public Preview | 가입 없는 조사, 즉시 결과 | 임시 content + 최소 비콘텐츠 운영정보 |
| Account Beta | 선택 저장, History, 개인 Evidence reuse | 사용자가 저장을 선택한 조사 |
| Paid Persistent | 장기 보관, 높은 quota, 고급 export | 계약된 저장공간과 운영 metadata |
| Enterprise | 팀 공유, SSO, Review, 감사, 보존정책 | 기관 정책에 따른 격리 데이터 |

## 12. 1년 후 목표상태

- 공개 MCP가 최소 두 종류 Host에서 쉽게 연결된다.
- 반복적으로 쓰는 실제 사용자가 존재하고 조사 유용성이 측정된다.
- Public Preview는 기본 무보관 약속과 purge 검증을 유지한다.
- 저장 수요가 확인되면 선택 가입과 Personal Workspace가 제공된다.
- 유료화는 저장·장기실행·높은 quota에 대한 비용과 수요가 확인된 뒤 시작한다.
- 기관 기능은 일반 공개 서비스의 사용성을 해치지 않는 별도 mode로 제공한다.
- Government, Regulation, Procurement, Technology Profile이 순차적으로 확장된다.
- 성과지표는 가입자 수보다 완료 조사, 결과 수령, 유용성, 공식 근거 비율을 우선한다.

## 13. 핵심 용어

| 용어 | 정의 |
|---|---|
| Public Preview | 가입 없이 제한된 공개자료 조사를 제공하는 현재 목표 단계 |
| Zero Retention | 사용자 content를 영구 저장하지 않고 전달 또는 TTL 후 삭제하는 기본 정책 |
| User Content | 질문, 검색어, 원문, 추출문, Passage, 보고서 본문 |
| Operational Metadata | content를 포함하지 않는 상태, 시간, 크기 bucket, failure code, 비용 정보 |
| Ephemeral Run | 임시 작업공간과 TTL을 가진 공개 조사 실행 |
| Opaque Run Handle | 계정 없이 status/result를 조회하기 위한 추측 불가능한 일회성 식별자 |
| Research Profile | 조사 유형별 공식 출처 우선순위, 질문분해, 완료조건 설정 |
| Official Source | 법적·행정적·기술적 발행 권한이 확인되는 1차 또는 공식 자료 |
| Citation | 출처 URL, 제목, 발행기관, 기준시점과 원문 구간을 결합한 인용정보 |
| Opt-in Persistence | 사용자가 가입하고 특정 조사의 저장을 명시적으로 선택한 상태 |
| Personal Workspace | Account Beta에서 개인이 저장한 조사만 관리하는 공간 |
| Organization | Enterprise 단계에서 팀·기관의 권한과 데이터를 격리하는 경계 |

---

이 제품은 처음부터 거대한 Evidence 플랫폼이 되는 것으로 성공하지 않는다. **사람들이 부담 없이 써 보고, 결과가 실제로 유용하며, 저장을 원할 만큼 다시 찾을 때** 다음 단계로 성장한다.
