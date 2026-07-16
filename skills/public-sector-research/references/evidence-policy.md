# Evidence 정책

## 출처 등급

| 등급 | 의미 | 예시 |
|---|---|---|
| `OFFICIAL_PRIMARY` | 발행기관의 원문 | 법령, 정부 가이드, 공식 공시 |
| `OFFICIAL_SECONDARY` | 공식기관이 제공한 복제본·설명자료 | 공식 해설, 기관 호스팅 외부문서 |
| `ACADEMIC_PRIMARY` | 원 학술논문·연구보고서 | 학술지 원문, 연구기관 보고서 |
| `COMPANY_OFFICIAL` | 기업의 공식 문서 | 제품 문서, 공시, IR |
| `REPUTABLE_MEDIA` | 검증 가능한 언론 보도 | 원 출처 보조 확인 |
| `COMMUNITY` | 블로그·커뮤니티 | 발견과 맥락 보조 |
| `UNVERIFIED_WEB` | 등급 미확인 | 초기 후보 |
| `LOCAL_FILE` | 사용자가 제공한 로컬 파일 | 내부 검토자료 |

공식 domain이라는 이유만으로 `OFFICIAL_PRIMARY`를 자동 부여하지 않는다. 발행 주체, 문서 제목, 원문 여부를 확인한다.

## Evidence Score

종합점수는 다음 구성요소의 가중합이다.

| 구성요소 | 가중치 | 의미 |
|---|---:|---|
| Authority | 25% | 발행주체와 출처 등급 |
| Primary source | 15% | 1차자료 여부 |
| Direct relevance | 20% | 질문·track 핵심어와 Passage 직접성 |
| Original snapshot | 15% | 원문 bytes와 SHA-256 확보 |
| Specificity | 10% | page·HTML block·JSON Pointer locator |
| Freshness | 10% | 기준일 대비 발행일 |
| Independence | 5% | 다른 근거와 독립성 |

`overall` 하나만 사용하지 말고 각 구성요소의 설명을 함께 검토한다.

현재 Independence는 provenance graph가 없으므로 기본 0.5다. 동일 문장·동일 hash 중복은 제거하지만 기사→보도자료→원문 계보를 완전히 판별하지 못한다.

## 사실과 추론

- `FACT`: 원문 Passage가 직접 지지하는 진술
- `INFERENCE`: 여러 근거를 연결한 해석
- `RECOMMENDATION`: 업무 적용을 위한 제안

현재 deterministic report는 extractive citation을 생성하고 자동 `INFERENCE`·`RECOMMENDATION`을 만들지 않는다. AI 호스트가 후속 초안을 작성할 때 이 구분을 명시해야 한다.

## 최신성

발행일이 없으면 Freshness를 0.5로 두고 “발행일 미확인”으로 표시한다. 수집시점은 문서 발행일이나 현행성을 대신하지 않는다.
