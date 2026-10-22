# 문서·결과 목차

기준일 2026-10-19. 문서를 목적별 폴더로 나눴다. 새 문서나 결과가 생기면 해당 파트의 표에 한 줄 추가한다.

```
docs/
├─ index.md                  이 목차
├─ 회고.md                   고민과 해결 기록
├─ reference.md              조회 기준·회사 선택·검증 기록 상세
├─ verification/             구현이 맞는지 확인한 기록
│   └─ test_results.md
├─ evaluation/               질문 해석 평가 (질문, 결과, 응답)
│   ├─ eval_results.md
│   ├─ eval_questions.md
│   ├─ eval_responses.md
│   └─ agent_hard_qa.md
└─ backlog/                  앞으로 할 일과 설계 메모
    ├─ agent_design.md        (에이전트 설계와 구현 현황)
    ├─ policies.md
    ├─ unresolved_cases.md
    └─ future_requirements.md
eval/                        평가 데이터·실행기·결과 파일 (코드 쪽)
tests/, tests_live/          자동 테스트
```

## 파트 1. 시작하기

| 문서 | 내용 | 읽을 때 |
|---|---|---|
| [reference.md](reference.md) | README에서 옮긴 상세: 조회 기준, 회사 선택 규칙, 질문 해석과 모니터링, 날짜별 검증 기록 표 | 세부 규칙·검증 이력이 필요할 때 |
| [../README.md](../README.md) | 설치·설정·실행·테스트 방법, 조회 기준, 검증 기록 요약 | 처음 볼 때 |
| [회고.md](회고.md) | 사용자가 던진 고민, 결정, 해결, 남은 문제, 배운 점을 시간순·주제별로 정리 | 지금까지의 흐름을 볼 때 |
| [../AGENT.md](../AGENT.md) | 개발 에이전트 지침과 단계별 로드맵 | 작업 원칙 확인 |
| [../finpilot_project_plan.md](../finpilot_project_plan.md), [../finance_study_notes.md](../finance_study_notes.md) | 원본 기획서, 금융 개념 학습 기록(수정하지 않음) | 배경 확인 |

## 파트 2. 검증 — 구현이 맞는가 (`docs/verification/`)

| 문서 | 내용 | 읽을 때 |
|---|---|---|
| [verification/test_results.md](verification/test_results.md) | 자동 테스트 220개 목록, 실제 OpenDART 회귀 테스트 13개, DART 원문 대조, 오류 상황 확인, LangSmith trace 비밀값 점검 | 조회·계산이 맞는지 확인할 때 |

관련 코드: [../tests/test_finance.py](../tests/test_finance.py), [../tests/test_candidates.py](../tests/test_candidates.py), [../tests/test_tools.py](../tests/test_tools.py), [../tests/test_famous.py](../tests/test_famous.py), [../tests/test_agent.py](../tests/test_agent.py)(오프라인, 에이전트는 가짜 LLM), [../tests/test_mcp_server.py](../tests/test_mcp_server.py)(MCP 서버), [../tests_live/test_verified_values.py](../tests_live/test_verified_values.py)(사용자가 원문과 대조한 12개 조합의 수치), [../tests_live/test_tools_live.py](../tests_live/test_tools_live.py)(도구의 실제 호출), [../tests_live/test_mcp_stdio.py](../tests_live/test_mcp_stdio.py)(MCP 서버를 별도 프로세스로 띄워 호출)

## 파트 3. 평가 — 질문 해석이 맞는가 (`docs/evaluation/`)

| 문서 | 내용 | 읽을 때 |
|---|---|---|
| [evaluation/eval_results.md](evaluation/eval_results.md) | 평가 1~4차 결과와 해석(프롬프트 수정 경위, 반복 실행, 실사용자형 질문, 위험 오답 발견) | 점수와 원인을 볼 때 |
| [evaluation/eval_questions.md](evaluation/eval_questions.md) | 질문 114개와 정답, 모델 결과. 정답 검토용 | 정답이 맞는지 검토할 때 |
| [evaluation/agent_hard_qa.md](evaluation/agent_hard_qa.md) | 에이전트에 어려운 질문 26개를 던진 질문·기대·답변·도구 호출·판정 전문(2회씩) | 에이전트가 실제로 어떻게 답하는지 볼 때 |
| [evaluation/eval_responses.md](evaluation/eval_responses.md) | 질문별 모델 해석(3회)과 파이프라인이 실제로 낸 응답 | 시스템이 어떻게 답했는지 볼 때 |

### 질문·정답 데이터 (`eval/`)

