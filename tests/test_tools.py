from datetime import date

import pytest

from dart import FinError
from tools import TOOLS, compute_ratio, get_financials, latest_published_year, resolve_company, resolve_years

OCT = date(2026, 10, 19)   # 오늘 날짜를 고정해 테스트가 날짜에 따라 달라지지 않게 한다
FEB = date(2027, 2, 10)    # 1~3월: 작년 보고서가 아직 안 나왔을 수 있는 시기
OCT27 = date(2027, 10, 19)

CORPS = [["1", "삼성전자", "005930", "SAMSUNG ELECTRONICS CO.,LTD."], ["2", "NAVER", "035420", "NAVER Corporation"],
         ["3", "삼성물산", "000830", "Samsung C&T"], ["4", "삼성물산", "028260", "SAMSUNG C&T"],
         ["5", "우리금융지주", "316140", ""], ["6", "우리금융지주", "053000", ""], ["7", "애니플러스", "310200", "Aniplus"],
         ["8", "POSCO홀딩스", "005490", "POSCO Holdings Inc."], ["9", "SK하이닉스", "000660", "SK hynix Inc."]]


def years(expr, today=OCT):
    return resolve_years(expr, today=today)


# ---------- resolve_years ----------
def test_latest_published_year_depends_on_today():
    assert latest_published_year(date(2026, 10, 19)) == 2025
    assert latest_published_year(date(2027, 3, 31)) == 2025   # 3월 말 전까지는 작년 보고서가 다 나온 것으로 보지 않음
    assert latest_published_year(date(2027, 4, 1)) == 2026


def test_explicit_and_range_years_sorted_unique():
    assert years({"kind": "explicit", "values": [2025, 2023, 2023]})["years"] == [2023, 2025]   # 건너뛴 연도를 채우지 않음
    assert years({"kind": "range", "start": 2023, "end": 2025})["years"] == [2023, 2024, 2025]


def test_reversed_range_is_normalized_with_note():
    r = years({"kind": "range", "start": 2025, "end": 2023})
    assert r["years"] == [2023, 2024, 2025] and r["notes"]


@pytest.mark.parametrize("expr, today, expected", [
    ({"kind": "relative", "expr": "작년"}, OCT, [2025]),
    ({"kind": "relative", "expr": "재작년"}, OCT, [2024]),
    ({"kind": "relative", "expr": "작년"}, FEB, [2026]),          # 오늘 기준 작년(보고서가 없을 수 있다는 안내가 붙음)
    ({"kind": "recent", "n": 3}, OCT, [2023, 2024, 2025]),
    ({"kind": "recent", "n": 3}, FEB, [2023, 2024, 2025]),        # 2월에는 2026 보고서가 아직 없으니 2025까지
    ({"kind": "recent", "n": 3}, OCT27, [2024, 2025, 2026]),
])
def test_relative_years_follow_today(expr, today, expected):
    assert years(expr, today)["years"] == expected


def test_last_year_in_early_year_carries_not_yet_published_note():
    assert any("3월 말" in n for n in years({"kind": "relative", "expr": "작년"}, FEB)["notes"])
    assert not years({"kind": "relative", "expr": "작년"}, OCT)["notes"]


def test_this_year_and_future_are_not_published_with_latest_hint():
    for expr in ({"kind": "relative", "expr": "올해"}, {"kind": "explicit", "values": [2026]}, {"kind": "explicit", "values": [2030]}):
        r = years(expr)
        assert r["status"] == "error" and r["code"] == "YEAR_NOT_PUBLISHED" and r["latest_published_year"] == 2025


@pytest.mark.parametrize("expr, code", [
    ({"kind": "explicit", "values": [2010]}, "YEAR_OUT_OF_RANGE"),
    ({"kind": "range", "start": 2015, "end": 2030}, "TOO_MANY_YEARS"),
    ({"kind": "range", "start": 2015, "end": 2025}, "TOO_MANY_YEARS"),   # 11개
    ({"kind": "recent", "n": 0}, "TOO_MANY_YEARS"),
    ({"kind": "recent", "n": 11}, "TOO_MANY_YEARS"),
    ({"kind": "relative", "expr": "내년"}, "INVALID_YEAR_EXPR"),
    ({"kind": "bogus"}, "INVALID_YEAR_EXPR"),
    ({"kind": "explicit", "values": ["abc"]}, "INVALID_YEAR_EXPR"),
    ({"kind": "range", "start": 2023}, "INVALID_YEAR_EXPR"),
    (None, "INVALID_YEAR_EXPR"),
    ("2024", "INVALID_YEAR_EXPR"),
])
def test_bad_year_expressions_return_error_not_exception(expr, code):
    r = years(expr)
    assert r["status"] == "error" and r["code"] == code


