import pytest

from dart import FinError, company_candidates, fetch_financials, find_company
from finance import operating_margin, revenue_growth, run


def rec(year=2024, rev=1000, op=100, basis="연결", unit="원", company="가"):
    return {"company": company, "year": year, "basis": basis, "unit": unit, "revenue": rev, "operating_profit": op}


def test_margin_normal():
    assert operating_margin(rec(rev=1000, op=150)) == pytest.approx(15.0)


def test_margin_negative_on_loss():
    assert operating_margin(rec(rev=1000, op=-250)) == pytest.approx(-25.0)


@pytest.mark.parametrize("rev", [0, -1000])
def test_margin_bad_denominator(rev):
    with pytest.raises(FinError) as e:
        operating_margin(rec(rev=rev))
    assert e.value.code == "INVALID_DENOMINATOR"


def test_growth_normal():
    assert revenue_growth(rec(2024, 1250), rec(2023, 1000)) == pytest.approx(25.0)


def test_growth_decline():
    assert revenue_growth(rec(2024, 800), rec(2023, 1000)) == pytest.approx(-20.0)


@pytest.mark.parametrize("prev_rev", [0, -5])
def test_growth_bad_denominator(prev_rev):
    with pytest.raises(FinError) as e:
        revenue_growth(rec(2024, 1000), rec(2023, prev_rev))
    assert e.value.code == "INVALID_DENOMINATOR"


def test_growth_year_mismatch():
    with pytest.raises(FinError) as e:
        revenue_growth(rec(2024), rec(2022))
    assert e.value.code == "PERIOD_MISMATCH"


def test_growth_basis_mismatch():
    with pytest.raises(FinError) as e:
        revenue_growth(rec(2024), rec(2023, basis="별도"))
    assert e.value.code == "BASIS_MISMATCH"


def row(account_id, amount, sj="IS", currency="KRW", rcept="R1"):
    return {"sj_div": sj, "account_id": account_id, "thstrm_amount": amount, "currency": currency, "rcept_no": rcept}


OK_ROWS = [row("ifrs-full_Revenue", "1,000"), row("dart_OperatingIncomeLoss", "-50"), row("ifrs-full_GrossProfit", "9")]


CORPS = [["00126380", "삼성전자", "005930"], ["00000001", "가나다", "000001"], ["00000002", "가나다", "000002"], ["00000003", "삼성전자서비스", "000003"]]


def test_find_company_exact():
    assert find_company(" 삼성전자 ", CORPS) == ("00126380", "삼성전자")


def test_find_company_ambiguous_and_not_found():
    with pytest.raises(FinError) as e:
        find_company("가나다", CORPS)
    assert e.value.code == "COMPANY_AMBIGUOUS"
    with pytest.raises(FinError) as e:
        find_company("삼성", CORPS)  # 부분 일치로 임의 선택하지 않고 후보만 안내
    assert e.value.code == "COMPANY_NOT_FOUND" and "삼성전자" in e.value.message


def fake(payload):
    return lambda params: payload


def fetch(payload):
    return fetch_financials("삼성전자", 2024, _get=fake(payload), _corps=CORPS)


def test_fetch_parses_amounts_and_source():
    r = fetch({"status": "000", "list": OK_ROWS})
    assert (r["revenue"], r["operating_profit"], r["rcept_no"], r["unit"], r["basis"]) == (1000, -50, "R1", "원", "연결")


def test_fetch_requests_cfs_for_consolidated():
    seen = {}
    fetch_financials("삼성전자", 2024, _get=lambda p: seen.update(p) or {"status": "000", "list": OK_ROWS}, _corps=CORPS)
    assert seen["corp_code"] == "00126380" and seen["fs_div"] == "CFS" and seen["bsns_year"] == "2024" and seen["reprt_code"] == "11011"


def test_fetch_no_data_status():
    with pytest.raises(FinError) as e:
        fetch({"status": "013", "message": "조회된 데이타가 없습니다."})
    assert e.value.code == "DATA_MISSING"


def test_fetch_other_status_is_api_error():
    with pytest.raises(FinError) as e:
        fetch({"status": "010", "message": "등록되지 않은 키"})
    assert e.value.code == "API_ERROR"


@pytest.mark.parametrize("rows, code", [
    (OK_ROWS[:1], "ACCOUNT_NOT_UNIQUE"),                              # 영업이익 없음
    (OK_ROWS + [row("ifrs-full_Revenue", "5")], "ACCOUNT_NOT_UNIQUE"),  # 매출 후보 2건
    ([row("ifrs-full_Revenue", ""), OK_ROWS[1]], "PARSE_ERROR"),       # 빈 문자열을 0으로 바꾸지 않음
    ([row("ifrs-full_Revenue", "1,0x"), OK_ROWS[1]], "PARSE_ERROR"),
    ([row("ifrs-full_Revenue", "1", currency="USD"), OK_ROWS[1]], "UNIT_MISMATCH"),
    ([OK_ROWS[0], row("dart_OperatingIncomeLoss", "1", rcept="R2")], "SOURCE_MISMATCH"),
])
def test_fetch_bad_rows(rows, code):
    with pytest.raises(FinError) as e:
        fetch({"status": "000", "list": rows})
    assert e.value.code == code


