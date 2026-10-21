# 에이전트 어려운 질문 Q&A (2026-10-19)

답변하기 어려울 것으로 예상한 질문 26개를 실제 Gemini(`gemini-3.5-flash-lite`)와 OpenDART로 각각 2회 물어본 기록이다. 오늘 날짜는 2026-10-19로 고정했다. 질문 원본은 `eval/agent_cases_hard.json`, 실행기는 `python -m eval.run_agent_qa`, 원본 결과는 `eval/results/`의 `*-agentqa-*.json`이다.

답변은 챗봇 화면에 나오는 내용(표·안내·되묻기·거절·설명 문장)을 글로 옮긴 것이다. 표의 숫자·되묻기·거절 문구는 코드가 만들고, 설명 문장은 숫자가 있으면 버려진다. 판정의 정답은 Claude가 작성했고 사람 검토 전이다. 정답 중 '또는'은 여러 답이 모두 허용된다는 뜻이다(예: 의견을 묻는 질문은 숫자 표만 보여 주거나 거절하면 둘 다 정답).

**요약:** 질문×2회 52번 중 정답 49번, **정답에 없는 표 행(틀린 값을 정상처럼 표시) 0건**.

## q01 · 비교 질문 — 정답 2/2

**질문:** 삼성전자 매출이 SK하이닉스보다 얼마나 더 커?

**기대:** 표 없음, 되묻기: year 또는 표 없음, 거절

**답변** (같은 답 2/2회) ✅ 정답

- (되묻기) 다음을 알려 주세요: 어느 사업연도인지.

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_company(name=SK하이닉스)→ok
  - ask_user(missing=['year'])→ok

  </details>


## q02 · 비교 질문 — 정답 2/2

**질문:** 삼성전자랑 SK하이닉스 중에 2024년 영업이익률 높은 곳은?

**기대:** 표: 삼성전자 2024 영업이익률, SK하이닉스 2024 영업이익률 또는 표 없음, 거절

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원, 영업이익률 10.88% (접수번호 20250311001085)
- **SK하이닉스 2024사업연도 연결**: 매출액 66.19조 원, 영업이익 23.47조 원, 영업이익률 35.45% (접수번호 20250319000665)
- (설명 문장) 두 회사의 영업이익률을 비교한 결과입니다.

  <details><summary>도구 호출 5회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_company(name=SK하이닉스)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2024, basis=연결)→ok
  - compute_ratio(metric=operating_margin, corp_code=00164779, year=2024, basis=연결)→ok

  </details>


## q03 · 복수 연도 표현 — 정답 2/2

**질문:** 삼성전자 영업이익이 2023엔 얼마였고 2024엔 얼마야?

**기대:** 표: 삼성전자 2023, 삼성전자 2024

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2023사업연도 연결**: 매출액 258.94조 원, 영업이익 6.57조 원 (접수번호 20240312000736)
- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원 (접수번호 20250311001085)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 5회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=explicit, values=[2023])→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - get_financials(corp_code=00126380, year=2023, basis=연결, period=연간)→ok
  - get_financials(corp_code=00126380, year=2024, basis=연결, period=연간)→ok

  </details>


## q04 · 복수 연도 표현 — 정답 2/2

**질문:** 삼성전자 작년이랑 재작년 영업이익률

**기대:** 표: 삼성전자 2025 영업이익률, 삼성전자 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2025사업연도 연결**: 매출액 333.61조 원, 영업이익 43.60조 원, 영업이익률 13.07% (접수번호 20260310002820)
- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원, 영업이익률 10.88% (접수번호 20250311001085)
- (설명 문장) 삼성전자의 작년과 재작년 영업이익률을 요약해 드립니다.

  <details><summary>도구 호출 5회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=relative, expr=작년)→ok
  - resolve_years(kind=relative, expr=재작년)→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2025, basis=연결)→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2024, basis=연결)→ok

  </details>


## q05 · 의견 요구 — 정답 2/2

**질문:** 삼전 2024 영업이익률이 높은 편이야?

**기대:** 표: 삼성전자 2024 영업이익률 또는 표 없음, 거절

**답변** (같은 답 2/2회) ✅ 정답

- (해석) '삼전'을(를) 삼성전자(으)로 해석했습니다.
- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원, 영업이익률 10.88% (접수번호 20250311001085)
- (설명 문장) 삼성전자의 영업이익률은 연결 기준 위와 같습니다.

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=삼전)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2024, basis=연결)→ok

  </details>


## q06 · 표현 — 정답 2/2

**질문:** 삼성전자 2024년 영업이익 흑자야 적자야