# ---------- resolve_company ----------
def rc(name, **kw):
    kw.setdefault("suggest", None)
    kw.setdefault("listing_fn", lambda code: None)
    return resolve_company(name, corps=CORPS, **kw)


def test_exact_and_formatting_only_match_confirms():
    assert rc("삼성전자")["corp_code"] == "1"
    assert rc(" naver ")["company"] == "NAVER"


def test_duplicate_names_confirm_only_the_currently_listed_one():
    r = rc("삼성물산", listing_fn=lambda code: {"3": "E", "4": "Y"}[code])   # 옛 삼성물산은 E(상장폐지 등)
    assert r["status"] == "ok" and r["corp_code"] == "4" and r["note"]


def test_duplicate_names_both_listed_stay_ambiguous_with_stock_codes():
    r = rc("우리금융지주", listing_fn=lambda code: "Y")
    assert r["status"] == "candidates" and r["reason"] == "AMBIGUOUS" and {c["stock_code"] for c in r["candidates"]} == {"316140", "053000"}


def test_duplicate_names_status_lookup_failure_does_not_guess():
    r = rc("우리금융지주", listing_fn=lambda code: None)     # 상태를 알 수 없으면 확정하지 않는다
    assert r["status"] != "ok"


def test_ambiguous_alias_is_candidate_not_confirmation():
    r = rc("포스코")
    assert r["status"] == "candidates" and r["candidates"][0] == {"name": "POSCO홀딩스", "stock_code": "005490", "source": "별칭 사전"}


@pytest.mark.parametrize("alias, company", [("삼전", "삼성전자"), ("네이버", "NAVER"), ("하이닉스", "SK하이닉스"), ("닉스", "SK하이닉스"), ("하닉", "SK하이닉스")])
def test_famous_alias_is_confirmed_immediately_and_shows_interpretation(alias, company):
    r = rc(alias)
    assert r["status"] == "ok" and r["company"] == company and r["resolved_by"] == "유명 별칭" and alias in r["note"] and company in r["note"]


def test_foreign_company_is_unsupported_without_misleading_candidates():
    ai = lambda n, c: {"proposed": [], "verified": [], "kind": "foreign"}
    r = rc("애플", suggest=ai)
    assert r["status"] == "unsupported" and r["code"] == "COMPANY_NOT_SUPPORTED" and "해외 기업" in r["message"]


def test_unknown_company_without_ai_signal_is_error_not_found():
    r = rc("전혀없는이름회사")
    assert r["status"] == "error" and r["code"] == "COMPANY_NOT_FOUND"


@pytest.mark.parametrize("name", [None, "", "   ", 123, "가" * 51])
def test_invalid_company_names_return_error(name):
    r = rc(name)
    assert r["status"] == "error" and r["code"] == "INVALID_NAME"


# ---------- get_financials ----------
def ok_fetch(corp_code, company, year, basis, _get):
    return {"company": company, "corp_code": corp_code, "year": year, "basis": basis, "unit": "원", "revenue": 1000, "operating_profit": 100,
            "rcept_no": "R1", "fetched_at": "t"}


def gf(corp_code="1", year=2024, **kw):
    kw.setdefault("fetch", ok_fetch)
    kw.setdefault("meta_fn", lambda c, y, r: {"report_name": "[기재정정]사업보고서 (2024.12)", "rcept_date": "20250313", "is_amended": True, "filings_for_year": 2})
    return get_financials(corp_code, year, corps=CORPS, today=OCT, **kw)


def test_get_financials_ok_includes_report_traceability():
    r = gf()
    assert r["status"] == "ok" and r["company"] == "삼성전자" and r["rcept_no"] == "R1"
    assert r["report_name"].startswith("[기재정정]") and r["rcept_date"] == "20250313" and r["is_amended"] is True


def test_report_meta_failure_does_not_block_the_numbers():
    r = gf(meta_fn=lambda c, y, rc_: None)
    assert r["status"] == "ok" and r["meta_available"] is False and r["is_amended"] is None


