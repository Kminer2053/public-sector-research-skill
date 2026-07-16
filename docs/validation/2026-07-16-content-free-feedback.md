# Content-Free Public Feedback 검증

> 기준일: 2026-07-16 · 판정: **Application Local PASS / Public Product Sampling Pending**

[Architecture](../ARCHITECTURE.md) · [PRD](../PRD.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md)

## 1. 목적

질문·검색어·원문·결과를 서버에 남기지 않는 Public Preview에서도 사용자가 결과를 유용하게
느끼는지, 저장·History·재사용 기능을 원하는지 최소한으로 확인한다. feedback을 조사 content나
사용자 식별자와 연결하지 않으며 Account Beta의 근거가 될 aggregate signal만 만든다.

## 2. 구현한 경계

- quick workspace purge가 확인된 뒤에만 feedback token을 발급한다.
- token payload는 `version`, cryptographic `nonce`, `expiry`만 포함한다.
- signing key는 abuse HMAC secret에서 domain-separated HMAC으로 파생한다.
- `psr.feedback.submit`은 `helpful`, `save_feature_interest` boolean 두 개만 받는다.
- free text, question, result, operation/run/user/IP/Host ID field를 받지 않는다.
- raw token, 질문과 결과를 저장하거나 application log에 기록하지 않는다.
- 사용된 token은 SHA-256 digest만 process memory에 TTL 동안 보관해 replay를 거부한다.
- background sweeper는 만료 digest를 `PSR_PURGE_SWEEP_SECONDS` 이내에 제거한다.
- 변조, 만료와 재사용은 `FEEDBACK_TOKEN_INVALID_OR_USED` 하나로 응답한다.
- log에는 content-free cumulative submitted/helpful/save-interest count만 허용한다.

## 3. 자동 검증

| 조건 | 기대값 | 결과 |
|---|---|---|
| token payload | version·nonce·expiry만 존재 | PASS |
| content identifier | question/run/user/IP 복원 불가 | PASS |
| purge 순서 | workspace purge 확인 뒤 token 발급 | PASS |
| Tool input | boolean 두 개, free text 없음 | PASS |
| 정상 제출 | accepted, `content_linked=false` | PASS |
| token replay | 두 번째 제출 거부, 중복 집계 0 | PASS |
| 변조·형식오류·만료 | 동일 typed error | PASS |
| raw token application logging | 0건 | PASS |
| question canary application logging | 0건 | PASS |
| aggregate logging | count 세 종류만 기록 | PASS |
| digest retention | expiry 뒤 purge interval 이내 제거 | PASS |
| workspace content | feedback 제출 뒤 0건 | PASS |
| TTL 설정 | 300..604800초 외 startup validation 거부 | PASS |

전체 회귀:

```text
470 passed (445 non-PostgreSQL + 25 PostgreSQL)
```

Coverage:

```text
raw total: 95.36%
normalized statement: 96.38%
branch: 91.29%
critical module statement minimum: 95.0%
public feedback module statement/branch: 100% / 100%
public MCP server statement/branch: 100% / 100%
status: pass
```

정적·공급망 검증:

```text
ruff: pass
format: pass
strict mypy: pass (146 source files)
dependency license manifest: current
```

실제 TCP reconnect, TLS terminating reverse proxy와 PostgreSQL RLS 회귀를 포함한 전체 suite를
실행했다.

## 4. 운영 한계

현재 replay digest와 aggregate counter는 process-local이다. process restart 뒤 이미 사용된
token을 다시 제출하거나 여러 replica에 같은 token을 제출하면 중복 집계될 수 있다. 따라서
초기 제한 공개는 single-node 또는 sticky routing으로 운영한다.

durable metric sink를 추가할 때도 question, result, URL, raw token, user/IP/Host ID를 key나
dimension으로 추가하지 않는다. multi-replica 전환 전에는 TTL이 있는 shared token-digest set과
content-free aggregate counter만 별도 보안 검토한다.

## 5. 남은 검증

- 실제 공개 Host에서 feedback UI/호출 동선이 사용자를 방해하지 않는지 확인
- reverse proxy/WAF/Host request·response body logging 비활성 및 canary scan
- helpful 응답 50건 이상과 긍정률 60% 이상 표본 수집
- 저장·History·재사용 관심 사용자 20명 이상 여부 확인
- process restart와 multi-replica를 위한 content-free shared dedup 설계
- metric backend의 보존기간, 접근권한과 삭제정책 승인

따라서 이번 판정은 익명 feedback의 application privacy boundary 통과를 뜻하며, 실제 사용자가
제품을 유용하게 평가했다거나 Account Beta 시작 조건을 충족했다는 뜻은 아니다.
