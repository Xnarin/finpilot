"""에이전트가 호출할 도구 함수. 모든 함수는 예외를 던지지 않고 {"status": ...} 사전을 돌려준다.

status: ok(성공) / candidates(사용자 확인이 필요한 후보) / unsupported(지원 범위 밖) / error(오류 코드와 사용자용 메시지)
금융 수치는 OpenDART 조회와 코드 계산으로만 만들고, 입력은 여기서 검증한다(LLM이 넘긴 값을 믿지 않는다).
"""
from datetime import date

from dart import (LISTED_CLS, FinError, exact_matches, famous_match, fetch_by_code, http_get, listing_class, load_corps, report_meta)
from finance import KIND_LABEL, candidates_for, operating_margin, revenue_growth
from langsmith import traceable
from question import suggest_companies

MIN_YEAR = 2015  # OpenDART 재무정보는 2015 사업연도부터 제공
MAX_YEARS = 10
BASES = ("연결", "별도")
UNSUPPORTED_PERIODS = ("분기", "1분기", "2분기", "3분기", "4분기", "반기", "상반기", "하반기", "월", "월별")
_REL = {"올해": 0, "금년": 0, "작년": -1, "지난해": -1, "전년": -1, "재작년": -2}


def _err(code, message, **extra):
    return {"status": "error", "code": code, "message": message, **extra}


def latest_published_year(today):
    """연간 사업보고서가 대부분 공시되어 있다고 볼 수 있는 가장 최근 사업연도. 12월 결산 법인은 보통 3월 말까지 공시한다."""
    return today.year - 1 if today >= date(today.year, 4, 1) else today.year - 2


@traceable(name="resolve_years", run_type="tool")
def resolve_years(expr, today=None):
    """연도 표현 -> 사업연도 목록. 상대 표현은 오늘 날짜 기준. 표현 형식:
    {"kind": "explicit", "values": [2023, 2025]} / {"kind": "range", "start": 2023, "end": 2025} /
    {"kind": "relative", "expr": "작년"} / {"kind": "recent", "n": 3}"""
    today = today or date.today()
    latest = latest_published_year(today)
    notes = []
    try:
        kind = expr["kind"]
        if kind == "explicit":
            years = [int(v) for v in expr["values"]]
        elif kind == "range":
            a, b = int(expr["start"]), int(expr["end"])
            if a > b:
                a, b = b, a
                notes.append("시작·끝 연도가 거꾸로여서 오름차순으로 바꿨습니다.")
            years = list(range(a, b + 1)) if b - a < 100 else []
        elif kind == "relative":
            if expr["expr"] not in _REL:
                return _err("INVALID_YEAR_EXPR", f"알 수 없는 상대 연도 표현입니다: {expr['expr']}")
            years = [today.year + _REL[expr["expr"]]]
        elif kind == "recent":
            n = int(expr["n"])
            if not 1 <= n <= MAX_YEARS:
                return _err("TOO_MANY_YEARS", f"최근 몇 년은 1~{MAX_YEARS}년까지 조회할 수 있습니다.")
            years = list(range(latest - n + 1, latest + 1))
            notes.append(f"'최근 {n}년'은 오늘({today.isoformat()}) 기준으로 공시된 가장 최근 사업연도({latest})까지로 계산했습니다.")
        else:
            return _err("INVALID_YEAR_EXPR", f"알 수 없는 연도 표현 종류입니다: {kind}")
    except (KeyError, TypeError, ValueError):
        return _err("INVALID_YEAR_EXPR", "연도 표현의 형식이 올바르지 않습니다.")
    years = sorted(set(years))
    if not years or len(years) > MAX_YEARS:
        return _err("TOO_MANY_YEARS", f"한 번에 {MAX_YEARS}개 연도까지만 조회할 수 있습니다. 범위를 줄여 주세요.")
    if years[0] < MIN_YEAR:
        return _err("YEAR_OUT_OF_RANGE", f"OpenDART 재무정보는 {MIN_YEAR}사업연도부터 조회할 수 있습니다.")
    future = [y for y in years if y >= today.year]
    if future:
        return _err("YEAR_NOT_PUBLISHED", f"{future[0]}사업연도 연간 보고서는 아직 나오지 않았습니다(다음 해 3월 말까지 공시). 가장 최근 공시 연도는 {latest}입니다.",
                    latest_published_year=latest)
    if today.year - 1 in years and latest < today.year - 1:
        notes.append(f"{today.year - 1}사업연도 보고서는 보통 3월 말까지 공시되므로 아직 없을 수 있습니다.")
    return {"status": "ok", "years": years, "notes": notes}


