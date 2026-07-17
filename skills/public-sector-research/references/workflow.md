# 실행 워크플로

## 목차

1. 프로젝트 초기화
2. 조사계획
3. 출처 탐색
4. 수집과 보고서
5. 부분 실패
6. 재사용과 갱신
7. 사람 검토

## 1. 프로젝트 초기화

조사 산출물을 둘 프로젝트 루트에서 실행한다.

```bash
python3 <skill-directory>/scripts/psr.py project init <project-path> --name "<project-name>"
```

생성물:

```text
<project>/.psr/
├─ project.json
├─ research.db
├─ profiles/
├─ runs/
├─ sources/
├─ reports/
└─ exports/
```

원문 파일은 `sources/`, 구조화 메타데이터와 Passage·Citation은 `research.db`에 저장한다.

## 2. 조사계획

```bash
python3 <skill-directory>/scripts/psr.py --project <project> research plan \
  "<question>" --as-of YYYY-MM-DD --jurisdiction KR --profile government
```

계획은 다음을 포함한다.

- 조사 track과 질문
- 필요한 근거 유형
- 우선 domain
- 추천 검색어
- 완료 기준
- 최대 출처·bytes·시간

같은 질문·기준일·프로필은 같은 `run_id`를 생성해 불필요한 중복 계획을 줄인다.

## 3. 출처 탐색

호스트의 검색 도구를 사용한다. 검색 capability가 없으면 사용자가 제공한 URL, 로컬 파일, 기존 Memory만 사용한다.

우선순위:

1. 법령·정부·공공기관·국제기구·표준기관 원문
2. 기관이 배포한 공식 PDF·공식 보도자료
3. 학술 원문과 기업 공식자료
4. 신뢰 가능한 언론
5. 발견용 커뮤니티·블로그

각 출처는 [source-manifest.md](source-manifest.md) 형식으로 기록한다.

## 4. 수집과 보고서

```bash
python3 <skill-directory>/scripts/psr.py --project <project> research run <run-id> \
  --sources-file sources.jsonl
```

처리:

1. 최근 snapshot 재사용 여부 확인
2. 외부 URL 안전성·robots 정책 확인
3. 최대 4개 출처 병렬 수집
4. HTML·JSON·PDF·TEXT Passage 추출
5. URL·문서 hash·Passage text 중복 제거
6. Evidence Score 구성요소 계산
7. SQLite와 원문 파일 저장
8. `result.json`, `brief.json`, `report.md`, `report.html` 생성

기본 보고서는 원문 구간을 사용한 보수적 초안이다. 최종 한국어 보고서는
[reporting.md](reporting.md)에 따라 `brief.json`을 작성하고 다시 생성한다.

## 5. 부분 실패

일부 출처가 실패해도 성공한 원문과 citation은 보존한다.

- `status=PARTIAL`: gap 또는 실패가 존재한다.
- `failures[].retryable=true`: 네트워크·일시 오류 등 재시도 후보다.
- `PDF_DEPENDENCY_MISSING`: `pypdf`가 없는 환경이다.
- `OCR_REQUIRED`: 이미지 기반 PDF로 별도 OCR 검토가 필요하다.
- `ROBOTS_DISALLOWED`: 자동 수집하지 말고 사람이 원문 접근방법을 검토한다.

전체 결과를 폐기하거나 성공으로 과장하지 않는다.

## 6. 재사용과 갱신

기본값은 7일 이내 동일 URL snapshot 재사용이다.

```bash
python3 <skill-directory>/scripts/psr.py --project <project> research run <run-id> \
  --sources-file sources.jsonl --refresh
```

`--refresh`는 새 원문을 수집한다. 동일 hash이면 기존 Document·Snapshot ID를 재사용한다. 이 버전은 의미 기반 Diff와 영향분석을 제공하지 않는다.

## 7. 사람 검토

보고서에서 다음을 우선 확인한다.

- 공식 1차자료 비율
- 발행일 미확인
- 질문과 Passage의 직접 관련성
- 적용대상·관할·시행일
- `PARTIAL` 원인
- 독립성 점수의 한계
- 상충 공식자료 누락 가능성

검토하지 않은 자동 결과를 기관의 최종 법률·감사·조달 판단으로 사용하지 않는다.
