# ADR-0010 — Progressive Identity, Opt-in Persistence, and Evidence Reuse

> 상태: Accepted · 날짜: 2026-07-16 · 결정자: Product owner

## Context

Public Preview의 최우선 목표는 가입 장벽 없이 실제 조사 유용성을 검증하는 것이다. 동시에 반복
사용자가 생기면 과거 조사, 근거 재사용, 갱신과 저장공간을 원하는 수요가 발생할 수 있다. 계정과
영구저장을 지금 필수 경로에 넣으면 공개 실험 속도를 늦추지만, 경계를 미리 설계하지 않으면 나중에
익명 content를 소급 저장하거나 public deployment에 persistent sink를 혼합하는 위험이 생긴다.

## Decision

### 1. 익명 공개 사용은 영구 기능이다

- `PUBLIC_EPHEMERAL`은 Account Beta 이후에도 제거하지 않는다.
- 공개 Tool은 로그인 없이 계속 호출할 수 있다.
- 익명 사용자의 질문·원문·결과는 전달 또는 TTL 뒤 삭제한다.
- 계정 기능 장애가 공개 조사 경로를 중단시키지 않도록 deployment와 composition root를 분리한다.

### 2. 계정은 사용 허가가 아니라 선택형 편의 기능이다

- Account Beta는 OIDC broker를 사용하고 자체 비밀번호를 보관하지 않는다.
- 초기 Beta는 운영 안정성을 위해 관심 사용자 초대 방식으로 열고, 검증 뒤 self-service로
  확대할 수 있다. 익명 공개 사용은 초대나 가입으로 제한하지 않는다.
- 가입만으로 조사 content를 저장하지 않는다.
- 인증된 요청도 기본 `retention_mode`는 `ephemeral`이다.
- 공개 사용자와 가입 사용자는 같은 official-first 품질 기준을 적용받는다. 무료 공개 결과의
  근거 품질을 낮춰 가입이나 결제를 유도하지 않는다.

```text
retention_mode=ephemeral  # 익명·가입 사용자 모두 가능, 기본값
retention_mode=saved      # 인증 사용자만 가능, 명시적 선택
```

### 3. 저장 요청은 실행 전에 확정한다

- `saved` 요청은 인증, consent version, quota와 persistent storage 가용성을 실행 전에 검증한다.
- 저장을 보장할 수 없으면 `PERSISTENCE_UNAVAILABLE`로 조사 시작 전에 실패한다.
- 사용자가 저장을 요청했는데 결과를 몰래 ephemeral로 강등하지 않는다.
- 익명으로 이미 완료한 조사는 서버에 남아 있지 않으므로 계정에 소급 연결하지 않는다.
- 사용자는 받은 Markdown/JSON을 향후 Account Workspace에 직접 import할 수 있다.

### 4. 저장된 조사만 개인화 기능의 입력이 된다

- History, Evidence reuse, freshness check, refresh, Project Memory는 `saved` 조사만 사용한다.
- ephemeral 질문과 결과를 추천·학습·프로파일링에 사용하지 않는다.
- Personal Workspace 데이터는 사용자 단위 RLS와 object namespace로 격리한다.
- export, 개별 삭제, account close를 제공한 뒤 Account Beta를 연다.

### 5. 자동 재사용은 최신성과 provenance를 숨기지 않는다

가입 사용자는 Personal Workspace에 저장한 조사와 Evidence를 후속 질문에서 재사용할 수 있다.
자동 재사용은 다음 별도 설정으로 통제한다.

```text
reuse_mode=off             # 저장자료를 읽지 않음
reuse_mode=prefer_fresh    # fresh 저장근거 우선, 부족하거나 stale이면 새 조사
reuse_mode=saved_only      # 저장자료만 사용하고 새 network 조사는 하지 않음
```

- 신규 계정의 `reuse_mode` 기본값은 `off`다.
- 사용자가 Workspace에서 재사용을 한 번 명시적으로 켜면 기본값을 `prefer_fresh`로 저장할 수
  있으며, 요청마다 다시 끌 수 있다.
- 재사용 전 `fresh`, `stale`, `unknown`을 판정한다. 법령·정책처럼 최신성이 핵심인 문서는
  profile별 freshness rule을 적용한다.
- `stale` 또는 `unknown` Evidence를 사실상 최신 자료처럼 조용히 사용하지 않는다.
- 결과에는 재사용한 Evidence, 새로 수집한 Evidence, freshness 판정, refresh 실패와 남은
  공백을 구분해 표시한다.
