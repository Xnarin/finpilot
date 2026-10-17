# 문서·결과 목차

기준일 2026-10-18. 문서를 목적별 폴더로 나눴다. 새 문서나 결과가 생기면 해당 파트의 표에 한 줄 추가한다.

```
docs/
├─ index.md                  이 목차
├─ verification/             구현이 맞는지 확인한 기록
│   └─ test_results.md
├─ evaluation/               질문 해석 평가 (질문, 결과, 응답)
│   ├─ eval_results.md
│   ├─ eval_questions.md
│   └─ eval_responses.md
└─ backlog/                  앞으로 할 일과 설계 메모
    ├─ unresolved_cases.md
    └─ future_requirements.md
eval/                        평가 데이터·실행기·결과 파일 (코드 쪽)
tests/, tests_live/          자동 테스트
```

## 파트 1. 시작하기

| 문서 | 내용 | 읽을 때 |
|---|---|---|
| [../README.md](../README.md) | 설치·설정·실행·테스트 방법, 조회 기준, 검증 기록 요약 | 처음 볼 때 |
| [../AGENT.md](../AGENT.md) | 개발 에이전트 지침과 단계별 로드맵 | 작업 원칙 확인 |
| [../finpilot_project_plan.md](../finpilot_project_plan.md), [../finance_study_notes.md](../finance_study_notes.md) | 원본 기획서, 금융 개념 학습 기록(수정하지 않음) | 배경 확인 |

## 파트 2. 검증 — 구현이 맞는가 (`docs/verification/`)

| 문서 | 내용 | 읽을 때 |
|---|---|---|
| [verification/test_results.md](verification/test_results.md) | 자동 테스트 32개 목록, 실제 OpenDART 회귀 테스트 13개, DART 원문 대조, 오류 상황 확인, LangSmith trace 비밀값 점검 | 조회·계산이 맞는지 확인할 때 |

관련 코드: [../tests/test_finance.py](../tests/test_finance.py)(오프라인), [../tests_live/test_verified_values.py](../tests_live/test_verified_values.py)(사용자가 원문과 대조한 12개 조합의 수치)

## 파트 3. 평가 — 질문 해석이 맞는가 (`docs/evaluation/`)

| 문서 | 내용 | 읽을 때 |
|---|---|---|
| [evaluation/eval_results.md](evaluation/eval_results.md) | 평가 1~4차 결과와 해석(프롬프트 수정 경위, 반복 실행, 실사용자형 질문, 위험 오답 발견) | 점수와 원인을 볼 때 |
| [evaluation/eval_questions.md](evaluation/eval_questions.md) | 질문 114개와 정답, 모델 결과. 정답 검토용 | 정답이 맞는지 검토할 때 |
| [evaluation/eval_responses.md](evaluation/eval_responses.md) | 질문별 모델 해석(3회)과 파이프라인이 실제로 낸 응답 | 시스템이 어떻게 답했는지 볼 때 |

### 질문·정답 데이터 (`eval/`)

| 파일 | 내용 |
|---|---|
| [../eval/questions.json](../eval/questions.json) | 질문 114개와 정답 원본. 묶음(split): `dev` 14, `final` 11, `dev_hard` 10, `final_hard` 10, `real` 69 |

묶음별 용도: `dev`, `dev_hard`는 프롬프트 개선에 쓴 묶음이다. `final`, `final_hard`, `real`은 최종 확인용이며 **이미 한 번 이상 사용됐다**. 구조나 프롬프트를 바꾼 뒤의 확인에는 새 묶음이 필요하다.

### 평가 결과 파일 (`eval/results/`)

프롬프트 해시: **v1** `714d672a2f38`(처음) → **v2** `fb05c08f8805` → **v3** `00c51b4db211` → **v4** `a7fa13a808a2`(현재). 모델은 모두 `gemini-3.5-flash-lite`, temperature 0이다.

