# Research Profile

프로필은 질문을 조사 track으로 나누고 출처·검색·근거선택 원칙을 정의한다. 프로젝트의
`.psr/profiles/<profile-id>.json`에 저장하며 초기화 시 `government.json`을 생성한다.

## 기본 계약

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

`tracks`는 활성화 가능한 base track의 전체 catalog다. 각 track에는 다음 필드를 둔다.

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

## Track 활성화

내장 `government` 프로필은 모든 질문에 무관한 track을 만들지 않도록 다음 필드를 사용한다.

```json
{
  "required_track_ids": ["law-regulation", "government-policy"],
  "optional_track_rules": [
    {"track_id": "privacy", "keywords": ["개인정보", "처리위탁", "보유기간"]}
  ],
  "broad_scope_keywords": ["종합", "전반", "정책 수립"],
  "excluded_track_ids": []
}
```

- `required_track_ids`: 좁은 질문에도 항상 포함한다.
- `optional_track_rules`: 질문에 keyword가 있을 때 catalog의 track을 활성화한다.
- `broad_scope_keywords`: 하나라도 일치하면 모든 optional base track을 활성화한다.
- `excluded_track_ids`: 해당 프로필에서 항상 제외한다.
- `conditional_tracks`: keyword가 있을 때 catalog 밖의 전문 track을 추가한다.

활성화 필드가 없는 기존 프로필은 호환성을 위해 `tracks` 전체를 필수로 취급한다. 로드할 때
수정되지 않은 구형 내장 `government.json`만 새 활성화 규칙으로 갱신하고, 사용자가 편집한
프로필은 덮어쓰지 않는다.

## 계획별 강제 조정

프로필을 수정하지 않고 한 번의 plan에서 track을 조정할 수 있다.

```bash
psr research plan "공공 디지털서비스 접근성 의무를 조사한다" \
  --include-track privacy \
  --exclude-track government-policy
```

두 옵션은 반복할 수 있다. 알 수 없는 ID, 동시 포함·제외, 모든 track 제외는 입력 오류다.
선택된 track 목록은 run ID 계산에도 반영되므로 같은 질문이라도 범위가 다르면 별도 run이 된다.

## 확장 원칙

1. source tier를 우선순위로만 사용하고 진실 판정으로 표현하지 않는다.
2. query domain, evidence type, selection term을 구체적으로 작성한다.
3. completion criteria에 gap 공개 조건을 포함한다.
4. 기존 프로젝트에서 사용한 track ID를 변경하지 않는다.
5. required·optional·excluded 분류가 모든 base track을 빠짐없이 포함하도록 한다.
6. 프로필 변경은 이후 생성하는 plan에만 적용한다.
