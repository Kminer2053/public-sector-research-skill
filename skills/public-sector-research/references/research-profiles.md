# Research Profile

프로필은 프로젝트의 `.psr/profiles/<profile-id>.json`에 저장한다. 프로젝트 초기화 시 `government.json`을 생성한다.

필수 최상위 필드:

```json
{
  "schema_version": "1.0",
  "id": "government",
  "title": "Government and Public Sector",
  "jurisdictions": ["KR"],
  "completion_criteria": ["..."],
  "tracks": []
}
```

각 track:

```json
{
  "id": "law-regulation",
  "title": "법령·규정",
  "research_question": "현행 법령의 의무와 적용대상은 무엇인가?",
  "evidence_types": ["법령", "시행령"],
  "source_tiers": ["OFFICIAL_PRIMARY"],
  "preferred_domains": ["law.go.kr"],
  "selection_terms": ["시행일", "적용대상", "의무"]
}
```

`conditional_tracks`는 질문에 특정 keyword가 있을 때 추가 track을 활성화한다.

프로필 확장 시 다음을 지킨다.

1. source tier는 우선순위이지 진실 판정이 아니다.
2. query domain과 evidence type을 구체적으로 작성한다.
3. completion criteria에 gap 공개 조건을 포함한다.
4. track ID는 기존 프로젝트에서 변경하지 않는다.
5. 프로필 파일 변경은 이후 생성하는 plan에만 적용한다.