| 결과 파일 | 시각 | 묶음 | 반복 | 프롬프트 | 결과 | 어떤 결과인가 |
|---|---|---|---|---|---|---|
| [20261017-191535-dev.json](../eval/results/20261017-191535-dev.json) | 19:15 | dev 14 | 1 | v1 | 14/14 | 1차 평가, 첫 프롬프트 |
| [20261017-191558-final.json](../eval/results/20261017-191558-final.json) | 19:15 | final 11 | 1 | v1 | 11/11 | 1차 평가, 첫 프롬프트 |
| [20261017-222718-dev_hard.json](../eval/results/20261017-222718-dev_hard.json) | 22:27 | dev_hard 10 | 1 | v1 | 9/10 | 2차 평가 시작점(어려운 질문 추가 직후) |
| [20261017-222744-dev.json](../eval/results/20261017-222744-dev.json) | 22:27 | dev 14 | 1 | v2 | 13/14 | 프롬프트 수정 1회차 후, d11 회귀 |
| [20261017-222758-dev_hard.json](../eval/results/20261017-222758-dev_hard.json) | 22:27 | dev_hard 10 | 1 | v2 | 8/10 | 프롬프트 수정 1회차 후 |
| [20261017-222823-dev.json](../eval/results/20261017-222823-dev.json) | 22:28 | dev 14 | 1 | v3 | 13/14 | 프롬프트 수정 2회차 후 |
| [20261017-222837-dev_hard.json](../eval/results/20261017-222837-dev_hard.json) | 22:28 | dev_hard 10 | 1 | v3 | 9/10 | 프롬프트 수정 2회차 후 |
| [20261017-222902-dev.json](../eval/results/20261017-222902-dev.json) | 22:29 | dev 14 | 1 | v4 | 13/14 | 프롬프트 수정 3회차 후(현재 프롬프트) |
| [20261017-222914-dev_hard.json](../eval/results/20261017-222914-dev_hard.json) | 22:29 | dev_hard 10 | 1 | v4 | 10/10 | 현재 프롬프트 |
| [20261017-222934-final.json](../eval/results/20261017-222934-final.json) | 22:29 | final 11 | 1 | v4 | 11/11 | 현재 프롬프트로 final 재확인 |
| [20261017-222946-final_hard.json](../eval/results/20261017-222946-final_hard.json) | 22:29 | final_hard 10 | 1 | v4 | 7/10 | 어려운 최종용 질문, 최초 실행 |
| [20261017-234045-all-x3.json](../eval/results/20261017-234045-all-x3.json) | 23:40 | 위 4개 묶음 45 | 3 | v4 | 호출 단위 93.3% | **기준선 1**: 반복 실행·토큰 포함 |
| [20261017-235007-real-x3.json](../eval/results/20261017-235007-real-x3.json) | 23:50 | real 69(점수 대상 65) | 3 | v4 | 호출 단위 84.6% | **기준선 2**: 실사용자형 질문, 미튜닝 |

- 비교 기준으로는 마지막 두 개(`x3`)를 쓴다. 앞의 11개는 반복 1회라 같은 질문의 비일관성을 알 수 없고 형식도 이전 방식이다.

## 파트 4. 백로그와 설계 — 앞으로 무엇을 할까 (`docs/backlog/`)

| 문서 | 내용 | 읽을 때 |
|---|---|---|
| [backlog/unresolved_cases.md](backlog/unresolved_cases.md) | 현재 시스템이 답하지 못한 64문항을 원인별 6유형(A~F)으로 묶고 해결 후보(도구·에이전트)를 적음 | 다음에 무엇을 고칠지 정할 때 |
| [backlog/future_requirements.md](backlog/future_requirements.md) | 복수 연도·회사 등 앞으로의 요구, 예외 상황 카탈로그, 에이전트 구조 메모, 정책 결정 항목 | 에이전트를 설계할 때 |

기계가 읽는 원본: [../eval/unresolved_cases.json](../eval/unresolved_cases.json)(64문항의 유형·원하는 동작·해결 후보). 나중에 golden set의 출발점으로 쓴다.

## 파트 5. 실행 명령 (참고)

| 목적 | 명령 | 결과가 저장되는 곳 |
|---|---|---|
| 오프라인 단위 테스트 | `python -m pytest` | 화면 출력 |
| 실제 OpenDART 회귀 테스트(키 필요) | `python -m pytest tests_live` | 화면 출력 |
| 질문 해석 평가(Gemini 호출) | `python -m eval.run_eval <묶음> [반복횟수]` | `eval/results/` |
| 질문별 응답 문서 생성(OpenDART 호출) | `python -m eval.export_responses <결과.json>…` | `docs/evaluation/eval_responses.md` |
