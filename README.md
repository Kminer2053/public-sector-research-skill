# Public Sector Research MCP

공공분야 업무종사자가 MCP 호환 AI 클라이언트에서 공식 자료 중심의 조사를 계획하고, 원문 근거를 검토·재사용하며, 감사 가능한 보고서를 만들 수 있게 하는 Evidence-First Research MCP입니다.

> 상태: 설계 단계. 아직 제품 코드는 구현하지 않았습니다.

## 왜 별도 저장소인가

이 프로젝트는 범용 탐색·수집 성능을 지향하는 기존 [`planned-web-crawling-skill`](https://github.com/Kminer2053/planned-web-crawling-skill)과 목적, 사용자, 위험 모델이 다릅니다.

- 기존 저장소: 단일 사용자의 유연한 조사형 크롤링 Skill
- 이 저장소: 공공분야 다중 사용자를 위한 공식자료 우선 Research MCP 서비스

기존 `crawlkit.py`의 fetch·parse·hash 원리는 검토 후 선택적으로 재사용하지만, 코드를 그대로 복제하거나 기존 Skill의 정책을 제품 정책으로 간주하지 않습니다.

## 핵심 문서

- [VISION](./docs/VISION.md): 제품 정체성과 공공분야 가치
- [PRD](./docs/PRD.md): 사용자·기능·MCP 계약·Acceptance Criteria
- [ARCHITECTURE](./docs/ARCHITECTURE.md): 원격 MCP, 다중 사용자, 증거 저장·보안 설계
- [ROADMAP](./docs/ROADMAP.md): MVP부터 공공분야 운영 확장까지의 구현 순서

## 프로토콜 기준

2026-07-16 현재 MCP 안정 사양인 `2025-11-25`를 기준으로 합니다. `2026-07-28` Release Candidate의 stateless transport 변화는 별도 adapter와 ADR로 추적하며, 안정 사양이 되기 전에는 운영 기준으로 고정하지 않습니다.

## 제품 원칙

```text
Official Sources First
Evidence Before Conclusions
Human Approval for Accountable Decisions
Tenant Isolation by Default
MCP-First, Client-Agnostic
Traceable, Reproducible, Reusable
```

## 현재 범위

이번 저장소 분리 단계에서는 설계 문서만 포함합니다. 기존 crawler 코드의 이동·리팩터링·배포는 Roadmap의 승인된 작업 패키지에서 시작합니다.
