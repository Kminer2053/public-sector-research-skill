# Public Research Human Review Packet 검증

> 기준일: 2026-07-16 · 판정:
> **Review Tooling Local PASS / Independent Public-Sector Human QA Pending**

[Architecture](../ARCHITECTURE.md) · [PRD](../PRD.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 목적

자동 schema·citation 검사를 통과한 결과가 실제 공공업무에도 유용한지는 별도 문제다. 담당자가
매번 다른 감각으로 평가하지 않도록 구조 품질지표와 사람 전용 판정표를 하나의 local review
packet으로 제공한다. 이 도구는 MCP 서버 기능이 아니며 질문과 결과를 서버나 DB에 저장하지
않는다.

## 2. 구현한 검토 경계

자동 계산:

- FACT citation coverage
- RECOMMENDATION citation coverage
- citation locator completeness
- document SHA-256로 중복을 제거한 공식 1차자료 비율
- Planner 필수 source track recall
- finding, citation, unique document, gap, conflict, failure 수
- 응답의 `PURGED`, `server_saved=false` 표시

사람에게만 맡기는 판단:

- 실제 업무 의사결정에 도움이 되는지
- 법적 의무, 권고와 사례를 혼동하거나 과잉해석하지 않는지
- 중요한 누락과 상충정보가 숨겨지지 않았는지
- 영문 원문을 한국어로 과도하게 의역하지 않았는지
- 초안·체크리스트·후속 조사로 전환 가능한지

`scripts/live_curated_review.py`는 질문과 전체 결과, 위 지표와 검토표를 stdout으로만 출력한다.
feedback token과 operation ID는 출력하지 않는다. 검토자가 저장을 원할 때만 승인된 로컬
문서공간으로 명시적으로 이동한다.

## 3. 실제 curated 실행

질문:

```text
공공기관 AI 구매 원칙에 데이터 권리, 학습 재사용, 업체 종속,
개인정보와 사람의 감독 조건을 포함해줘
```

관찰값:

| Metric | Result | Gate | 판정 |
|---|---:|---:|---|
| FACT citation coverage | 100% | 100% | PASS |
| RECOMMENDATION citation coverage | 100% | 100% | PASS |
| locator completeness | 100% | ≥95% | PASS |
| 공식 1차 document ratio | 80% | ≥70% | PASS |
| 필수 track recall | 100% | 100% | PASS |
| citation / unique document | 12 / 5 | 정보 | - |
| recommendation / FACT | 5 / 12 | 정보 | - |
| gap / conflict / failure | 3 / 0 / 0 | 정보 | - |
| retention | PURGED / server_saved=false | 필수 | PASS |

실행 종료코드 0은 구조지표 통과와 ephemeral directory empty를 함께 뜻한다.

## 4. 내부 검토에서 발견한 문제와 수정

초기 `data-rights` 권고문은 개인정보보호위원회의 개인정보·이용자 입력데이터 근거를 사용하면서
“기관 데이터의 모델 학습 재사용” 전체로 표현했다. 이는 원문보다 적용범위를 넓히는
과잉해석이었다.

수정 전:

```text
기관 데이터의 모델 학습 재사용 여부와 선택권, 보유기간·파기 조건을 계약 전에 확정한다.
```

수정 후:

```text
개인정보 또는 이용자 입력데이터를 모델 학습에 이용하는지,
정보주체의 선택권과 보유기간·파기 조건을 계약 전에 확인·명시한다.
```

회귀 test는 새 문구가 개인정보·이용자 입력데이터와 정보주체 범위를 유지하고
`기관 데이터`라는 포괄 표현을 다시 사용하지 않는지 검증한다. 실제 curated 원문 실행에서도
수정된 권고문과 전체 구조 PASS를 재확인했다.

## 5. 현재 제품 판단

내부 Product/Architecture 검토의 임시 판정은 **“보완 후 참고 가능”**이다.

장점:

- 권고와 사실이 분리되고 모든 항목에 근거 ID가 있다.
- 공식 원문 구간, locator, hash와 점수 구성요소를 확인할 수 있다.
- 근거가 부족한 정부정책·조달 track은 권고를 만들지 않고 missing anchor를 gap으로 남긴다.
- 법률자문이나 최종 기관 판단으로 자동 승격하지 않는다.

보완 필요:

- 국내 공식 조달자료가 없어 조달·업체종속 근거 일부가 오래된 WEF 자료에 의존한다.
- 시행일, 적용대상과 법령·가이드의 법적 성격을 체계적으로 판정하는 GR-002가 남아 있다.
- 일부 한국어 PDF 추출문은 띄어쓰기가 손실돼 사람이 읽기 어렵다.
- 상충 근거가 실제로 없는지 live Search로 확인하지 못했으므로 `conflicts=0`은 완전성 보장이 아니다.
- 외부 공공업무 담당자가 실제 규정·보고서 작성에 얼마나 시간을 절약하는지 아직 측정하지 않았다.

따라서 이 보고서는 사람 검토 절차와 내부 결함 발견 능력을 검증한 것이지, 공공분야 조사
품질의 최종 승인이나 PG1 최종 PASS가 아니다.

## 6. 자동 검증

전체 회귀:

```text
475 passed (450 non-PostgreSQL + 25 PostgreSQL)
```

Coverage:

```text
raw total: 95.41%
normalized statement: 96.42%
branch: 91.40%
critical module statement minimum: 95.0%
public review module statement/branch: 100% / 100%
status: pass
```

정적·공급망 검증:

```text
ruff: pass
format: pass
strict mypy: pass (149 source files)
dependency license manifest: current
```

실제 TCP reconnect, TLS terminating reverse proxy와 PostgreSQL RLS 회귀를 포함했다.

## 7. 다음 검증

1. 서로 다른 역할의 공공업무 담당자 3~5명이 같은 packet으로 독립 평가
2. 점수 차이와 낮은 항목을 비교해 rubric 문구와 결과 구조 보정
3. GR-002 법령·가이드 현행성, GR-003 재인용, GR-004 부분 실패 packet 확대
4. 국내 공식 조달 source adapter 또는 reviewed catalog 추가
5. live Search credential 확보 뒤 curated 대비 recall·비용·provider retention 비교

외부 검토자가 질문·결과를 저장할 경우에는 해당 기관의 문서 보존·개인정보 정책을 적용한다.
