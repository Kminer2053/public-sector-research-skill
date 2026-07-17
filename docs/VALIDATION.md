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
12. brief citation 유효성, HTML escape, 내부 근거·로컬 snapshot 링크
13. Codex metadata와 Claude marketplace JSON contract

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
