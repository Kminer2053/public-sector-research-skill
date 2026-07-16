# Trusted Proxy Client IP Boundary 검증

> 기준일: 2026-07-16 · 판정: **Application Local PASS / Gateway Rehearsal Pending**

[Architecture](../ARCHITECTURE.md) · [Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](../runbooks/public-preview.md) ·
[Threat Model](../security/THREAT_MODEL.md)

## 1. 목적

공개 MCP가 reverse proxy 뒤에서 모든 사용자를 proxy IP 하나로 보거나, 직접 접속자가 전달
header를 위조해 새 quota bucket을 얻는 문제를 방지한다.

## 2. 구현한 경계

- `PSR_TRUSTED_PROXY_CIDRS`에 포함된 peer만 `X-PSR-Client-IP`를 제공할 수 있다.
- 값은 IPv4 또는 IPv6 한 개만 허용한다.
- trusted peer의 header 누락, 비정상 IP, 쉼표 목록은 HTTP 400으로 fail closed한다.
- trusted network 밖의 peer가 보낸 같은 header는 client identity로 사용하지 않는다.
- header는 client IP를 `scope.client`로 정규화한 뒤 downstream application에 전달하기 전에
  제거한다.
- rate limiter는 정규화된 IP를 rotating HMAC bucket으로 변환하며 raw IP를 log·DB에
  기록하지 않는다.
- production public mode는 trusted proxy CIDR이 없으면 startup에 실패한다.

## 3. 자동 검증

| 조건 | 기대값 | 결과 |
|---|---|---|
| trusted proxy, 같은 canonical client IP 반복 | 설정 한도 뒤 429 | PASS |
| trusted proxy, 다른 canonical client IP | 독립 bucket | PASS |
| untrusted peer가 header 값 회전 | peer IP quota 유지 | PASS |
| trusted proxy header 누락 | 400 | PASS |
| 비정상 IP 또는 comma-separated chain | 400 | PASS |
| downstream header 관찰 | 제거됨 | PASS |
| CIDR host bits 포함 | canonical network로 정규화 | PASS |
| production public + CIDR 누락 | startup 실패 | PASS |

전체 회귀:

```text
423 passed (398 non-PostgreSQL + 25 PostgreSQL)
```

Coverage:

```text
raw total: 95.08%
normalized statement: 96.17%
branch: 90.79%
critical module statement minimum: 95.0%
status: pass
```

## 4. 운영 계약

Gateway는 외부 요청의 `X-PSR-Client-IP`를 전달하면 안 된다. 연결 peer와 gateway 자체의
신뢰 가능한 메커니즘으로 원 client IP를 확인한 뒤, header를 단일 canonical IP로 overwrite한다.
application process에는 gateway network만 접근하도록 방화벽을 구성하는 것을 권장한다.

## 5. 남은 검증

- 실제 TLS terminating reverse proxy 설정에서 header overwrite 확인
- 직접 origin 접근 차단과 spoof rehearsal
- edge raw-IP quota가 application limiter보다 먼저 동작하는지 확인
- multi-replica 환경의 공유 quota backend
- IPv4/IPv6 dual-stack과 CDN chain 운영정책

따라서 이 결과는 application 경계의 로컬 통과이며, Public Preview 배포 완료 판정은 아니다.