@traceable(name="resolve_company", run_type="tool", process_inputs=lambda i: {"name": i["name"]})
def resolve_company(name, corps=None, suggest=suggest_companies, listing_fn=listing_class):
    """회사명 -> 확정(ok) / 사용자 확인이 필요한 후보(candidates) / 조회 불가(unsupported) / 찾지 못함(error).
    누구나 쓰는 유명 별칭·초성(삼전·하닉·닉스·네이버·ㅅㅅㅈㅈ 등)은 바로 확정하고, 그 밖의 별칭·약칭·AI 제안은 자동 확정하지 않는다. 같은 이름의 회사가 둘 이상이면 현재 상장된 곳이 하나일 때만 확정한다."""
    if not isinstance(name, str) or not name.strip() or len(name) > 50:
        return _err("INVALID_NAME", "회사명을 1~50자로 입력해 주세요.")
    try:
        corps = corps if corps is not None else load_corps()
    except FinError as e:
        return _err(e.code, e.message)
    hits = exact_matches(name, corps)
    note = None
    if len(hits) > 1:
        listed = [h for h in hits if listing_fn(h[0]) in LISTED_CLS]
        if len(listed) == 1:
            hits, note = listed, "같은 이름의 회사 중 현재 상장된 곳으로 확정했습니다."
        elif len(listed) > 1:
            return {"status": "candidates", "reason": "AMBIGUOUS", "message": f"'{name.strip()}'에 해당하는 상장사가 {len(listed)}곳입니다. 어느 회사인지 알려 주세요.",
                    "candidates": [{"name": h[1], "stock_code": h[2], "source": "이름 일치"} for h in listed[:5]]}
        else:
            hits = []
    if len(hits) == 1:
        c = hits[0]
        return {"status": "ok", "company": c[1], "corp_code": c[0], "stock_code": c[2], "note": note, "resolved_by": "정확 일치"}
    if not hits:
        fm = famous_match(name, corps)
        if fm:  # 유명 별칭·초성은 바로 확정하되, 입력과 해석을 결과에 남겨 화면에 보이게 한다
            return {"status": "ok", "company": fm[1], "corp_code": fm[0], "stock_code": fm[2], "resolved_by": "유명 별칭",
                    "note": f"'{name.strip()}'을(를) {fm[1]}(으)로 해석했습니다."}
    names, sources, ai = candidates_for(name, corps, suggest=suggest)
    kind = ai.get("kind") if ai else None
    if names:
        return {"status": "candidates", "reason": "NOT_FOUND", "message": f"'{name.strip()}'과(와) 정확히 일치하는 상장사를 찾지 못했습니다. 아래 중에 있나요?",
                "candidates": [{"name": n, "stock_code": next((c[2] for c in corps if c[1] == n), None), "source": sources[n]} for n in names], "ai_kind": kind}
    if kind in KIND_LABEL:
        return {"status": "unsupported", "code": "COMPANY_NOT_SUPPORTED", "ai_kind": kind,
                "message": f"'{name.strip()}'은(는) {KIND_LABEL[kind]}으로 보여 OpenDART 상장사 공시로 조회할 수 없습니다. 한국 상장사라면 정식 회사명으로 다시 입력해 주세요."}
    return _err("COMPANY_NOT_FOUND", f"상장사 '{name.strip()}'을(를) 찾지 못했습니다.", ai_kind=kind)