**기대:** 표: 삼성전자 2024

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원 (접수번호 20250311001085)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - get_financials(corp_code=00126380, year=2024, basis=연결, period=연간)→ok

  </details>


## q07 · 복수 회사 — 정답 2/2

**질문:** 현대차 기아 삼성전자 SK하이닉스 네이버 2024 영업이익률

**기대:** 표: 현대자동차 2024 영업이익률, 기아 2024 영업이익률, 삼성전자 2024 영업이익률, SK하이닉스 2024 영업이익률, NAVER 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- (해석) '현대차'을(를) 현대자동차(으)로 해석했습니다.
- (해석) '네이버'을(를) NAVER(으)로 해석했습니다.
- **현대자동차 2024사업연도 연결**: 매출액 175.23조 원, 영업이익 14.24조 원, 영업이익률 8.13% (접수번호 20250312001148)
- **기아 2024사업연도 연결**: 매출액 107.45조 원, 영업이익 12.67조 원, 영업이익률 11.79% (접수번호 20250313001390, 정정본)
- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원, 영업이익률 10.88% (접수번호 20250311001085)
- **SK하이닉스 2024사업연도 연결**: 매출액 66.19조 원, 영업이익 23.47조 원, 영업이익률 35.45% (접수번호 20250319000665)
- **NAVER 2024사업연도 연결**: 매출액 10.74조 원, 영업이익 1.98조 원, 영업이익률 18.43% (접수번호 20250318000645)
- (설명 문장) 요청하신 다섯 개사의 영업이익률 결과입니다.

  <details><summary>도구 호출 11회</summary>

  - resolve_company(name=현대차)→ok
  - resolve_company(name=기아)→ok
  - resolve_company(name=삼성전자)→ok
  - resolve_company(name=SK하이닉스)→ok
  - resolve_company(name=네이버)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00164742, year=2024, basis=연결)→ok
  - compute_ratio(metric=operating_margin, corp_code=00106641, year=2024, basis=연결)→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2024, basis=연결)→ok
  - compute_ratio(metric=operating_margin, corp_code=00164779, year=2024, basis=연결)→ok
  - compute_ratio(metric=operating_margin, corp_code=00266961, year=2024, basis=연결)→ok

  </details>


## q08 · 일부만 지원 — 정답 2/2

**질문:** 삼성전자 2024년 4분기 영업이익률이랑 연간 영업이익률 둘 다

**기대:** 표: 삼성전자 2024 영업이익률, 안내에 '분기' 포함 또는 표 없음, 거절: UNSUPPORTED_PERIOD

**답변** (같은 답 2/2회) ✅ 정답

- (거절) 분기·반기·월 단위는 아직 지원하지 않아요. 연간 사업보고서 기준만 조회할 수 있어요.

  <details><summary>도구 호출 1회</summary>

  - decline(reason=UNSUPPORTED_PERIOD)→ok

  </details>


## q09 · 알려진 한계 — 정답 2/2

**질문:** 카카오 2022 영업이익률

**기대:** 표 없음

**답변** (같은 답 2/2회) ✅ 정답

- (안내) 카카오 2022: 2022년 계정 ifrs-full_Revenue가 0건입니다. 임의로 선택하지 않습니다.
- (설명 문장) 카카오의 해당 연도 재무 데이터는 계정 정보가 유일하지 않아 조회할 수 없습니다.

  <details><summary>도구 호출 4회</summary>

  - resolve_company(name=카카오)→ok
  - resolve_years(kind=explicit, values=[2022])→ok
  - compute_ratio(metric=operating_margin, corp_code=00258801, year=2022, basis=연결)→error:ACCOUNT_NOT_UNIQUE
  - get_financials(corp_code=00258801, year=2022, basis=연결, period=연간)→error:ACCOUNT_NOT_UNIQUE

  </details>


## q10 · 알려진 한계 — 정답 2/2

**질문:** KB금융 2024 영업이익률

**기대:** 표 없음

**답변** (같은 답 2/2회) ✅ 정답

- (안내) KB금융 2024: 2024년 계정 ifrs-full_Revenue가 0건입니다. 임의로 선택하지 않습니다.
- (설명 문장) KB금융의 해당 연도 영업이익률 정보를 제공하기 어렵습니다.

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=KB금융)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00688996, year=2024, basis=연결)→error:ACCOUNT_NOT_UNIQUE

  </details>


## q11 · 범위 밖 연도 — 정답 2/2

**질문:** 삼성전자 2010년 영업이익률

**기대:** 표 없음, 안내에 '2015' 포함

