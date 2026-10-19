"""도구 함수의 실제 OpenDART 호출 테스트. 실행: python -m pytest tests_live (DART_API_KEY 필요)

정정 보고서·상장 구분 기대값은 2026-10-19에 공시검색(list.json)·기업개황(company.json) 응답과 직접 비교해 확인한 사실이다.
"""
import pytest

from dart import load_env
from tools import compute_ratio, get_financials, resolve_company

load_env()


def fin(name, year, basis="연결"):
    c = resolve_company(name, suggest=None)
    assert c["status"] == "ok", c
    return get_financials(c["corp_code"], year, basis)


def test_same_name_company_is_resolved_to_the_currently_listed_one():
    # '삼성물산'은 상장폐지된 옛 법인(000830, corp_cls E)과 현재 법인(028260, corp_cls Y)이 목록에 함께 있다.
    r = resolve_company("삼성물산", suggest=None)
    assert r["status"] == "ok" and r["corp_code"] == "00149655" and r["stock_code"] == "028260"


@pytest.mark.parametrize("name, year, rcept, amended, date", [
    ("현대자동차", 2022, "20240314001531", True, "20240314"),   # 2023-03 원본 이후 2024-03에 기재정정 → 정정본이 조회됨
    ("기아", 2024, "20250313001390", True, "20250313"),
    ("삼성전자", 2024, "20250311001085", False, "20250311"),    # 정정 없는 연도
    ("한화에어로스페이스", 2025, "20260316001112", False, "20260316"),   # 이후 첨부정정(재무 값 변경 없음)이 있어도 원본이 조회됨
])
def test_report_traceability_and_amendment_flag(name, year, rcept, amended, date):
    r = fin(name, year)
    assert r["status"] == "ok" and (r["rcept_no"], r["is_amended"], r["rcept_date"]) == (rcept, amended, date)
    assert r["meta_available"] is True


def test_separate_basis_differs_from_consolidated():
    cons, sep = fin("삼성전자", 2024, "연결"), fin("삼성전자", 2024, "별도")
    assert sep["status"] == "ok" and sep["basis"] == "별도"
    assert 0 < sep["revenue"] < cons["revenue"]           # 본체만의 매출은 자회사를 합친 값보다 작다(사람이 원문과 대조한 값은 아님)


def test_account_structure_gap_is_reported_not_hidden():
    # 카카오 2022는 매출 계정이 표준 ID(ifrs-full_Revenue)가 아니라 '영업수익'(다른 ID)이라 조용히 고르지 않고 오류로 알린다. 알려진 한계.
    r = fin("카카오", 2022)
    assert r["status"] == "error" and r["code"] == "ACCOUNT_NOT_UNIQUE"


def test_quarter_request_never_reaches_opendart_and_returns_unsupported():
    c = resolve_company("삼성전자", suggest=None)
    r = get_financials(c["corp_code"], 2024, period="1분기")
    assert r["status"] == "unsupported" and r["code"] == "UNSUPPORTED_PERIOD"


def test_full_chain_famous_alias_to_ratio():
    chosen = resolve_company("네이버", suggest=None)       # 유명 별칭은 바로 확정(입력과 해석이 note에 남음)
    assert chosen["status"] == "ok" and chosen["company"] == "NAVER" and "네이버" in chosen["note"]
    data = get_financials(chosen["corp_code"], 2024)
    # 손계산: 1,979,263,438,827 / 10,737,719,264,647 ≈ 18.43%
    assert compute_ratio("operating_margin", data)["value_pct"] == pytest.approx(18.43, abs=0.01)


def test_famous_tables_point_to_exactly_one_real_listed_company():
    from dart import CHOSUNG_FAMOUS, FAMOUS, famous_match, load_corps
    corps = load_corps()
    for key, target in {**FAMOUS, **CHOSUNG_FAMOUS}.items():
        assert sum(1 for c in corps if c[1] == target) == 1, (key, target)      # 대상이 목록에 정확히 한 곳
    for key in FAMOUS:
        assert famous_match(key, corps) is not None, key                         # 유명 별칭은 전부 바로 확정
    assert famous_match("ㅅㅅㅈㅈ", corps) is None and famous_match("ㄴㅇㅂ", corps) is None   # 초성이 다른 회사와 겹치면 확정하지 않는다(2026-10-19 확인)


@pytest.mark.parametrize("alias, company, stock", [("삼전", "삼성전자", "005930"), ("닉스", "SK하이닉스", "000660"), ("하이닉스", "SK하이닉스", "000660"),
                                                    ("네이버", "NAVER", "035420"), ("ㅎㄷㅈㄷㅊ", "현대자동차", "005380"), ("ㅎㅇㄴㅅ", "SK하이닉스", "000660")])
def test_famous_aliases_resolve_directly_against_real_list(alias, company, stock):
    r = resolve_company(alias, suggest=None)
    assert r["status"] == "ok" and r["company"] == company and r["stock_code"] == stock and r["resolved_by"] == "유명 별칭"


def test_ambiguous_names_are_not_confirmed_against_real_list():
    # 한화·두산은 같은 이름의 상장사(지주회사)가 실제로 있어 정확 일치로 확정되므로 제외한다
    for name in ("삼성", "현대", "엘지", "포스코", "롯데"):
        assert resolve_company(name, suggest=None)["status"] != "ok", name