@traceable(name="get_financials", run_type="tool", process_inputs=lambda i: {k: i.get(k) for k in ("corp_code", "year", "basis", "period")})
def get_financials(corp_code, year, basis="연결", period="연간", corps=None, today=None, fetch=fetch_by_code, meta_fn=report_meta, _get=http_get):
    """확정된 회사(resolve_company가 준 corp_code)의 연간 사업보고서 매출액·영업이익. 같은 연도 보고서가 여럿이면 OpenDART가 주는 최신 정정본이며
    접수번호·접수일·정정 여부를 함께 돌려준다. 분기·월·환산 요청은 조용히 연간 값으로 바꾸지 않고 지원하지 않는다고 알린다."""
    today = today or date.today()
    if period != "연간":
        what = "분기·반기·월" if period in UNSUPPORTED_PERIODS else f"'{period}'"
        return {"status": "unsupported", "code": "UNSUPPORTED_PERIOD", "message": f"{what} 단위 조회는 아직 지원하지 않습니다. 연간 사업보고서 기준만 조회할 수 있습니다."}
    if basis not in BASES:
        return _err("UNSUPPORTED_BASIS", f"재무제표 기준은 {'/'.join(BASES)} 중에서 골라 주세요.")
    if isinstance(year, bool) or not isinstance(year, int):
        return _err("INVALID_YEAR", "사업연도는 정수로 입력해 주세요.")
    if year < MIN_YEAR:
        return _err("YEAR_OUT_OF_RANGE", f"OpenDART 재무정보는 {MIN_YEAR}사업연도부터 조회할 수 있습니다.")
    if year >= today.year:
        return _err("YEAR_NOT_PUBLISHED", f"{year}사업연도 연간 보고서는 아직 나오지 않았습니다(다음 해 3월 말까지 공시).",
                    latest_published_year=latest_published_year(today))
    try:
        corps = corps if corps is not None else load_corps()
        row = next((c for c in corps if c[0] == corp_code), None) if isinstance(corp_code, str) else None
        if row is None:
            return _err("INVALID_CORP_CODE", "확정되지 않은 회사입니다. 먼저 회사를 확정해 주세요.")
        data = fetch(corp_code, row[1], year, basis, _get)
    except FinError as e:
        msg = e.message
        if e.code == "DATA_MISSING" and year == today.year - 1 and today < date(today.year, 4, 1):
            msg += " 작년 보고서는 보통 3월 말까지 공시되므로 아직 나오지 않았을 수 있습니다."
        return _err(e.code, msg)
    meta = meta_fn(corp_code, year, data["rcept_no"])
    return {"status": "ok", **data, "stock_code": row[2], "report_name": meta and meta["report_name"], "rcept_date": meta and meta["rcept_date"],
            "is_amended": meta and meta["is_amended"], "meta_available": meta is not None}


@traceable(name="compute_ratio", run_type="tool", process_inputs=lambda i: {"metric": i.get("metric")})
def compute_ratio(metric, current, previous=None):
    """metric: "operating_margin"(영업이익률) / "revenue_growth"(매출 성장률). current·previous는 get_financials의 ok 결과."""
    need = ("company", "year", "basis", "unit", "revenue", "operating_profit")
    try:
        if metric not in ("operating_margin", "revenue_growth"):
            return _err("INVALID_METRIC", "지원하는 계산은 operating_margin, revenue_growth입니다.")
        if not isinstance(current, dict) or any(k not in current for k in need):
            return _err("INVALID_INPUT", "조회 결과(current)가 올바르지 않습니다.")
        if metric == "operating_margin":
            return {"status": "ok", "metric": metric, "value_pct": operating_margin(current), "formula": "영업이익 ÷ 매출액 × 100",
                    "year": current["year"], "basis": current["basis"]}
        if not isinstance(previous, dict) or any(k not in previous for k in need):
            return _err("INVALID_INPUT", "매출 성장률에는 전기 조회 결과(previous)가 필요합니다.")
        return {"status": "ok", "metric": metric, "value_pct": revenue_growth(current, previous), "formula": "(당기 매출액 − 전기 매출액) ÷ 전기 매출액 × 100",
                "year": current["year"], "basis": current["basis"]}
    except FinError as e:
        return _err(e.code, e.message)


TOOLS = {"resolve_years": resolve_years, "resolve_company": resolve_company, "get_financials": get_financials, "compute_ratio": compute_ratio}
