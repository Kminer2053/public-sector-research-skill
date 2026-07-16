# Public Sector Research Agent

공공분야 업무담당자가 Codex, Claude Code, Agent Skills 호환 호스트 또는 일반 CLI에서 공식 원문 중심의 조사를 수행하고, 근거를 사용자 PC에 저장·검토·재사용할 수 있게 하는 범용 Evidence Research Skill입니다.

```text
AI 호스트의 검색·브라우저
→ 공통 SKILL.md
→ 로컬 psr CLI
→ 계획·수집·파싱·Evidence Score
→ .psr/research.db + 원문 snapshot
→ Markdown/JSON 검토 보고서
```

`main`은 로컬 범용 Skill과 provider-neutral Core만 포함합니다. 원격 MCP, 공개 서버, 로그인, 클라우드 저장, 유료화 코드는 제품 단계 브랜치에서 개발합니다.

## 현재 제공 기능

- Government/Public Sector Research Profile
- 법령·정책·조달·개인정보·국제표준 track 계획
- 호스트가 찾은 URL 또는 사용자 로컬 파일 입력
- HTTP(S)·공개주소·robots·byte·timeout 경계
- HTML·JSON·TEXT 및 선택형 PDF Passage 추출
- SHA-256 기반 문서 중복 제거와 최근 snapshot 재사용
- 구성요소가 설명되는 Evidence Score
- SQLite Evidence Index와 파일시스템 원문 저장
- 부분실패 보존
- 한국어 Markdown 및 JSON 보고서
- Codex metadata와 Claude Code plugin marketplace metadata

## 설치

### Codex

Skill installer로 저장소의 Skill 경로를 설치합니다.

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo Kminer2053/public-sector-research-mcp \
  --path skills/public-sector-research
```

### Claude Code

Claude Code에서 저장소를 marketplace로 등록한 뒤 Skill plugin을 설치합니다.

```text
/plugin marketplace add Kminer2053/public-sector-research-mcp
/plugin install public-sector-research@public-sector-research-agent
```

### 공통 설치 스크립트

저장소를 clone한 환경에서는 다음 명령으로 Codex, Claude, `~/.agents/skills`에 설치할 수 있습니다.

```bash
python3 scripts/install_skill.py --target all
```

### CLI 패키지

Skill은 설치 없이 bundled script로 실행할 수 있습니다.

```bash
python3 skills/public-sector-research/scripts/psr.py --version
```

패키지 설치 시 `psr` console command를 제공합니다. PDF 처리가 필요하면 `pdf` extra를 설치합니다.

```bash
python3 -m pip install -e ".[pdf]"
```

## 빠른 사용

```bash
python3 skills/public-sector-research/scripts/psr.py \
  project init ./example-project --name "AI 구매원칙"

python3 skills/public-sector-research/scripts/psr.py \
  --project ./example-project research plan \
  "공공기관 생성형 AI 구매 시 데이터 권리와 업체 종속 방지 원칙을 조사하라"
```

계획이 생성한 query로 공식 출처를 찾고 `sources.jsonl`을 작성한 뒤 실행합니다.

```bash
python3 skills/public-sector-research/scripts/psr.py \
  --project ./example-project research run <run-id> \
  --sources-file sources.jsonl
```

결과:

```text
example-project/.psr/
├─ research.db
├─ profiles/
├─ runs/<run-id>/
│  ├─ plan.json
│  ├─ result.json
│  └─ report.md
├─ sources/<source-id>/documents/<document-id>/snapshots/<snapshot-id>/
│  ├─ original.*
│  ├─ extracted.md
│  └─ metadata.json
└─ reports/<run-id>.md
```

## 문서

- [VISION](docs/VISION.md)
- [PRD](docs/PRD.md)
- [ARCHITECTURE](docs/ARCHITECTURE.md)
- [ROADMAP](docs/ROADMAP.md)
- [BRANCH STRATEGY](docs/BRANCH_STRATEGY.md)
- [VALIDATION](docs/VALIDATION.md)

## 제품 경계

- 자동 법률·감사·조달 판단을 제공하지 않습니다.
- 로그인, CAPTCHA, paywall, 접근제한을 우회하지 않습니다.
- 외부 원문과 조사자료를 중앙 서버로 전송하지 않습니다.
- AI 호스트가 수행한 검색의 데이터 처리정책은 해당 호스트에 따릅니다.
- 발행일·현행성·적용범위와 Evidence Score는 사람이 최종 검토해야 합니다.

이전 원격 MCP Public Preview 구현은 `archive/mcp-public-preview-2026-07-16`에 보존합니다.