def test_run_missing_prior_year():
    def f(company, year, basis="연결"):
        if year == 2023:
            raise FinError("DATA_MISSING", "없음")
        return {**rec(year, company="삼성전자"), "rcept_no": "R", "fetched_at": "t"}
    r = run("매출 성장률 계산", 2024, "삼성전자", fetch=f)
    assert r["error_code"] == "DATA_MISSING" and r["result"] is None
    assert [s["status"] for s in r["steps"]] == ["성공", "실패"]


def test_run_growth_and_margin_with_fixed_data():
    d = {2023: 1000, 2024: 1250}
    f = lambda company, year, basis="연결": {**rec(year, rev=d[year], op=250, company="삼성전자"), "rcept_no": "R", "fetched_at": "t"}
    assert run("매출 성장률 계산", 2024, "삼성전자", fetch=f)["result"]["revenue_growth_pct"] == pytest.approx(25.0)
    assert run("영업이익률 계산", 2024, "삼성전자", fetch=f)["result"]["operating_margin_pct"] == pytest.approx(20.0)  # 250/1250


def fake_parse(parsed):
    return lambda text: {"parsed": parsed, "model": "fake", "ms": 1.0}


@pytest.mark.parametrize("parsed, missing_label", [
    ({"company": None, "year": 2024, "task": "실적 조회"}, "기업"),
    ({"company": "삼성전자", "year": None, "task": "실적 조회"}, "사업연도"),
    ({"company": "삼성전자", "year": 2024, "task": None}, "작업"),
])
def test_ask_incomplete_question_stops_without_guessing(parsed, missing_label):
    from finance import ask
    r = ask("q", parse=fake_parse(parsed))
    assert r["error_code"] == "QUESTION_INCOMPLETE" and missing_label in r["error_message"]
    assert r["result"] is None and [s["status"] for s in r["steps"]] == ["실패"]


def test_ask_llm_failure_is_reported():
    from finance import ask

    def boom(text):
        raise FinError("LLM_ERROR", "실패")
    assert ask("q", parse=boom)["error_code"] == "LLM_ERROR"


def test_parse_question_rejects_bad_llm_output():
    from question import parse_question
    with pytest.raises(FinError) as e:
        parse_question("q", _llm=lambda t: '{"task": "주가 예측"}')  # 허용되지 않은 작업값
    assert e.value.code == "LLM_BAD_OUTPUT"
    assert parse_question("q", _llm=lambda t: '{"company": "가", "year": 2024, "task": "실적 조회"}')["parsed"]["year"] == 2024


CORPS2 = [["1", "삼성전자", "005930"], ["2", "삼성전기", "009150"], ["3", "SK하이닉스", "000660"], ["4", "NAVER", "035420"],
          ["5", "현대자동차", "005380"], ["6", "카카오", "035720"]]


def test_candidates_abbreviation_substring_and_typo():
    assert company_candidates("삼전", CORPS2)[:2] == ["삼성전자", "삼성전기"]  # 약칭
    assert company_candidates("하이닉스", CORPS2)[0] == "SK하이닉스"           # 부분 일치
    assert "현대자동차" in company_candidates("현대자동자", CORPS2)             # 오타


def test_formatting_only_difference_is_accepted_but_abbreviation_is_not():
    assert find_company("sk 하이닉스", CORPS2) == ("3", "SK하이닉스")
    assert find_company("naver", CORPS2) == ("4", "NAVER")
    assert find_company("삼전", CORPS2) == ("1", "삼성전자")     # 유명 별칭은 바로 확정
    with pytest.raises(FinError) as e:
        find_company("삼성", CORPS2)                             # 모호한 이름은 확정하지 않고 되묻기
    assert e.value.code == "COMPANY_NOT_FOUND" and "삼성전자" in e.value.candidates


def test_pick_company_reruns_with_chosen_name_and_records_choice():
    from finance import pick_company

    def f(company, year, basis="연결"):
        if company == "삼전":
            raise FinError("COMPANY_NOT_FOUND", "x", ["삼성전자"])
        return {**rec(year, company=company), "rcept_no": "R", "fetched_at": "t"}
    r0 = run("영업이익률 계산", 2024, "삼전", fetch=f, candidates_fn=None)
    assert r0["candidates"] == ["삼성전자"]
    r1 = pick_company(r0, "삼성전자", fetch=f)
    assert r1["error_code"] is None and r1["result"]["company"] == "삼성전자"
    assert r1["steps"][0]["data"] == {"입력": "삼전", "선택": "삼성전자"}