- 삭제된 조사와 Evidence는 즉시 재사용 후보에서 제외한다.
- 다른 사용자의 저장자료와 Public Preview의 ephemeral content는 재사용 후보가 될 수 없다.
- 자동 재사용은 조사 비용과 시간을 줄이는 기능이지, 근거 검증을 생략하는 기능이 아니다.

### 6. 무료 Account Beta와 유료 기능을 분리한다

- Account Beta는 초기 팬과 반복 사용자가 제품 가치를 검증하는 무료·제한형 단계다.
- 무료 Beta에는 제한된 저장공간, History, freshness 표시와 Evidence reuse를 제공할 수 있다.
- 계정 생성, 저장량, 자동 재사용률과 refresh 비용을 먼저 측정한다.
- 저장공간, 장기 실행, 예약 refresh, 높은 quota처럼 지속 비용이 발생하는 기능만 이후 유료
  후보가 된다.

### 7. 유료화는 저장과 운영비가 검증된 뒤 추가한다

- 무료 공개 조사의 공식자료 우선 원칙과 근거 품질을 낮춰 유료 전환을 유도하지 않는다.
- 유료 가치는 저장공간, 긴 실행, 높은 quota, 갱신, 고급 export와 지원에서 만든다.
- 가격, quota, retention, backup, 삭제정책을 결제 전에 표시한다.
- 결제정보와 연구 content의 접근권한을 분리한다.

## Mode Boundary

| Mode | 인증 | 기본 보존 | persistent write 조건 |
|---|---|---|---|
| `PUBLIC_EPHEMERAL` | 없음 | 무보관 | 항상 금지 |
| `ACCOUNT_OPT_IN` | OIDC | 무보관 | 인증 + `saved` + consent + quota |
| `PAID_PERSISTENT` | OIDC | 상품정책 | 계약 + 명시적 retention |
| `ENTERPRISE` | 기관 SSO | 기관정책 | tenant policy + 권한 |

아직 구현되지 않은 mode는 Foundation 또는 Public composition으로 대체 실행하지 않고 startup에서
fail closed한다.

## Consequences

### Positive

- 지금은 조사 품질과 공개 사용성에 집중할 수 있다.
- 향후 팬과 반복 사용자는 기존 공개 흐름을 잃지 않고 기능을 확장할 수 있다.
- 무의식적 저장과 익명 content의 소급 귀속을 방지한다.
- 인증·저장·과금 장애의 blast radius를 public service와 분리할 수 있다.

### Trade-offs

- 익명 조사는 서버 측 자동 재사용이 불가능하다.
- 사용자가 익명 결과를 나중에 저장하려면 직접 export/import해야 한다.
- Account/Paid mode마다 별도 보안·삭제·복구 검증이 필요하다.
- 동일 codebase라도 mode별 배포·Tool catalog·data sink를 관리해야 한다.

## Activation Gates

Account Beta는 다음이 모두 충족될 때만 구현·공개한다.

1. Public Preview Product Validation Gate 통과
2. 저장·History·재사용 관심 사용자 20명 이상
3. 개인정보 처리방침과 consent UX 승인
4. OIDC login/provisioning, RLS, encryption, export/delete/account-close 검증
5. `retention_mode=ephemeral` persistent content zero test 통과
6. cross-user 접근과 mode 혼선 test 100% 통과
7. `reuse_mode`별 fresh/stale/unknown 동작과 재사용 provenance 표시 검증
8. Account 서비스 장애 중에도 익명 Public Preview가 정상 동작

Paid Persistent는 저장 사용량, 원가와 지불 의사가 확인되고 backup/restore, billing correctness,
deletion manifest와 독립 보안 검토가 끝난 뒤 활성화한다.

## Rejected Alternatives

- **처음부터 로그인 필수:** 유용성 검증 전에 전환 장벽과 개인정보 범위를 키운다.
- **가입하면 자동 저장:** 사용자의 기대와 Zero-Retention 기본값을 깨뜨린다.
- **가입 즉시 과거 자료 자동 재사용:** 사용자가 저장자료의 사용 여부를 통제하지 못하고 stale
  Evidence가 조용히 섞일 수 있다.
- **익명 조사 자동 소급 연결:** 삭제 약속과 익명성을 훼손한다.
- **한 process에서 mode별 repository를 동적 선택:** 구성 오류가 persistent content leak으로 이어질 수 있다.
- **무료 결과 품질을 제한해 유료화:** 제품의 공신력과 공공적 가치를 훼손한다.