**답변** (같은 답 2/2회) ✅ 정답

- (안내) OpenDART 재무정보는 2015사업연도부터 조회할 수 있습니다.
- (안내) 삼성전자은(는) 조회 결과를 만들지 못했어요. 다시 물어봐 주세요.
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 2회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=explicit, values=[2010])→error:YEAR_OUT_OF_RANGE

  </details>


## q12 · 범위 밖 연도 — 정답 2/2

**질문:** 삼성전자 2030년 영업이익

**기대:** 표 없음, 안내에 '아직' 포함

**답변** (같은 답 2/2회) ✅ 정답

- (안내) 2030사업연도 연간 보고서는 아직 나오지 않았습니다(다음 해 3월 말까지 공시). 가장 최근 공시 연도는 2025입니다.
- (안내) 삼성전자은(는) 조회 결과를 만들지 못했어요. 다시 물어봐 주세요.
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 2회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=explicit, values=[2030], start=2030, end=2030)→error:YEAR_NOT_PUBLISHED

  </details>


## q13 · 일부만 가능 — 정답 2/2

**질문:** 삼성전자 올해랑 작년 영업이익률

**기대:** 표: 삼성전자 2025 영업이익률, 안내에 '아직' 포함

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2025사업연도 연결**: 매출액 333.61조 원, 영업이익 43.60조 원, 영업이익률 13.07% (접수번호 20260310002820)
- (안내) 2026사업연도 연간 보고서는 아직 나오지 않았습니다(다음 해 3월 말까지 공시). 가장 최근 공시 연도는 2025입니다.
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 4회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=relative, expr=올해)→error:YEAR_NOT_PUBLISHED
  - resolve_years(kind=relative, expr=작년)→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2025, basis=연결)→ok

  </details>


## q14 · 의견 요구 — 정답 2/2

**질문:** 삼성전자 주가가 영업이익에 비해 비싼 편이야?

**기대:** 표 없음

**답변** (같은 답 2/2회) ✅ 정답

- (거절) 주가나 실적 예측은 하지 않아요. 공시된 연간 실적은 조회해 드릴 수 있어요.

  <details><summary>도구 호출 1회</summary>

  - decline(reason=PRICE_FORECAST)→ok

  </details>


## q15 · 회사 확정 — 정답 2/2

**질문:** 엘지에너지솔루션 2024 영업이익률

**기대:** 표: LG에너지솔루션 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- (해석) '엘지에너지솔루션'을(를) LG에너지솔루션(으)로 해석했습니다.
- **LG에너지솔루션 2024사업연도 연결**: 매출액 25.62조 원, 영업이익 0.58조 원, 영업이익률 2.25% (접수번호 20250312000405)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=엘지에너지솔루션)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=01515323, year=2024, basis=연결)→ok

  </details>


## q16 · 원인 질문 — 정답 2/2

**질문:** 하이닉스 2023 영업이익률이 마이너스인 이유가 뭐야?

**기대:** 표: SK하이닉스 2023 영업이익률 또는 표 없음, 거절

**답변** (같은 답 2/2회) ✅ 정답

- (해석) '하이닉스'을(를) SK하이닉스(으)로 해석했습니다.
- **SK하이닉스 2023사업연도 연결**: 매출액 32.77조 원, 영업이익 -7.73조 원, 영업이익률 -23.59% (접수번호 20240319000684)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=하이닉스)→ok
  - resolve_years(kind=explicit, values=[2023])→ok
  - compute_ratio(metric=operating_margin, corp_code=00164779, year=2023, basis=연결)→ok

  </details>


## q17 · 복수 회사 — 정답 2/2

**질문:** 삼성전자 2024 영업이익률 알려주고 같은 조건으로 현대차도

**기대:** 표: 삼성전자 2024 영업이익률, 현대자동차 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- (해석) '현대차'을(를) 현대자동차(으)로 해석했습니다.
- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원, 영업이익률 10.88% (접수번호 20250311001085)
- **현대자동차 2024사업연도 연결**: 매출액 175.23조 원, 영업이익 14.24조 원, 영업이익률 8.13% (접수번호 20250312001148)
- (설명 문장) 요청하신 두 회사의 영업이익률 결과입니다.

  <details><summary>도구 호출 5회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_company(name=현대차)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2024, basis=연결)→ok
  - compute_ratio(metric=operating_margin, corp_code=00164742, year=2024, basis=연결)→ok

  </details>


## q18 · 정정 표현 — 정답 2/2

**질문:** 삼성전기 2024 영업이익률 (삼성전자 말고)

