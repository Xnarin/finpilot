# 테스트·검증 결과

기준일 2026-10-17. 재현 방법은 명령, 확인자는 항목별로 구분했다. 자동 테스트 통과는 고정 응답 기준이며 실제 연동 성공을 뜻하지 않는다.

## 1. 자동 테스트 (`python -m pytest`) — 138개 통과 (0.4초)

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

### 회사 후보 (`tests/test_candidates.py`, 2026-10-19 추가, 11개)

| 테스트 | 확인 내용 |
|---|---|
| `test_alias_comes_first_with_source` | 별칭(네이버·삼전)이 후보 1번이고 출처가 표시됨 |
| `test_alias_target_missing_from_list_is_not_suggested` | 별칭의 대상이 상장사 목록에 없으면 후보로 내지 않음 |
| `test_preferred_stock_maps_to_common_stock_company_with_note` | 삼성전자우·삼성전자2우B → 삼성전자, 우선주라는 출처 표시 |
| `test_english_name_candidates` | 영문명(Samsung Electronics, sk hynix) 후보, 해외 회사는 후보 없음 |
| `test_formatting_only_difference_is_still_accepted_directly` | 공백·대소문자 차이만 있으면 바로 확정 |
| `test_alias_is_never_auto_confirmed` | 별칭은 자동 확정하지 않고 후보로 되묻기 |
| `test_all_alias_keys_are_normalized_form` | 별칭 사전의 키 형식 |
| `test_ai_suggestions_are_verified_against_official_list` | AI가 제안한 이름 중 목록에 정확히 있는 것만 남김 |
| `test_ai_suggestion_failure_or_bad_output_is_harmless` | AI 호출 실패·형식 오류가 와도 조용히 넘어감 |
| `test_candidates_for_order_alias_then_ai_then_rest_with_sources` | 후보 순서: 별칭·우선주 → AI → 나머지, 출처 표시 |
| `test_run_adds_candidates_and_ai_step_but_never_picks_one` | 실행 기록에 AI 제안 단계가 남고 회사를 자동으로 고르지 않음 |

### 해외·비상장 안내 (`tests/test_candidates.py`, 2026-10-19 추가, 5개)

| 테스트 | 확인 내용 |
|---|---|
| `test_weak_candidates_exist_without_ai_classification` | AI 분류가 없으면 `애플`→`애니플러스`(약칭 추정)가 후보로 나오는 소음 원인을 재현 |
| `test_foreign_classification_drops_weak_candidates` | AI가 해외·비상장으로 분류하면 약한 후보를 버림 |
| `test_foreign_classification_keeps_strong_candidates` | 별칭·영문명 등 강한 후보는 AI가 해외라고 해도 유지 |
| `test_run_reports_unsupported_company_with_reason_and_no_buttons` | `COMPANY_NOT_SUPPORTED`와 이유 문구, 후보 버튼 없음, 기록에 AI 분류 |
| `test_run_keeps_not_found_with_candidates_when_ai_says_unclear` | AI가 모른다고 하면 기존 후보로 되묻기 |

### 도구 함수 (`tests/test_tools.py`, 2026-10-19 추가, 62개)
`tools.py`의 도구는 예외를 던지지 않고 `status`가 담긴 결과를 돌려준다. 오늘 날짜는 테스트에서 고정한다(2026-10-19, 2027-02-10, 2027-10-19).

| 도구 | 확인 내용 |
|---|---|
| `resolve_years` | 연도 목록·범위의 정렬·중복 제거(건너뛴 연도를 채우지 않음), 거꾸로 쓴 범위 정규화, 작년·재작년·최근 N년이 오늘 날짜에 따라 달라짐(1~3월에는 전전년까지), 올해·미래 연도는 `YEAR_NOT_PUBLISHED`와 가장 최근 공시 연도 안내, 범위 밖·11개 이상·잘못된 형식(None, 문자열 등) 11종은 오류로 반환 |
| `resolve_company` | 정확 일치·공백·대소문자 차이만 확정, **같은 이름 중 현재 상장된 한 곳만 확정**(둘 다 상장이면 종목코드와 함께 후보, 상태를 알 수 없으면 확정하지 않음), 별칭은 후보로만(자동 확정 없음), 해외 기업은 후보 없이 `unsupported`, 잘못된 이름 5종 |
| `get_financials` | 정상 결과에 접수번호·접수일·정정 여부 포함, **분기·반기·월 요청은 조회 없이 `UNSUPPORTED_PERIOD`**, 별도 기준이 조회에 전달됨, 잘못된 기준·연도 형식·범위·올해·확정되지 않은 회사 코드 검증 8종, 조회 오류가 구조화된 결과로 변환, 공시 목록 실패가 숫자 조회를 막지 않음, 1~3월 작년 보고서 부재 시 시기 안내 |
| `compute_ratio` | 영업이익률(영업손실 음수 포함)·매출 성장률, 분모 0 이하·연도 불일치·기준 불일치·입력 누락·잘못된 지표 오류 구조화 |

