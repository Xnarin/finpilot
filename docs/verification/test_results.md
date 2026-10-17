# 테스트·검증 결과

기준일 2026-10-17. 재현 방법은 명령, 확인자는 항목별로 구분했다. 자동 테스트 통과는 고정 응답 기준이며 실제 연동 성공을 뜻하지 않는다.

## 1. 자동 테스트 (`python -m pytest`) — 32개 통과 (0.3초)

네트워크·API 키 없이 실행. OpenDART 응답과 LLM 호출은 고정값·가짜 함수로 대체했다. 기대값은 테스트 안에 직접 적은 상수다.

| 영역 | 테스트 | 확인 내용 |
|---|---|---|
| 영업이익률 | `test_margin_normal` | 1000·150 → 15% |
| | `test_margin_negative_on_loss` | 영업손실 → 음수 −25% (정상 결과) |
| | `test_margin_bad_denominator` (0, −1000) | 매출 0 이하 → `INVALID_DENOMINATOR` |
| 매출 성장률 | `test_growth_normal` / `_decline` | +25%, −20% |
| | `test_growth_bad_denominator` (0, −5) | 전기 매출 0 이하 → `INVALID_DENOMINATOR` |
| | `test_growth_year_mismatch` | 직전 연도가 아니면 `PERIOD_MISMATCH` |
| | `test_growth_basis_mismatch` | 연결/별도 불일치 → `BASIS_MISMATCH` |
| 회사 찾기 | `test_find_company_exact` | 공백 제거 후 정확히 일치하는 한 곳 |
| | `test_find_company_ambiguous_and_not_found` | 동명 2곳 → `COMPANY_AMBIGUOUS`, 부분 일치는 선택하지 않고 후보만 안내 |
| OpenDART 응답 파싱 | `test_fetch_parses_amounts_and_source` | 쉼표 제거 정수 변환, 접수번호, 단위 원, 연결 |
| | `test_fetch_requests_cfs_for_consolidated` | corp_code, 연결(CFS), 사업보고서(11011) 요청 |
| | `test_fetch_no_data_status` | 상태 013 → `DATA_MISSING` |
| | `test_fetch_other_status_is_api_error` | 그 밖의 상태 → `API_ERROR` |
| | `test_fetch_bad_rows` ×6 | 영업이익 없음·매출 후보 2건 → `ACCOUNT_NOT_UNIQUE`, 빈 문자열·잘못된 숫자 → `PARSE_ERROR`(0으로 바꾸지 않음), 통화 USD → `UNIT_MISMATCH`, 접수번호 불일치 → `SOURCE_MISMATCH` |
| 실행 흐름 | `test_run_missing_prior_year` | 전기 누락 시 단계 [성공, 실패], 결과 없음 |
| | `test_run_growth_and_margin_with_fixed_data` | 25%, 20% 계산 |
| 회사 후보 | `test_candidates_abbreviation_substring_and_typo` | 약칭(`삼전`→삼성전자·삼성전기), 부분 일치(`하이닉스`→SK하이닉스), 오타 후보 |
| | `test_formatting_only_difference_is_accepted_but_abbreviation_is_not` | `sk 하이닉스`·`naver`는 공백·대소문자 차이만이라 확정, `삼전`은 확정하지 않고 후보를 알려 되묻기 |
| | `test_pick_company_reruns_with_chosen_name_and_records_choice` | 후보를 고르면 같은 연도·작업으로 재실행하고 선택 기록을 남김 |
| 질문 해석 | `test_ask_incomplete_question_stops_without_guessing` ×3 | 기업·연도·작업 중 하나라도 비면 `QUESTION_INCOMPLETE`로 중단 |
| | `test_ask_llm_failure_is_reported` | LLM 오류가 오류 코드로 표시 |
| | `test_parse_question_rejects_bad_llm_output` | 허용되지 않은 작업값 → `LLM_BAD_OUTPUT`, 정상 JSON은 통과 |

## 2. 실제 OpenDART 조회 확인

| 확인 | 결과 | 확인자 |
|---|---|---|
| 삼성전자 2024 영업이익률·매출 성장률을 직접 손계산과 대조 (10.88%, 16.20%) | 일치 | Claude |
| SK하이닉스 성장률 102.02%, 현대자동차 7.73% (2024) 조회 성공 | 조회 성공 | Claude |
| 삼성전자·SK하이닉스·현대자동차 각 2022~2025 수치를 DART 사업보고서 원문(접수번호)과 대조 | 일치 | 사용자 |