@pytest.mark.parametrize("period", ["분기", "1분기", "반기", "월별"])
def test_quarter_month_requests_are_refused_not_turned_into_annual(period):
    called = []
    r = gf(period=period, fetch=lambda *a: called.append(a))
    assert r["status"] == "unsupported" and r["code"] == "UNSUPPORTED_PERIOD" and not called     # 조회 자체를 하지 않는다


def test_separate_basis_is_supported_and_passed_through():
    seen = {}
    gf(basis="별도", fetch=lambda corp, name, year, basis, g: seen.update(basis=basis) or ok_fetch(corp, name, year, basis, g))
    assert seen["basis"] == "별도"


@pytest.mark.parametrize("kwargs, code", [
    ({"basis": "개별"}, "UNSUPPORTED_BASIS"),
    ({"year": "2024"}, "INVALID_YEAR"),
    ({"year": True}, "INVALID_YEAR"),
    ({"year": 2010}, "YEAR_OUT_OF_RANGE"),
    ({"year": 2026}, "YEAR_NOT_PUBLISHED"),
    ({"year": 2031}, "YEAR_NOT_PUBLISHED"),
    ({"corp_code": "999"}, "INVALID_CORP_CODE"),
    ({"corp_code": None}, "INVALID_CORP_CODE"),
])
def test_get_financials_validates_inputs(kwargs, code):
    r = gf(**kwargs)
    assert r["status"] == "error" and r["code"] == code


def test_this_year_error_hints_latest_published_year():
    assert gf(year=2026)["latest_published_year"] == 2025


def test_fetch_errors_become_structured_results():
    def boom(*a):
        raise FinError("ACCOUNT_NOT_UNIQUE", "계정 0건")
    r = gf(fetch=boom)
    assert r == {"status": "error", "code": "ACCOUNT_NOT_UNIQUE", "message": "계정 0건"}


def test_data_missing_for_last_year_in_early_year_explains_timing():
    def missing(*a):
        raise FinError("DATA_MISSING", "없음")
    r = get_financials("1", 2026, corps=CORPS, today=FEB, fetch=missing, meta_fn=lambda *a: None)
    assert r["code"] == "DATA_MISSING" and "3월 말" in r["message"]
    r2 = get_financials("1", 2024, corps=CORPS, today=FEB, fetch=missing, meta_fn=lambda *a: None)
    assert "3월 말" not in r2["message"]


# ---------- compute_ratio ----------
def fin(year, rev, op, basis="연결", company="삼성전자"):
    return {"company": company, "year": year, "basis": basis, "unit": "원", "revenue": rev, "operating_profit": op}


def test_compute_margin_and_growth():
    assert compute_ratio("operating_margin", fin(2024, 1000, 150))["value_pct"] == pytest.approx(15.0)
    assert compute_ratio("operating_margin", fin(2024, 1000, -250))["value_pct"] == pytest.approx(-25.0)   # 영업손실은 정상 결과
    assert compute_ratio("revenue_growth", fin(2024, 1250, 0), fin(2023, 1000, 0))["value_pct"] == pytest.approx(25.0)


@pytest.mark.parametrize("args, code", [
    (("operating_margin", fin(2024, 0, 10), None), "INVALID_DENOMINATOR"),
    (("revenue_growth", fin(2024, 10, 1), fin(2023, -5, 1)), "INVALID_DENOMINATOR"),
    (("revenue_growth", fin(2024, 10, 1), fin(2022, 10, 1)), "PERIOD_MISMATCH"),
    (("revenue_growth", fin(2024, 10, 1), fin(2023, 10, 1, basis="별도")), "BASIS_MISMATCH"),
    (("revenue_growth", fin(2024, 10, 1), None), "INVALID_INPUT"),
    (("operating_margin", {"revenue": 1}, None), "INVALID_INPUT"),
    (("operating_margin", None, None), "INVALID_INPUT"),
    (("sharpe_ratio", fin(2024, 10, 1), None), "INVALID_METRIC"),
])
def test_compute_ratio_errors_are_structured(args, code):
    r = compute_ratio(*args)
    assert r["status"] == "error" and r["code"] == code


def test_tool_registry_lists_the_four_tools():
    assert set(TOOLS) == {"resolve_years", "resolve_company", "get_financials", "compute_ratio"}