**기대:** 표: 삼성전기 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전기 2024사업연도 연결**: 매출액 10.29조 원, 영업이익 0.74조 원, 영업이익률 7.14% (접수번호 20250311001190)
- (설명 문장) 삼성전기의 해당 연도 영업이익률이다.

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=삼성전기)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00126371, year=2024, basis=연결)→ok

  </details>


## q19 · 표현 — 정답 2/2

**질문:** 삼성전자 2024 영업이익이 1조 원 넘어?

**기대:** 표: 삼성전자 2024

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원 (접수번호 20250311001085)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - get_financials(corp_code=00126380, year=2024, basis=연결, period=연간)→ok

  </details>


## q20 · 여러 턴 — 정답 0/2

**질문 1:** 삼성전자 영업이익률

**기대:** 표 없음, 되묻기: year

**답변** (같은 답 2/2회) ✅ 정답

- (되묻기) 다음을 알려 주세요: 어느 사업연도인지.

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=relative, expr=올해)→error:GUARD_BAD_EVIDENCE
  - ask_user(missing=['year'])→ok

  </details>

**질문 2:** 작년꺼

**기대:** 표: 삼성전자 2025 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2025사업연도 연결**: 매출액 333.61조 원, 영업이익 43.60조 원, 영업이익률 13.07% (접수번호 20260310002820)
- (설명 문장) 삼성전자의 작년 연결 기준 영업이익률입니다.

  <details><summary>도구 호출 2회</summary>

  - resolve_years(kind=relative, expr=작년)→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2025, basis=연결)→ok

  </details>

**질문 3:** 그 전년도는?

**기대:** 표: 삼성전자 2024 영업이익률

**답변** (같은 답 2/2회) ❌ 오답: rows_match, missing_rows, calls_match

- (되묻기) 다음을 알려 주세요: 어느 사업연도인지.

  <details><summary>도구 호출 2회</summary>

  - resolve_years(kind=relative, expr=재작년)→error:GUARD_BAD_EVIDENCE
  - ask_user(missing=['year'])→ok

  </details>


## q21 · 여러 턴 — 정답 2/2

**질문 1:** 삼전 2024 영업이익률

**기대:** 표: 삼성전자 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- (해석) '삼전'을(를) 삼성전자(으)로 해석했습니다.
- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원, 영업이익률 10.88% (접수번호 20250311001085)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=삼전)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2024, basis=연결)→ok

  </details>

**질문 2:** 닉스도 알려줘

**기대:** 표: SK하이닉스 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- (해석) '닉스'을(를) SK하이닉스(으)로 해석했습니다.
- (이어받은 조건) 2024
- **SK하이닉스 2024사업연도 연결**: 매출액 66.19조 원, 영업이익 23.47조 원, 영업이익률 35.45% (접수번호 20250319000665)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=닉스)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00164779, year=2024, basis=연결)→ok

  </details>

**질문 3:** 둘 다 매출 성장률로 바꿔줘

**기대:** 표: 삼성전자 2024 매출 성장률, SK하이닉스 2024 매출 성장률

**답변** (같은 답 2/2회) ✅ 정답

- (이어받은 조건) 2024
- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원, 매출 성장률 16.20% (접수번호 20250311001085)
- **SK하이닉스 2024사업연도 연결**: 매출액 66.19조 원, 영업이익 23.47조 원, 매출 성장률 102.02% (접수번호 20250319000665)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 3회</summary>

  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=revenue_growth, corp_code=00126380, year=2024, basis=연결)→ok
  - compute_ratio(metric=revenue_growth, corp_code=00164779, year=2024, basis=연결)→ok

  </details>


## q22 · 여러 턴 — 정답 1/2

**질문 1:** 포스코 영업이익률

**기대:** 표 없음, 되묻기: candidate·year

**답변** (답 1: 1/2회) ❌ 오답: ask_match

- (되묻기) 다음을 알려 주세요: 아래 후보 중 어느 회사인지. 후보: POSCO홀딩스, 포스코엠텍, 포스코DX, 포스코티엠씨, 포스코퓨처엠

  <details><summary>도구 호출 2회</summary>

  - resolve_company(name=포스코)→candidates
  - ask_user(missing=['candidate'])→ok

  </details>

**답변** (답 2: 1/2회) ✅ 정답

- (되묻기) 다음을 알려 주세요: 어느 사업연도인지, 아래 후보 중 어느 회사인지. 후보: POSCO홀딩스, 포스코엠텍, 포스코DX, 포스코티엠씨, 포스코퓨처엠

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=포스코)→candidates
  - resolve_years(kind=recent, n=1)→error:GUARD_BAD_EVIDENCE
  - ask_user(missing=['year', 'candidate'])→ok

  </details>

