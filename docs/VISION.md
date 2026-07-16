# VISION — Universal Evidence Research Skill

[PRD](PRD.md) · [ARCHITECTURE](ARCHITECTURE.md) · [ROADMAP](ROADMAP.md)

## 한 줄 정의

**Public Sector Research Agent는 어느 AI 호스트에서든 공공업무 질문을 공식 원문 중심의 검토 가능한 Evidence Package로 바꾸는 로컬 우선 범용 Agent Skill이다.**

## 문제

공공업무의 품질은 그럴듯한 요약보다 출처의 권위, 원문 구간, 기준시점, 적용범위와 미확인 사항을 얼마나 명확히 남기는가에 달려 있다. 일반 검색과 일회성 AI 대화는 원문 snapshot, Passage locator, 중복 판정, 부분실패, 조사 재사용을 안정적으로 보존하지 않는다.

## 제품 방향

- 하나의 Agent Skills 표준 폴더를 Codex·Claude·호환 호스트에서 사용한다.
- 검색 capability는 AI 호스트가 제공하고 Evidence 처리 규칙은 공통 Python Core가 담당한다.
- 원문과 메타데이터는 사용자 프로젝트의 `.psr/`에 저장한다.
- 공식 원문을 확보하지 못하면 그 사실을 숨기지 않는다.
- 서버 운영은 제품 검증 이후 선택적으로 추가한다.

## 주요 사용자

- 정책·기획 담당자
- 법무·규정 담당자
- 조달·계약 담당자
- 개인정보·AI 담당자
- 감사·평가 담당자
- 공공분야 연구·용역 수행자

## 핵심 가치

1. Evidence First, Opinion Later
2. Research Once, Reuse Locally
3. Official Sources First
4. Traceable and Reproducible
5. Human-Reviewable
6. Host-Portable

## 하지 않을 것

- 범용 검색엔진 자체 개발
- 대규모 분산 크롤링
- 접근제한 우회
- 출처 없는 자동 결론
- 초기부터 원격 멀티테넌트 SaaS 구축
- MCP를 제품 본체로 강제

## 성공한 상태

사용자가 AI 호스트를 바꾸어도 같은 Skill과 `.psr/` 프로젝트를 사용해 계획, 원문, citation, 보고서를 이어서 검토한다. 핵심 주장은 원문 Passage와 연결되고, gap과 부분실패가 보고서에 표시되며, 네트워크가 없을 때도 기존 Evidence Memory를 조회한다.