**테스트가 실제로 잡는지 확인(변이 점검):** 도구 코드를 일부러 망가뜨려 보았다. 분기 요청 가드 제거, 올해 가드 제거, 동명 회사 상장 확인 제거, 회사 코드 검증 제거, 최근 N년 기준일 제거 5가지가 모두 테스트 실패로 잡혔고 이후 원래대로 복구했다.

### 유명 별칭·초성 (`tests/test_famous.py`, 2026-10-19 추가, 28개)
| 확인 내용 |
|---|
| 삼전·하닉·닉스·하이닉스·현차·현대차·네이버·카뱅(공백이 섞여도)이 바로 확정됨 |
| 삼성·현대·엘지·포스코·SK·하이·카카오 같은 모호하거나 짧은 이름은 사전으로 확정되지 않음, 사전에 모호한 이름(삼성, 현대, 엘지, 포스코, 한화, 롯데, 두산, sk, lg)이 들어 있지 않음 |
| 사전 대상이 목록에 없거나 같은 이름이 둘이면 확정하지 않음 |
| 입력과 같은 이름의 실제 회사가 있으면 그 회사가 우선 |
| 정식명 초성은 목록에서 하나뿐일 때만 확정, 겹치는 회사가 있으면 확정하지 않음 |
| 모르는 초성은 `초성 일치` 후보로만 나옴, 영문 접두어를 뺀 한글 초성 계산(`SK하이닉스`→`ㅎㅇㄴㅅ`) |

정책 변경에 맞춰 기존 테스트 7개(별칭이 후보로만 나오는 가정)를 모호한 별칭(포스코) 기준으로 고쳤다.

## 2. 실제 OpenDART 조회 확인

| 확인 | 결과 | 확인자 |
|---|---|---|
| 삼성전자 2024 영업이익률·매출 성장률을 직접 손계산과 대조 (10.88%, 16.20%) | 일치 | Claude |
| SK하이닉스 성장률 102.02%, 현대자동차 7.73% (2024) 조회 성공 | 조회 성공 | Claude |
| 삼성전자·SK하이닉스·현대자동차 각 2022~2025 수치를 DART 사업보고서 원문(접수번호)과 대조 | 일치 | 사용자 |

