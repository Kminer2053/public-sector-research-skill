# Supply-chain Artifacts

## Versioned artifact

- `dependency-licenses.json`: `uv.lock`의 cross-platform runtime dependency closure와 package metadata license
- 생성/검증: `python scripts/dependency_licenses.py [--check]`

현재 platform에 설치되지 않는 conditional package 4종은 PyPI metadata를 수동 검토해 script에 명시한다. lock version 변경 시 다시 검토한다.

| Package | 검토 license |
|---|---|
| colorama | BSD-3-Clause |
| greenlet | MIT AND PSF-2.0 |
| pywin32 | PSF-2.0 and bundled license files |
| tzdata | Apache-2.0 |

`pywin32`는 source tree의 개별 license file이 최종 근거이므로 Windows distribution 전 NOTICE 검토가 필요하다.

## CI-generated artifact

- `uv audit --preview-features audit --frozen`: OSV known vulnerability gate
- `uv export --preview-features sbom-export --frozen --no-dev --format cyclonedx1.5`: release SBOM
- `uv build`: wheel/sdist

SBOM은 timestamp와 UUID가 있어 version control에 고정하지 않고 release build에서 생성한다. dependency license manifest는 drift review를 위해 version control에 둔다.

## Open decision

이 repository 자체의 distribution license와 NOTICE 정책은 아직 결정되지 않았다. dependency manifest는 project license 결정을 대신하지 않는다. 외부 배포·Pilot package 발행 전에 Product/Legal owner가 LICENSE/NOTICE를 승인해야 한다.