원문 대조 방법: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=<접수번호>` → 연결 손익계산서의 당기 열, 백만원 단위 환산 후 비교.

## 2-1. 실제 OpenDART 회귀 테스트 (`python -m pytest tests_live`, 키 필요) — 13개 통과 (2.4초)

- 삼성전자·SK하이닉스·현대자동차 × 2022~2025, 12개 조합의 매출액·영업이익·접수번호가 저장된 값과 정확히 일치. 저장된 값은 사용자가 DART 원문과 대조해 일치를 확인한 수치다(`tests_live/test_verified_values.py`).
- 실제 데이터로 계산한 SK하이닉스 2023 영업이익률 −23.59%(영업손실), 삼성전자 2025 매출 성장률 10.88%가 손계산과 일치.
- 일반 `pytest`에는 포함되지 않는다(`pytest.ini`의 `testpaths = tests`).
- **관찰:** 현대자동차 2022 보고서의 접수번호가 `20240314001531`로, 접수일이 2023년이 아니라 2024년 3월이다. 정정된 사업보고서가 조회되고 있을 가능성이 있다(미확인). 정정공시 선택 기준은 아직 정하지 않았다.

## 3. 오류 상황 확인

| 상황 | 기대 결과 | 확인 방법 · 확인자 |
|---|---|---|
| 없는 회사 / 부분 이름(`삼성`) | `COMPANY_NOT_FOUND` (+ 비슷한 이름 목록) | 코드 실행 Claude, 화면 사용자 |
| 금융업(KB금융) | `ACCOUNT_NOT_UNIQUE` | 코드 실행 Claude, 화면 사용자 |
| 보고서 없는 연도(2030) | `DATA_MISSING` | 코드 실행 Claude, 화면 사용자 |
| 틀린 DART 키 | `API_ERROR`, 키 미노출 | 화면 사용자 |
| 연도 없는 질문(`삼성전자 영업이익률`) | `QUESTION_INCOMPLETE` | 화면 로직 시뮬레이션 Claude |
| 지원 밖 질문(`주가 예측`) | `QUESTION_INCOMPLETE`(작업) | 화면 로직 시뮬레이션 Claude |
| 약칭(`삼전`) | `COMPANY_NOT_FOUND` + 후보 버튼, `삼성전자(으)로 조회` 클릭 시 정상 조회(영업이익률 10.88%) | 화면 로직 시뮬레이션 Claude |

## 3-1. 회사 후보 되묻기 (실제 상장사 목록 기준, Claude)

| 입력 | 후보 |
|---|---|
| 삼전 | 삼성전기, 삼화전기, 삼지전자, 삼성전자, 삼화전자공업 (삼성전자가 4번째, 순위 신호가 없어 노이즈가 섞임) |
| 하이닉스 | SK하이닉스 |
| 현대차 | 현대차증권, 현대자동차 |
| 현대자동자(오타) | 현대자동차 |
| 네이버 | 후보 없음(영문 표기 NAVER와 철자가 달라 찾지 못함) |

## 4. 모니터링 확인

- LangSmith trace가 `finpilot-dev`, `finpilot-eval` 프로젝트에 도착함을 API 조회로 확인(`ask`, `parse_question`, `run`, `fetch_financials`).
- 전송 실패 여부는 SDK가 백그라운드로 처리해 화면에서 확인하지 못한다. 화면은 tracing 켜짐/꺼짐만 표시한다.

## 4-1. LangSmith trace 비밀값 점검 (2026-10-17, Claude)

- 두 프로젝트(`finpilot-dev`, `finpilot-eval`)의 최근 run 각 100개씩 총 200개의 입력·출력·extra·오류를 검사: DART·Gemini·LangSmith 키 값과 키 형태 패턴(`AIza…`, `lsv2_…`, `crtfc_key=`) **발견 0건**.
- 각 run이 보내는 입력: `ask`(text), `parse_question`(text), `run`(company, task, year), `fetch_financials`(company, year, basis). 점검 중 `parse_question`이 `_llm` 함수 객체도 보내는 것을 발견해 입력을 text만 보내도록 수정함(비밀값은 아님).
- 한계: 최근 200개만 검사했고 전체 이력은 아니다.

## 5. 확인하지 못했거나 남은 위험

- 질문 입력 화면에서 `rec["inputs"]` `NoneType` 오류가 한 번 보고되었으나 Claude는 재현하지 못했다. 사용자가 서버를 재시작한 뒤 정상 동작을 확인했다(확인자: 사용자). 원인은 확정하지 못했고, 실행 중이던 서버가 예전 모듈을 들고 있었을 가능성이 가장 크다.
- 금융업(은행·보험·증권)은 지원하지 않는다.
- 정정공시가 있을 때 어느 값을 쓸지는 정하지 않았다(현재는 연도별 보고서의 당기 금액만 사용).
