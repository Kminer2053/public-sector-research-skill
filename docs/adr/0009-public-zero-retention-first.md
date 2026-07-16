# ADR-0009 — Public Zero-Retention First

> 상태: Accepted · 날짜: 2026-07-16 · 결정자: Product owner

## Context

기존 설계는 기관 사용자, OAuth 로그인, Organization/Project, 영구 Evidence Store, Review와 Project Memory를 MVP부터 제공하는 방향이었다. 이 구조는 장기적으로 가치가 있지만, 아직 실제 사용자가 제품을 반복해서 사용할지 검증되지 않은 단계에서 가입·관리·보존·결제·기관 운영을 모두 선행하게 만든다.

제품의 현재 우선순위는 다음과 같다.

1. 누구나 쉽게 MCP를 연결하고 유용한 공공자료 조사 결과를 받는다.
2. 사용자 질문·수집 원문·생성 결과를 서비스가 장기 보유하지 않는다.
3. 안전한 수집과 비용·남용 방어를 최소 공개 조건으로 둔다.
4. 반복 사용과 저장 수요가 확인된 뒤에만 계정과 영구 저장을 제공한다.

## Decision

제품 단계를 네 개로 분리한다.

### Stage A — Public Preview

- 가입과 로그인 없이 공개 MCP를 사용할 수 있다.
- 사용자의 질문, 수집 원문, 추출문, 보고서 본문은 영구 DB에 저장하지 않는다.
- 짧은 조사는 같은 Tool 응답으로 반환한다.
- 긴 조사는 opaque run handle로 임시 조회하며, 결과 전달 또는 TTL 만료 후 삭제한다.
- 안전·사용량 통제를 위한 최소 비콘텐츠 metadata만 제한적으로 보관한다.
- Project Memory, 과거 조사 재사용, 팀 공유, 결제는 제공하지 않는다.

### Stage B — Opt-in Account Beta

- 사용자가 저장·과거 조사 검색을 원할 때만 OIDC 계정을 만든다.
- 신규 계정은 Personal Workspace를 가진다.
- 저장은 명시적 opt-in이며 기본값은 계속 무보관이다.
- 저장한 조사에만 History, Evidence reuse, refresh 기능을 제공한다.

### Stage C — Paid Persistent Service

- 저장공간, 장기 Job, 고급 Profile, 더 높은 quota, export를 유료 기능으로 제공한다.
- 암호화, 삭제, backup/restore, billing, support와 보존정책을 제품 계약으로 제공한다.

### Stage D — Team and Public-Sector Enterprise

- Organization, Membership, 기관 SSO, RLS, Review, audit export, legal hold를 제공한다.
- 현재 구현된 OAuth/PostgreSQL/Tenant foundation은 이 단계와 Stage B/C의 준비 자산으로 재사용한다.

## Public Preview Retention Contract

| 데이터 | 기본 처리 |
|---|---|
| 사용자 질문 | 실행 중 memory/tmp에만 존재, log·영구 DB 저장 금지 |
| 검색어 | upstream 요청에만 사용, 영구 저장 금지 |
| HTML·PDF·JSON 원문 | 격리된 임시 작업공간, 보고서 조립 후 우선 삭제 |
| Passage·중간 추출물 | 임시 작업공간, Run 종료 후 삭제 |
| 최종 보고서 | 즉시 반환 또는 최대 30분 임시 보관 |
| 미수령 완료 결과 | 생성 후 최대 60분에 강제 삭제 |
| 실패 작업 content | 실패 확정 후 10분 이내 삭제 |
| 실행 중 작업공간 | 생성 후 최대 60분, 절대 상한 2시간 |
| token·cookie·credential | 저장 및 downstream 전달 금지 |
| abuse counter | 회전 HMAC key 기반 비식별 bucket, 최대 7일 |
| aggregate metric | 질문·원문 없는 건수·시간·성공률만 보관 |

성공적인 결과 수령 뒤 content는 60초 이내 purge 대상으로 표시한다. TTL은 운영 설정으로 더 짧게 할 수 있지만 공개 약속보다 길게 늘리려면 새 Product/Security 결정을 요구한다.

## Minimum Public Safety

Public Preview를 열기 전에 다음이 모두 필요하다.

1. IP와 익명 capability 단위 rate/concurrency quota
2. SSRF 방어와 redirect마다 public IP 재검증
3. HTTPS 공개 source만 허용하고 localhost·private·link-local·metadata endpoint 차단
4. request, 다운로드, 압축해제, parser, 결과 크기와 실행시간 제한
5. 사용자 cookie·credential·private document upload 미지원
6. captcha·paywall·로그인·접근제한 우회 미지원
7. raw content·질문이 log, trace, metric, crash dump에 없는지 검사
8. TTL sweeper와 startup orphan purge
9. 정상 전달·timeout·worker crash·process restart 후 purge 검증
10. 비용 상한과 긴급 차단 스위치

## Product Validation

Stage B는 일정이 아니라 사용자 증거로 시작한다. 초기 추천 trigger는 다음과 같다.

- 4주 연속 주간 완료 조사 100건 이상
- 완료 결과 수령률 60% 이상
- 자발적 유용성 응답 50건 이상에서 긍정 60% 이상
- History·저장·재사용 요청 20명 이상
- abuse와 1회 조사 비용이 운영 상한 안에 있음

수치는 Public Preview 운영 전 Product 문서에서 조정할 수 있으나, “저장이 있으면 좋을 것 같다”는 내부 추측만으로 Stage B를 시작하지 않는다.

## Consequences

- 초기 사용 장벽과 개인정보·저작권 보관 위험이 낮아진다.
- 실제 조사 품질과 사용자 수요 검증에 집중할 수 있다.
- 장기 재사용·Living Report·팀 협업은 초기에는 제공하지 않는다.
- 결과 전달 실패에 대비해 짧은 TTL의 임시 저장과 opaque handle이 필요하다.
- 기존 OAuth·PostgreSQL·Tenant 코드는 폐기하지 않지만 Public Preview 요청의 필수 경로에서 제외한다.
- 공개 endpoint는 로그인 대신 더 강한 edge abuse·SSRF·비용 통제가 필요하다.

## Rejected Alternatives

- 처음부터 로그인·기관승인 필수: 실제 효용 검증 전에 가입 장벽과 운영범위를 키운다.
- 완전 동기식·완전 무상태만 허용: 긴 PDF와 다중 source 조사에서 연결 종료 시 결과를 잃는다.
- 모든 조사 자동 저장: 공개 서비스의 개인정보·저작권·비용 위험을 불필요하게 높인다.
- 기존 Tenant foundation 폐기: 후속 선택 저장과 팀 기능에 이미 검증된 자산을 버리게 된다.

## Revisit Triggers

- 사용자가 저장·History·재사용을 반복적으로 요청
- 결과 크기나 실행시간이 현재 TTL 모델을 지속적으로 초과
- 공개 남용 비용이 edge 통제로 관리되지 않음
- 기관 또는 유료 고객이 보존·감사·팀 기능을 요청
- 법률·약관·개인정보 검토가 retention contract 변경을 요구
