"""실제 OpenDART 호출 회귀 테스트. 실행: python -m pytest tests_live  (DART_API_KEY 필요, 기본 `pytest`에는 포함되지 않음)

기대값은 2026-10-17에 사용자가 DART 사업보고서 원문(접수번호 기준, 연결 손익계산서 당기 열)과 직접 대조해 일치를 확인한 수치다.
조회·파싱·계정 선택 로직이 바뀌어 이 값이 달라지면 회귀로 본다. 정정공시 등으로 DART 쪽 값이 바뀐 경우에는 원문을 다시 확인한 뒤 갱신한다.
"""
import pytest

from dart import fetch_financials, load_env
from finance import revenue_growth, operating_margin

load_env()

# (회사, 사업연도, 매출액(원), 영업이익(원), 접수번호)
VERIFIED = [
    ("삼성전자", 2022, 302231360000000, 43376630000000, "20230307000542"),
    ("삼성전자", 2023, 258935494000000, 6566976000000, "20240312000736"),
    ("삼성전자", 2024, 300870903000000, 32725961000000, "20250311001085"),
    ("삼성전자", 2025, 333605938000000, 43601051000000, "20260310002820"),
    ("SK하이닉스", 2022, 44621568000000, 6809417000000, "20230321001209"),
    ("SK하이닉스", 2023, 32765719000000, -7730313000000, "20240319000684"),
    ("SK하이닉스", 2024, 66192960000000, 23467319000000, "20250319000665"),
    ("SK하이닉스", 2025, 97146675000000, 47206319000000, "20260317000635"),
    ("현대자동차", 2022, 142527535000000, 9819769000000, "20240314001531"),  # 접수일이 2024-03: 정정 보고서로 보이나 미확인
    ("현대자동차", 2023, 162663579000000, 15126901000000, "20240313001451"),
    ("현대자동차", 2024, 175231153000000, 14239592000000, "20250312001148"),
    ("현대자동차", 2025, 186254472000000, 11467851000000, "20260318001394"),
]


@pytest.mark.parametrize("company, year, revenue, op, rcept", VERIFIED)
def test_verified_values(company, year, revenue, op, rcept):
    r = fetch_financials(company, year)
    assert (r["revenue"], r["operating_profit"], r["rcept_no"]) == (revenue, op, rcept)


def test_ratios_from_live_data_match_hand_calculation():
    # 손계산: -7,730,313 / 32,765,719 ≈ -23.59%, (333,605,938 - 300,870,903) / 300,870,903 ≈ 10.88%
    assert operating_margin(fetch_financials("SK하이닉스", 2023)) == pytest.approx(-23.59, abs=0.01)
    assert revenue_growth(fetch_financials("삼성전자", 2025), fetch_financials("삼성전자", 2024)) == pytest.approx(10.88, abs=0.01)
