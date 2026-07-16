# Direct Gateway and OCI Build Reproducibility Validation

> 날짜: 2026-07-16 · 환경: macOS arm64 local · 판정:
> **LOCAL CONTRACT PASS / NGINX OCI CI·STAGING PENDING**

[Gateway Runbook](../runbooks/direct-nginx-gateway.md) ·
[Container Runbook](../runbooks/container-public-preview.md) ·
[Validation Criteria](../VALIDATION_CRITERIA.md) ·
[Threat Model](../security/THREAT_MODEL.md)

## 1. 목적

다음 두 위험을 닫기 위한 change다.

1. OCI runtime dependency는 해시 검증되지만 `uv` bootstrap과 PEP 517 build backend가 완전히
   고정되지 않았던 공급망 공백
2. Application의 trusted-proxy 방어는 구현됐지만 실제 gateway 기준 설정이 없어
   `X-PSR-Client-IP` overwrite와 edge quota가 운영자 해석에 맡겨졌던 공백

## 2. OCI builder 보강

변경:

- `hatchling==1.31.0` exact pin
- `requirements/container-build.in`
- `requirements/container-build.txt`
- `uv==0.11.15`, Hatchling과 transitive dependency의 SHA-256 hash
- builder bootstrap의 `pip --require-hashes --only-binary=:all:`
- runtime dependency wheel 생성의 `--require-hashes --only-binary=:all:`
- project wheel은 사전 설치한 pinned Hatchling으로 `uv build --no-build-isolation`

확인:

```text
uv offline wheel build: PASS
selected Hatchling: 1.31.0
build requirement packages: 6
unhashed build requirement: 0
build-tool OSV known vulnerability: 0
clean hashed builder install: PASS
patched builder no-isolation wheel build: PASS
```

초기 감사에서 `uv 0.11.14`의
[`GHSA-4gg8-gxpx-9rph`](https://github.com/advisories/GHSA-4gg8-gxpx-9rph)를 발견했다.
이 버전은 악성 wheel의 entry-point name을 통한 환경 밖 file write 가능성이 있고 별도
workaround가 없어, patched `0.11.15`로 즉시 교체하고 hash·CI version·검증기를 함께
갱신했다.

실제 Linux OCI build와 amd64/arm64 wheel availability는 GitHub Actions 실행 전까지 PENDING이다.

## 3. Direct NGINX gateway

추가:

- `deploy/nginx/nginx.conf`
- `deploy/nginx/templates/psr-public.conf.template`
- `deploy/nginx/entrypoint/15-psr-validate-env.sh`
- `scripts/verify_gateway_contract.py`
- `tests/unit/test_gateway_contract.py`
- pinned NGINX syntax gate in `.github/workflows/ci.yml`
- [Direct Gateway Runbook](../runbooks/direct-nginx-gateway.md)

고정한 보안속성:

- TLS 1.2/1.3
- unknown SNI handshake 거부
- Host·upstream·port·TLS mount의 pre-render fail-closed 검증
- exact `/mcp`, 그 외 404
- client forwarding/IP/credential header 모두 제거
- `X-PSR-Client-IP=$remote_addr`로 overwrite
- canonical Host와 random request ID 재생성
- IP/global request·connection limit
- body 1 MiB와 bounded timeout
- request/response buffering, cache, upstream retry 금지
- content-free access log와 critical-only error log
- non-root/read-only/tmpfs syntax validation

이 기준은 direct ingress 전용이다. CDN/LB 앞단은 별도 trusted-CIDR·real-IP 설계 전 지원하지
않는다.

## 4. Local 실행 결과

```text
container static contract: PASS
gateway static contract: PASS
container/gateway contract unit tests: 10 passed
TLS reverse-proxy integration tests: 2 passed
spoofed IP values sent: 4
upstream canonical client IP: 203.0.113.10
upstream sensitive forwarding/credential headers: 0
full regression with PostgreSQL 17: 501 passed
raw coverage: 95.13%
normalized statement coverage: 96.24%
branch coverage: 90.75%
critical module statement minimum: 95.00%
ruff/format: PASS
mypy strict: PASS (154 files)
project lock OSV: 53 packages, known vulnerability 0
OCI build tools OSV: 6 packages, known vulnerability 0
Markdown links/fences: 47 files, missing/unbalanced 0
ruff targeted: PASS
format targeted: PASS
git diff --check: PASS
```

TLS 시험은 실제 loopback TCP와 test CA를 사용했다. 외부 요청에 bearer, cookie,
`Forwarded`, `X-Forwarded-For`, `X-Real-IP`, `X-PSR-Client-IP`를 넣었지만 proxy가 모두
폐기했다. Application trusted-proxy middleware는 새 canonical IP를 소비한 뒤 해당 header도
downstream에서 제거했다.

## 5. Content Retained

- 사용자 질문·검색어·원문·결과: 저장 0
- TLS test certificate/key: pytest 임시 directory, test 종료 후 fixture 정리 대상
- build audit wheel: `/tmp`의 source package artifact만 존재
- gateway access log test content: raw IP·URI·header·body 없음

## 6. 아직 통과로 기록하지 않는 항목

로컬에 Docker/Podman/nerdctl/buildctl이 없으므로 다음은 PENDING이다.

- pinned NGINX image pull
- official entrypoint envsubst 실제 render
- `nginx -t`
- Linux UID 101 read-only/tmpfs startup
- gateway→application container network
- 실제 TLS certificate chain
- 실제 public IP별 quota
- platform log canary
- CDN/LB topology

또한 application OCI artifact의 실제 build/smoke도 기존과 같이 GitHub Actions 실행 전
`VAL-PUB-EDGE-012 PASS`로 승격하지 않는다.

## 7. 판정

공개 gateway의 기준 구성과 자동 정적검증, TLS spoof 통합시험은 로컬 PASS다.
`VAL-PUB-EDGE-002~004`의 구현 전제는 갖췄지만 실제 NGINX OCI CI와 staging rehearsal이
남았으므로 PG3 또는 Public Preview Ready로 표현하지 않는다.