| 파일 | 내용 |
|---|---|
| [../eval/questions.json](../eval/questions.json) | 질문 114개와 정답 원본. 묶음(split): `dev` 14, `final` 11, `dev_hard` 10, `final_hard` 10, `real` 69 |
| [../eval/agent_cases.json](../eval/agent_cases.json) | 에이전트 평가 dev 묶음: 42개 케이스·47턴(고치면서 쓴 묶음) |
| [../eval/agent_cases_hard.json](../eval/agent_cases_hard.json) | 에이전트 어려운 질문 26개 케이스·30턴(비교·의견·정정·한계·여러 턴 등, 일부 정답은 "또는" 허용) |
| [../eval/agent_cases_heldout.json](../eval/agent_cases_heldout.json) | 에이전트 평가 held-out 묶음: 25개 케이스·28턴(결과를 본 뒤 에이전트를 고쳤으므로 소진됨) |
| [../eval/alias_cases.json](../eval/alias_cases.json) | 회사명 입력 91개와 정식명 정답(회사 후보 평가용, 그룹: dict·not_in_dict_kr·english·preferred·typo·none·foreign·unlisted) |

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

| [20261019-093314-alias-x3.json](../eval/results/20261019-093314-alias-x3.json) | 10-19 09:33 | alias 57(회사명 입력) | 3 | 해당 없음(회사 후보 단계) | AI 포함 hit@1 141/147(정답이 있는 49개 입력×3회) | **회사 후보 기준선**: 코드 후보만 vs AI 제안 포함, `python -m eval.run_alias_eval` |
| [20261019-102053-alias-x3.json](../eval/results/20261019-102053-alias-x3.json) | 10-19 10:20 | alias 75(해외·비상장 18 추가) | 3 | 해당 없음 | 사전 외 한글 별칭 38/48 | 분류 추가 직후, 제안 프롬프트 1안(후보 이름이 나빠짐) |
| [20261019-102436-alias-x3.json](../eval/results/20261019-102436-alias-x3.json) | 10-19 10:24 | alias 75 | 3 | 해당 없음 | 사전 외 한글 별칭 46/48, 해외 42/42 | 제안 프롬프트 2안, 해외·비상장 안내 |
| [20261019-113942-alias-x3.json](../eval/results/20261019-113942-alias-x3.json) | 10-19 11:39 | alias 91(모호한 그룹명·초성 16 추가) | 3 | 해당 없음 | 바로 확정 20개 중 오확정 0 | **현재 회사 후보**: 유명 별칭·초성 즉시 확정 점검 |

| [20261019-142630-agent-x1.json](../eval/results/20261019-142630-agent-x1.json) | 10-19 14:26 | agent dev 42 | 1 | 에이전트 | 37/42 | 에이전트 첫 시험 |
| [20261019-143427-agent-x3.json](../eval/results/20261019-143427-agent-x3.json) | 10-19 14:34 | agent dev 42 | 3 | 에이전트 1차 | 120/126 | 첫 구현(근거 인용이 약함) |
| [20261019-144342-agent-x3.json](../eval/results/20261019-144342-agent-x3.json) | 10-19 14:43 | agent dev 42 | 3 | 에이전트 2차 | 123/126 | 인용·지표 검사 강화 |
| [20261019-145038-agent-x3.json](../eval/results/20261019-145038-agent-x3.json) | 10-19 14:50 | agent dev 42 | 3 | 에이전트 3차 | 126/126 | 후보 자동 되묻기 |
| [20261019-160723-agentqa-x2.json](../eval/results/20261019-160723-agentqa-x2.json) | 10-19 16:07 | agent hard 26 | 2 | 에이전트(이어받기 수정 후) | 49/52, 정답에 없는 행 0 | 어려운 질문 Q&A, `agent_hard_qa.md`의 원본 |
| [20261019-145646-agent-x3.json](../eval/results/20261019-145646-agent-x3.json) | 10-19 14:56 | agent held-out 25 | 3 | 에이전트 3차 | 65/75 (평가셋 오류 정정 시 71/75) | **에이전트 일반화 점수**, 정답에 없는 행 0 |
| [20261021-173851-agent-gemini-3.5-flash-lite-full-x3.json](../eval/results/20261021-173851-agent-gemini-3.5-flash-lite-full-x3.json) | 10-21 17:38 | agent held-out 25(소진) | 3 | 3.5-flash-lite · 전체 프롬프트 | 75/75, 정답에 없는 행 0 | **모델 비교 기준**(현재 설정), eval_results 10차 |
| [20261021-174305-agent-gemini-3.5-flash-lite-core-x3.json](../eval/results/20261021-174305-agent-gemini-3.5-flash-lite-core-x3.json) | 10-21 17:43 | agent held-out 25(소진) | 3 | 3.5-flash-lite · 규칙 1~5만 | 71/75, 정답에 없는 행 0 | 프롬프트 축소 비교, eval_results 10차 |
| [20261022-092110-agent-gemini-3.5-flash-full-x3.json](../eval/results/20261022-092110-agent-gemini-3.5-flash-full-x3.json) | 10-22 09:21 | agent held-out 25(소진) | 3 | 3.5-flash · 전체 | 72/75, 정답에 없는 행 0 | 모델 비교, eval_results 10차 |
| [20261022-092555-agent-gemini-3.1-flash-lite-full-x3.json](../eval/results/20261022-092555-agent-gemini-3.1-flash-lite-full-x3.json) | 10-22 09:25 | agent held-out 25(소진) | 3 | 3.1-flash-lite · 전체 | 75/75, 정답에 없는 행 0 | 모델 비교(비용 약 18% 낮음), eval_results 10차 |
| [20261022-093425-agent-gemini-2.5-flash-full-x3.json](../eval/results/20261022-093425-agent-gemini-2.5-flash-full-x3.json) | 10-22 09:34 | agent held-out 25(소진) | 3 | 2.5-flash · 전체 | 72/75, 정답에 없는 행 0 | 모델 비교, eval_results 10차 |

