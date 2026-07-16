# 호스트 이식성

Skill의 공통 단위는 `SKILL.md`, `scripts/`, `references/`다. 호스트마다 설치 위치와 권한 UX는 다르지만 실행 계약은 동일하다.

## Codex

Codex Skill 경로에 `skills/public-sector-research` 폴더를 설치한다. `agents/openai.yaml`은 Codex UI metadata이며 Core 동작에 영향을 주지 않는다.

## Claude Code

저장소를 plugin marketplace로 등록하거나 `skills/public-sector-research`를 Claude의 사용자·프로젝트 Skill 위치에 설치한다. `.claude-plugin/marketplace.json`은 이 저장소의 Skill 경로를 가리킨다.

## Agent Skills 호환 호스트

호스트가 Agent Skills 표준을 지원하면 동일 폴더를 해당 discovery 위치에 복사한다. GitHub Copilot 등은 `.agents/skills` 또는 제품별 경로를 사용할 수 있다.

## 셸 실행 가능한 기타 AI

Skill 자동발견이 없어도 다음 두 항목을 제공하면 된다.

1. `SKILL.md`의 workflow 지침
2. `python3 scripts/psr.py ...` CLI 실행 권한

## 웹 채팅 전용 환경

로컬 파일·프로세스를 실행할 수 없는 순수 웹 채팅은 이 로컬 Skill을 직접 실행할 수 없다. 향후 Hosted MCP/API adapter가 필요하며 해당 코드는 `main`이 아닌 제품 단계 브랜치에서 개발한다.

## 권한 차이

- 네트워크 접근 허용 여부
- 로컬 파일 쓰기 범위
- Python 및 선택 PDF 의존성
- 사용자 확인 UI
- 검색·브라우저 capability

가 호스트마다 다르다. 기능이 없으면 실패를 숨기지 말고 기존 Memory, 사용자 제공 URL, 로컬 파일 방식으로 축소한다.
