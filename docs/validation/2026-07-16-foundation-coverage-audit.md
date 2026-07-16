# Foundation Coverage Gate 감사 보고서 — 2026-07-16

> 대상: F2 PostgreSQL Durability · F3 OAuth Resource Server · F4 Remote Conformance · 검증 보강 commit: `952e173`

[검증 기준](../VALIDATION_CRITERIA.md) · [구현 계획](../IMPLEMENTATION_PLAN.md) · [Remote G5 보고서](./2026-07-16-remote-g5.md)

## 1. 결론

완료 감사에서 기존 `pytest-cov`의 combined percentage만으로는 다음 세 기준을 각각 증명할 수 없음을 확인했다.

- 전체 executable statement 90% 이상
- 전체 branch 85% 이상
- domain·application·authorization policy critical module statement 95% 이상

동일한 PostgreSQL 17.10·OAuth·TCP/TLS 전체 suite를 coverage JSON으로 재측정한 최초 결과는 statement `93.27%`, branch `79.84%`였다. 기존 combined `90%` gate는 통과했지만 branch 기준은 실패했다. 따라서 이 시점의 branch gate 통과 주장은 증거가 부족했다.

commit `952e173`에서 security/configuration, OIDC/JWKS, cursor integrity, Run/Job invariant와 worker opaque error를 보강하고 별도 CI gate를 추가했다. 최종 결과는 다음과 같다.

| 기준 | 요구 | 관찰 | 판정 |
|---|---:|---:|---|
| 전체 executable statements | ≥ 90% | 95.02% (`2118/2229`) | PASS |
| 전체 branches | ≥ 85% | 87.10% (`432/496`) | PASS |
| critical module statements | 각 ≥ 95% | 최소 95.00% | PASS |
| 전체 test | 모두 성공 | 185 passed | PASS |

이 보고서는 coverage 품질 기준만 닫는다. Codex Resource/Prompt 승인 대기로 인한 `G5 PARTIAL`, 실제 기관 IdP/gateway, G6 owner 승인은 그대로 열린다.

## 2. 보강 범위

- production/development 구성의 URL, scope, algorithm, issuer, JWKS origin fail-closed 분기
- JWT optional claim 최소공개, malformed Discovery/JWKS root, JWK `key_ops`·algorithm 거부
- OIDC verifier 소유 HTTP client lifecycle
- ResearchRun fingerprint·terminal timestamp invariant
- Job attempt·lease·heartbeat·terminal outcome invariant
- HMAC cursor의 secret 길이, 길이 제한, malformed input, signed-invalid payload
- worker heartbeat/complete의 opaque missing-target error
- coverage artifact 자체의 malformed/fail/pass 동작

## 3. 재현 명령

PostgreSQL test URL을 설정한 환경에서:

```bash
pytest --cov=psr_mcp --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json
python scripts/coverage_gate.py --coverage-json coverage.json
```

최종 gate 출력:

```json
{"branch_percent": 87.1, "critical_statement_percent_minimum": 95.0, "statement_percent": 95.02, "status": "pass"}
```

추가 품질 검증:

```text
ruff check: PASS
ruff format --check: PASS
mypy --strict src tests scripts: PASS
dependency license manifest: PASS
offline sdist/wheel build: PASS
```

## 4. CI 회귀 방지

`.github/workflows/ci.yml`은 `coverage.json`을 생성한 뒤 `scripts/coverage_gate.py`를 실행한다. 다음 중 하나라도 발생하면 job이 실패한다.

1. 전체 statement가 90% 미만
2. 전체 branch가 85% 미만
3. `src/psr_mcp/domain/`, `src/psr_mcp/application/`, `src/psr_mcp/auth/policy.py` 중 executable statement가 있는 module이 95% 미만
4. coverage JSON이 없거나 malformed이거나 covered count가 total을 초과

combined percentage는 참고 수치일 뿐 독립 기준을 대체하지 않는다.
