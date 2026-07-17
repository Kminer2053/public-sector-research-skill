# Validation

## Main Gate

다음이 모두 통과해야 `main` release로 간주한다.

1. `SKILL.md` frontmatter와 폴더명 validation
2. Python 3.9+ syntax와 CLI import
3. Planner required·optional·conditional·include/exclude track test
4. HTML·JSON·TEXT·PDF parser test
5. public URL policy test
6. SQLite schema·snapshot·hash dedup test
7. 정상 E2E에서 `result.json`·`brief.json`·Markdown·HTML report 생성
8. 동일 source 재사용 test
9. 일부 source 실패 시 `PARTIAL` 보존 test
10. Evidence citation에 locator·SHA-256·score breakdown 포함
11. 네트워크 없이 Memory 검색·형식별 report rebuild
12. Codex metadata와 Claude marketplace JSON contract
13. `brief.json` citation 무결성, unknown ID, citation 없는 사실·해석 거부
14. HTML 사용자 문자열 escape, 외부 CDN·추적 리소스 없음, 내부 근거·로컬 snapshot 링크
15. HTML parser가 nav·header·footer·form을 근거 후보에서 제외

## 수동 Smoke

```bash
python3 skills/public-sector-research/scripts/psr.py project init /tmp/psr-smoke \
  --name "smoke"

python3 skills/public-sector-research/scripts/psr.py --project /tmp/psr-smoke \
  research plan "공공기관 AI 구매 시 개인정보와 데이터 권리를 조사하라"
```

fixture source manifest로 `research run`을 실행하고 다음 파일을 확인한다.

- `.psr/research.db`
- `.psr/runs/<run-id>/plan.json`
- `.psr/runs/<run-id>/result.json`
- `.psr/runs/<run-id>/brief.json`
- `.psr/runs/<run-id>/report.md`
- `.psr/runs/<run-id>/report.html`
- `.psr/reports/<run-id>.md`
- `.psr/reports/<run-id>.html`
- `.psr/sources/.../original.*`
- `.psr/sources/.../metadata.json`

실제 공식 URL smoke는 네트워크, robots, 원문 변경에 영향을 받으므로 unit test와 분리한다.

## HTML 수동 QA

최소 390px, 768px, 1440px에서 다음을 확인한다.

- 가로 스크롤이나 잘린 텍스트가 없음
- 목차 anchor와 scroll progress가 동작
- 근거 버튼이 해당 citation 상세를 열고 `Esc`로 닫힘
- 사실·해석·권고 필터의 `aria-pressed`와 표시 상태가 일치
- 공식 원문과 로컬 보존본 링크가 올바름
- JavaScript 비활성 상태에서도 전체 내용과 근거 목록을 읽을 수 있음
- 인쇄 미리보기에서 탐색 UI가 숨고 카드가 불필요하게 분할되지 않음