- 비교 기준으로는 `x3` 결과들을 쓴다(질문 해석 두 개, 회사 후보 한 개, 에이전트 held-out 한 개). 에이전트 dev는 고치면서 쓴 묶음이라 일반화 점수가 아니다. 앞의 11개는 반복 1회라 같은 질문의 비일관성을 알 수 없고 형식도 이전 방식이다.

## 파트 4. 백로그와 설계 — 앞으로 무엇을 할까 (`docs/backlog/`)

| 문서 | 내용 | 읽을 때 |
|---|---|---|
| [backlog/unresolved_cases.md](backlog/unresolved_cases.md) | 현재 시스템이 답하지 못한 64문항을 원인별 6유형(A~F)으로 묶고 해결 후보(도구·에이전트)를 적음 | 다음에 무엇을 고칠지 정할 때 |
| [backlog/agent_design.md](backlog/agent_design.md) | 에이전트(LangGraph, 챗봇형) 설계: 사용자 결정 13개, 구조·상태·안전 규칙·화면·평가, 공식 문서·스파이크 확인 결과와 설계 수정안 | 에이전트를 만들 때 |
| [backlog/policies.md](backlog/policies.md) | MVP 정책 결정(상대 연도, 되묻기, 별도·분기, 정정본)과 구현 위치, 정정공시·동명 회사 확인 결과 | 정책을 확인할 때 |
| [backlog/future_requirements.md](backlog/future_requirements.md) | 복수 연도·회사 등 앞으로의 요구, 예외 상황 카탈로그, 에이전트 구조 메모, 정책 결정 항목 | 에이전트를 설계할 때 |

기계가 읽는 원본: [../eval/unresolved_cases.json](../eval/unresolved_cases.json)(64문항의 유형·원하는 동작·해결 후보). 나중에 golden set의 출발점으로 쓴다.

## 파트 5. 실행 명령 (참고)

| 목적 | 명령 | 결과가 저장되는 곳 |
|---|---|---|
| 오프라인 단위 테스트 | `python -m pytest` | 화면 출력 |
| 실제 OpenDART 회귀 테스트(키 필요) | `python -m pytest tests_live` | 화면 출력 |
| 질문 해석 평가(Gemini 호출) | `python -m eval.run_eval <묶음> [반복횟수]` | `eval/results/` |
| 에이전트 평가(Gemini·OpenDART 호출) | `python -m eval.run_agent_eval [반복] [--baseline] [--cases=agent_cases_heldout.json] [--model=…] [--prompt=core]` | `eval/results/` |
| 어려운 질문 Q&A 기록 | `python -m eval.run_agent_qa [--cases=…] [--repeats=2]` | `docs/evaluation/agent_hard_qa.md`, `eval/results/` |
| MCP 서버 실행 | `python mcp_server.py` (stdio) | — |
| 챗봇 화면 실행 | `streamlit run chat_app.py` | 화면 |
| 회사명 후보 평가(Gemini 호출) | `python -m eval.run_alias_eval [반복횟수]` | `eval/results/` |
| 질문별 응답 문서 생성(OpenDART 호출) | `python -m eval.export_responses <결과.json>…` | `docs/evaluation/eval_responses.md` |