원문 대조 방법: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=<접수번호>` → 연결 손익계산서의 당기 열, 백만원 단위 환산 후 비교.

## 2-1. 실제 OpenDART 회귀 테스트 (`python -m pytest tests_live`, 키 필요) — 30개 통과 (약 4초)

- 삼성전자·SK하이닉스·현대자동차 × 2022~2025, 12개 조합의 매출액·영업이익·접수번호가 저장된 값과 정확히 일치. 저장된 값은 사용자가 DART 원문과 대조해 일치를 확인한 수치다(`tests_live/test_verified_values.py`).
- 실제 데이터로 계산한 SK하이닉스 2023 영업이익률 −23.59%(영업손실), 삼성전자 2025 매출 성장률 10.88%가 손계산과 일치.
- 도구의 실제 호출(`tests_live/test_tools_live.py`, 9개): 삼성물산 동명 회사가 현재 법인(028260)으로 확정, 현대자동차 2022·기아 2024는 정정본(`is_amended` True, 접수일 확인), 삼성전자 2024는 정정 없음, 한화에어로스페이스 2025는 첨부정정이 뒤에 있어도 원본, 삼성전자 2024 별도 매출이 연결보다 작음, 분기 요청이 조회 없이 `unsupported`, 별칭→후보→확정→영업이익률 전체 흐름(NAVER 18.43%, 손계산 일치).
- 유명 별칭 사전의 모든 대상이 실제 목록에 정확히 한 곳 있고, 모든 별칭이 바로 확정되며, 초성 `ㅅㅅㅈㅈ`·`ㄴㅇㅂ`는 다른 회사와 겹쳐 확정되지 않음을 매번 검사한다. 삼전·닉스·하이닉스·네이버·ㅎㄷㅈㄷㅊ·ㅎㅇㄴㅅ가 실제 목록에서 올바른 종목코드로 바로 확정되고, 삼성·현대·엘지·포스코·롯데는 확정되지 않는다(한화·두산은 같은 이름의 상장사가 실제로 있어 정확 일치로 확정됨).
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

## 3-2. 후보 개선 후 화면 로직 시뮬레이션 (2026-10-19, Claude)

| 입력 | 후보 버튼 | 결과 |
|---|---|---|
| 네이버 2024년 영업이익률 | `NAVER · 별칭 사전` | 클릭 시 NAVER 2024 영업이익률 18.43% (매출 10.74조 원, 영업이익 1.98조 원) |
| 삼성전자우 2024년 실적 | `삼성전자 · 우선주 → 해당 회사 재무제표` | 후보 표시 확인 |
| 엘지이노텍 2024년 실적 | `LG이노텍 · AI 제안 (상장사 목록에서 확인됨)` | 후보 표시 확인 |

회사 후보 성능 평가는 [eval_results.md](../evaluation/eval_results.md)의 5차 항목을 본다. 브라우저에서 직접 눌러 보는 확인은 아직 하지 않았다.

## 3-1. 회사 후보 되묻기 (실제 상장사 목록 기준, Claude, 2026-10-17 개선 전 기록)

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

## 4-0. LangSmith 월 한도 초과 발견 (2026-10-19, Claude)

- 도구 테스트를 돌리다 `429 ... Monthly unique traces usage limit exceeded` 오류가 출력되었다. LangSmith 계정의 이번 달 trace 한도가 소진된 것이다(한도 크기와 요금제는 확인하지 못했다).
- 원인 후보: 단위 테스트와 실제 호출 테스트가 `.env`의 `LANGSMITH_TRACING=true`를 읽어 실행할 때마다 trace를 보냈다. 조치: `tests/conftest.py`, `tests_live/conftest.py`에서 테스트 중에는 전송을 끈다(`LANGSMITH_TRACING=false`). 평가 실행(`eval.run_eval` 등)과 화면 실행은 의도적으로 계속 전송한다.
- 영향: 한도가 풀릴 때까지 trace가 서버에 저장되지 않을 수 있다. SDK는 오류를 로그로만 남기고 앱은 계속 동작한다("추적 실패가 계산 결과를 손상시키지 않는다"는 원칙은 지켜짐). 이번 달 한도 소진 이후의 평가·실행 trace는 누락되었을 수 있다.

## 4-1. LangSmith trace 비밀값 점검 (2026-10-17, Claude)

- 두 프로젝트(`finpilot-dev`, `finpilot-eval`)의 최근 run 각 100개씩 총 200개의 입력·출력·extra·오류를 검사: DART·Gemini·LangSmith 키 값과 키 형태 패턴(`AIza…`, `lsv2_…`, `crtfc_key=`) **발견 0건**.
- 각 run이 보내는 입력: `ask`(text), `parse_question`(text), `run`(company, task, year), `fetch_financials`(company, year, basis). 점검 중 `parse_question`이 `_llm` 함수 객체도 보내는 것을 발견해 입력을 text만 보내도록 수정함(비밀값은 아님).
- 한계: 최근 200개만 검사했고 전체 이력은 아니다.

## 5. 확인하지 못했거나 남은 위험

- 질문 입력 화면에서 `rec["inputs"]` `NoneType` 오류가 한 번 보고되었으나 Claude는 재현하지 못했다. 사용자가 서버를 재시작한 뒤 정상 동작을 확인했다(확인자: 사용자). 원인은 확정하지 못했고, 실행 중이던 서버가 예전 모듈을 들고 있었을 가능성이 가장 크다.
- 금융업(은행·보험·증권)은 지원하지 않는다.
- 정정공시가 있을 때 어느 값을 쓸지는 정하지 않았다(현재는 연도별 보고서의 당기 금액만 사용).
