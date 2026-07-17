# 한국어 조사보고서 작성

## 목차

1. 기본 산출물
2. `brief.json` 작성
3. 검증 규칙
4. 보고서 재생성
5. 품질 확인

## 1. 기본 산출물

`research run`은 다음 파일을 생성한다.

```text
.psr/runs/<run-id>/
├─ result.json
├─ brief.json
├─ report.md
└─ report.html
```

기본 `brief.json`은 원문 구간을 그대로 줄인 보수적 초안이다. 사람이 읽을 최종 보고서는
에이전트가 `result.json`의 citation만 사용해 핵심 내용·시사점·권고를 정리한 뒤 다시 생성한다.

## 2. `brief.json` 작성

```json
{
  "schema_version": "1.0",
  "title": "조사보고서 제목",
  "subtitle": "조사 범위와 목적을 설명하는 한 문장",
  "executive_summary": [
    {
      "kind": "FACT",
      "text": "원문이 직접 확인해 주는 핵심 내용",
      "citation_ids": ["cit-..."]
    }
  ],
  "key_findings": [
    {
      "id": "finding-slug",
      "title": "확인사항 제목",
      "kind": "FACT",
      "text": "업무담당자가 이해할 수 있는 설명",
      "citation_ids": ["cit-..."],
      "track_id": "government-policy"
    }
  ],
  "implications": [
    {
      "kind": "INFERENCE",
      "text": "확인된 사실에서 도출한 업무상 의미",
      "citation_ids": ["cit-..."]
    }
  ],
  "recommendations": [
    {
      "kind": "RECOMMENDATION",
      "text": "담당자가 검토할 실행안",
      "citation_ids": ["cit-..."]
    }
  ],
  "open_questions": ["추가 확인이 필요한 사항"]
}
```

한 항목에는 하나의 명확한 주장만 쓴다. 영문 원문을 번역할 때 의무 강도와 적용범위를
과장하지 않는다. 숫자·시행일·적용대상은 원문이 직접 확인하는 범위만 적는다.

## 3. 검증 규칙

- `FACT`: 하나 이상의 유효한 `citation_ids`가 필수다.
- `INFERENCE`: 근거가 되는 citation이 필수며, 원문 사실과 해석을 섞지 않는다.
- `RECOMMENDATION`: 권고임을 명시한다. citation은 선택이지만 근거가 있으면 연결한다.
- 존재하지 않는 citation ID가 하나라도 있으면 보고서를 생성하지 않는다.
- `key_findings[].id`는 보고서 안에서 중복할 수 없다.
- HTML에는 사용자 입력을 escape하고 외부 CDN·폰트·추적 코드를 넣지 않는다.

## 4. 보고서 재생성

```bash
python3 <skill-directory>/scripts/psr.py --project <project> report build <run-id> \
  --brief-file <brief.json> --format all
```

- `--format md`: Markdown만 갱신
- `--format html`: HTML만 갱신
- `--format all`: 두 형식 모두 갱신

입력한 brief는 `.psr/runs/<run-id>/brief.json`에 정규화해 저장한다. 이후 네트워크 없이
`report build <run-id>`를 실행해 같은 보고서를 재생성할 수 있다.

## 5. 품질 확인

- 첫 화면에 질문, 기준일, 조사상태, 공식자료 수, 추가 확인 수가 보이는가?
- 각 사실과 해석에서 근거 버튼이 열리는가?
- 근거에서 공식 원문과 수집 당시 원문으로 이동할 수 있는가?
- `PARTIAL`, 조사 공백, 실패가 보고서에서 숨겨지지 않았는가?
- 메뉴·푸터·쿠키·로그인 문구가 핵심 확인사항에 포함되지 않았는가?
- 모바일 폭, 키보드, 인쇄, JavaScript 비활성 상태에서 읽을 수 있는가?