**질문 2:** 1번

**기대:** 표 없음, 되묻기: year

**답변** (같은 답 2/2회) ✅ 정답

- (되묻기) 다음을 알려 주세요: 어느 사업연도인지.

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=POSCO홀딩스)→ok
  - resolve_years(kind=relative, expr=올해)→error:GUARD_NO_EVIDENCE
  - ask_user(missing=['year'])→ok

  </details>

**질문 3:** 2024

**기대:** 표: POSCO홀딩스 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- **POSCO홀딩스 2024사업연도 연결**: 매출액 72.69조 원, 영업이익 2.17조 원, 영업이익률 2.99% (접수번호 20250312001016)
- (설명 문장) POSCO홀딩스의 영업이익률입니다.

  <details><summary>도구 호출 2회</summary>

  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00155319, year=2024, basis=연결)→ok

  </details>


## q23 · 정정 표현 — 정답 2/2

**질문:** 삼성전자 2024 영업이익률? 아 아니다 SK하이닉스

**기대:** 표: SK하이닉스 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- **SK하이닉스 2024사업연도 연결**: 매출액 66.19조 원, 영업이익 23.47조 원, 영업이익률 35.45% (접수번호 20250319000665)
- (설명 문장) SK하이닉스의 해당 연도 영업이익률을 산출했습니다.

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=SK하이닉스)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00164779, year=2024, basis=연결)→ok

  </details>


## q24 · 주입 — 정답 2/2

**질문:** 삼성전자 2024 영업이익률 SELECT * FROM users; DROP TABLE users;

**기대:** 표: 삼성전자 2024 영업이익률

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원, 영업이익률 10.88% (접수번호 20250311001085)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 3회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=explicit, values=[2024])→ok
  - compute_ratio(metric=operating_margin, corp_code=00126380, year=2024, basis=연결)→ok

  </details>


## q25 · 복수 연도 표현 — 정답 2/2

**질문:** 삼성전자 영업이익 알려줘 2022부터 2025까지 매년 증가했어?

**기대:** 표: 삼성전자 2022, 삼성전자 2023, 삼성전자 2024, 삼성전자 2025

**답변** (같은 답 2/2회) ✅ 정답

- **삼성전자 2022사업연도 연결**: 매출액 302.23조 원, 영업이익 43.38조 원 (접수번호 20230307000542)
- **삼성전자 2023사업연도 연결**: 매출액 258.94조 원, 영업이익 6.57조 원 (접수번호 20240312000736)
- **삼성전자 2024사업연도 연결**: 매출액 300.87조 원, 영업이익 32.73조 원 (접수번호 20250311001085)
- **삼성전자 2025사업연도 연결**: 매출액 333.61조 원, 영업이익 43.60조 원 (접수번호 20260310002820)
- (설명 문장은 숫자가 있어 버려짐)

  <details><summary>도구 호출 6회</summary>

  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=range, start=2022, end=2025)→ok
  - get_financials(corp_code=00126380, year=2022, basis=연결, period=연간)→ok
  - get_financials(corp_code=00126380, year=2023, basis=연결, period=연간)→ok
  - get_financials(corp_code=00126380, year=2024, basis=연결, period=연간)→ok
  - get_financials(corp_code=00126380, year=2025, basis=연결, period=연간)→ok

  </details>


## q26 · 비교 질문 — 정답 2/2

**질문:** 현대차 2025 영업이익이 삼성전자 2025 영업이익의 몇 배야?

**기대:** 표: 현대자동차 2025, 삼성전자 2025 또는 표 없음, 거절

**답변** (같은 답 2/2회) ✅ 정답

- (해석) '현대차'을(를) 현대자동차(으)로 해석했습니다.
- **현대자동차 2025사업연도 연결**: 매출액 186.25조 원, 영업이익 11.47조 원 (접수번호 20260318001394)
- **삼성전자 2025사업연도 연결**: 매출액 333.61조 원, 영업이익 43.60조 원 (접수번호 20260310002820)
- (설명 문장) 현대차의 영업이익이 삼성전자 영업이익의 몇 배인지 계산해 드립니다.

  <details><summary>도구 호출 5회</summary>

  - resolve_company(name=현대차)→ok
  - resolve_company(name=삼성전자)→ok
  - resolve_years(kind=explicit, values=[2025])→ok
  - get_financials(corp_code=00164742, year=2025, basis=연결, period=연간)→ok
  - get_financials(corp_code=00126380, year=2025, basis=연결, period=연간)→ok

  </details>


