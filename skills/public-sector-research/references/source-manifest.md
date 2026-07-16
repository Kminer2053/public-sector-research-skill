# Source Manifest 계약

## JSONL 형식

한 줄에 하나의 JSON object를 기록한다.

```json
{"track_id":"privacy","url":"https://example.go.kr/guide.pdf","title":"개인정보 안내서","publisher":"개인정보보호위원회","source_tier":"OFFICIAL_PRIMARY","published_at":"2025-08-07"}
```

로컬 파일:

```json
{"track_id":"government-policy","path":"./input/internal-guidance.pdf","title":"내부 검토자료","publisher":"사용자 제공","source_tier":"LOCAL_FILE"}
```

## 필드

| 필드 | 필수 | 규칙 |
|---|---|---|
| `track_id` | 예 | plan에 존재하는 track ID |
| `url` | 조건부 | `path`와 둘 중 하나만 사용 |
| `path` | 조건부 | `url`과 둘 중 하나만 사용 |
| `title` | 아니오 | 없으면 문서 title 또는 파일명 사용 |
| `publisher` | 아니오 | 없으면 hostname 또는 Local file 사용 |
| `source_tier` | 아니오 | 기본 `UNVERIFIED_WEB`; 확인 후 명시 권장 |
| `published_at` | 아니오 | `YYYY-MM-DD`; 발행일·개정일을 혼동하지 말 것 |

## 인라인 형식

간단한 실행은 반복 `--source`를 사용할 수 있다.

```bash
--source law-regulation=https://example.go.kr/law \
--source privacy=./privacy-guide.pdf
```

인라인 형식은 title·publisher·tier·published date를 표현할 수 없으므로 검증 가능한 조사에는 JSONL을 우선한다.
