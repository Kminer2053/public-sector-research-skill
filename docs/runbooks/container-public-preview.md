# Public Preview Container Runbook

> 상태: OCI artifact 구현 · 실제 공개 gateway 배포 전

[Architecture](../ARCHITECTURE.md) · [Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Public Preview Runbook](./public-preview.md) · [Threat Model](../security/THREAT_MODEL.md)

## 1. 목적과 보안 계약

이 컨테이너는 가입 없는 `PUBLIC_EPHEMERAL` endpoint만 실행한다.

- image에는 코드와 runtime dependency만 포함한다.
- Account DB URL, OAuth issuer와 persistent content credential을 기본값이나 image layer에 넣지
  않는다.
- process는 numeric user/group `10001:10001`로 실행한다.
- root filesystem은 read-only로 실행한다.
- `/tmp`, `/var/lib/psr/ephemeral`, `/run/psr`만 tmpfs로 제공한다.
- 질문·원문·결과는 PostgreSQL, volume과 일반 log에 저장하지 않는다.
- 운영 필수 설정이 빠지면 server는 fail closed한다.

Dockerfile에 `VOLUME`을 선언하지 않는다. 선언하면 orchestrator가 의도하지 않은 persistent
anonymous volume을 만들 수 있으므로 ephemeral mount는 배포 명령에서만 명시한다.

## 2. Image Build

```bash
docker build --target runtime --tag psr-public:local .
python3 scripts/verify_container_contract.py
```

base image는 Python 3.12.13 slim Bookworm multi-platform digest에 고정한다. dependency는
`uv.lock`을 requirements로 export해 builder stage에서 wheel로 만든 뒤 runtime stage에 offline
install한다. dependency wheel 생성은 lockfile hash를 검증한다. `uv`와 source tree는 최종
runtime image에 복사하지 않는다.

로컬 Docker engine이 없는 개발환경에서는 static contract와 Python regression만 실행하고, OCI
build와 hardened runtime smoke는 GitHub Actions의 `Public Preview OCI gate`에서 수행한다.

## 3. 운영 필수 환경변수

| 변수 | 예 | 규칙 |
|---|---|---|
| `PSR_PUBLIC_URL` | `https://research.example.org` | 외부에서 보이는 HTTPS origin |
| `PSR_RESOURCE_SERVER_URL` | `https://research.example.org/mcp` | 같은 origin의 MCP endpoint |
| `PSR_ABUSE_HMAC_KEY_REF` | `env://PSR_ABUSE_HMAC_KEY` | secret reference만 설정 |
| `PSR_ABUSE_HMAC_KEY` | secret manager 주입 | 32 bytes 이상, image/manifest 금지 |
| `PSR_TRUSTED_PROXY_CIDRS` | `172.20.0.0/16` | 실제 reverse proxy network만 허용 |
| `PSR_PUBLIC_DAILY_QUICK_BUDGET` | `500` | 1 이상, 초기 비용상한 |
| `PSR_SEARCH_PROVIDER` | `curated` | 현재 제한 검증범위; live provider는 별도 승인 |

Dockerfile 기본값은 `PSR_ENV=production`, `PSR_SERVICE_MODE=public_ephemeral`,
`PSR_AUTH_MODE=static`, `PSR_STORAGE_MODE=memory`다. 운영 URL, abuse secret, trusted proxy와
daily budget이 없으면 시작하지 않는다.

## 4. Hardened 실행 예

아래는 topology 예시다. 실제 trusted proxy CIDR, URL, secret 전달 방식과 resource limit은
배포환경에서 확정한다.

```bash
docker run --detach --name psr-public \
  --read-only \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --pids-limit=256 \
  --memory=1g \
  --cpus=2 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --tmpfs /var/lib/psr/ephemeral:rw,noexec,nosuid,nodev,size=512m,mode=0700,uid=10001,gid=10001 \
  --tmpfs /run/psr:rw,noexec,nosuid,nodev,size=1m,mode=0700,uid=10001,gid=10001 \
  --env PSR_PUBLIC_URL=https://research.example.org \
  --env PSR_RESOURCE_SERVER_URL=https://research.example.org/mcp \
  --env PSR_ABUSE_HMAC_KEY_REF=env://PSR_ABUSE_HMAC_KEY \
  --env PSR_ABUSE_HMAC_KEY \
  --env PSR_TRUSTED_PROXY_CIDRS=172.20.0.0/16 \
  --env PSR_PUBLIC_DAILY_QUICK_BUDGET=500 \
  --env PSR_SEARCH_PROVIDER=curated \
  psr-public:local
```

`PSR_ABUSE_HMAC_KEY`의 실제 값은 shell history나 compose file에 쓰지 않고 secret manager 또는
배포플랫폼의 secret reference로 주입한다.

## 5. Edge 계약

컨테이너는 TLS를 직접 종료하지 않는다. reverse proxy/WAF가 다음을 수행한다.

1. 외부 HTTPS와 canonical Host 강제
2. body, connection과 IP rate limit
3. 사용자가 보낸 `X-PSR-Client-IP` 제거
4. 실제 client IP 하나만 `X-PSR-Client-IP`로 설정
5. application에는 trusted proxy network에서만 연결
6. private network egress 차단과 DNS 정책 적용

application의 `proxy_headers`는 꺼져 있다. 임의의 `X-Forwarded-For`를 신뢰하지 않으며
`PSR_TRUSTED_PROXY_CIDRS`의 peer에서 온 canonical header만 quota 입력으로 사용한다.

## 6. Liveness와 Readiness

Dockerfile에는 `HEALTHCHECK`이 없다.

- `psr.research.quick`을 healthcheck로 호출하면 실제 조사 budget과 feedback 지표를 오염시킨다.
- process/TCP liveness는 orchestrator가 확인한다.
- MCP readiness가 필요하면 낮은 빈도로 `psr.service.policy`만 호출한다.
- release 직전에는 `psrctl conformance-public`을 한 번 실행한다. 이 명령은 실제 quick budget을
  소비하므로 상시 healthcheck로 사용하지 않는다.

## 7. CI Container Smoke

CI는 final image와 동일한 `runtime-base`에서 파생한 `test` target을 사용한다.

```text
network=none
read-only root
all capabilities dropped
no-new-privileges
numeric non-root user
tmpfs only
development fixture only
```

`scripts/container_smoke.py`는 container 내부 loopback에서 official MCP SDK로
policy → quick → purge → feedback → reconnect를 검증한다. fixture이므로
`release_gate_checked=false`를 강제하고 공개 준비 PASS로 해석하지 않는다.

CI 완료 조건:

- container user `10001`
- root filesystem write 실패
- `/tmp`와 ephemeral root만 write 가능
- public Tool catalog와 schema conformance PASS
- quick 결과 `PURGED`
- feedback content link 없음
- smoke 뒤 ephemeral root empty
- final image entrypoint가 `["psr-mcp"]`

## 8. 배포 전 남은 외부 검증

- 실제 OCI build CI 통과
- image/SBOM 취약점 scan 정책
- 실제 TLS gateway header overwrite와 spoof rehearsal
- egress/private-route 검증
- production `psrctl doctor --require-public-ready`
- curated 또는 승인된 live provider의 실제 source smoke
- staging retention canary와 purge failure game day
- 두 MCP Host의 anonymous conformance
- 프로젝트 LICENSE/NOTICE 결정

이 runbook의 존재는 Public Preview 공개 승인을 의미하지 않는다.
