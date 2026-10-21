"""MCP 서버 테스트(네트워크 없음). 실제 MCP 클라이언트(mcp.client.Client)가 서버를 프로세스 안에서 호출한다."""
import asyncio

import pytest
from mcp.client import Client

import mcp_server
import tools as T

CORPS = [["00126380", "삼성전자", "005930", "SAMSUNG ELECTRONICS CO.,LTD."], ["00164779", "SK하이닉스", "000660", "SK hynix Inc."],
         ["00266961", "NAVER", "035420", "NAVER Corporation"], ["00000009", "POSCO홀딩스", "005490", ""], ["00000010", "포스코퓨처엠", "003670", ""]]


def call(name, args):
    async def go():
        async with Client(mcp_server.mcp) as c:
            return await c.call_tool(name, args)
    return asyncio.run(go())


def tools_list():
    async def go():
        async with Client(mcp_server.mcp) as c:
            return (await c.list_tools()).tools
    return asyncio.run(go())


def fin(corp_code, year, basis="연결", period="연간", **_):
    data = {("00126380", 2023): (258_935_494, 6_566_976), ("00126380", 2024): (300_870_903, 32_725_961)}
    if (corp_code, year) not in data:
        return {"status": "error", "code": "DATA_MISSING", "message": f"{year}년 데이터가 없습니다."}
    rev, op = data[(corp_code, year)]
    return {"status": "ok", "company": "삼성전자", "corp_code": corp_code, "year": year, "basis": basis, "unit": "원", "revenue": rev, "operating_profit": op, "rcept_no": f"R{year}"}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(T, "load_corps", lambda: CORPS)
    monkeypatch.setattr(T, "get_financials", fin)


def test_server_exposes_the_four_tools_with_enum_schemas_and_descriptions():
    ts = {t.name: t for t in tools_list()}
    assert set(ts) == {"resolve_years", "resolve_company", "get_financials", "compute_ratio"}
    assert all(t.description and t.output_schema for t in ts.values())
    gf = ts["get_financials"].input_schema["properties"]
    assert gf["basis"]["enum"] == ["연결", "별도"] and gf["period"]["enum"] == ["연간", "분기", "반기", "월"]
    assert set(ts["compute_ratio"].input_schema["properties"]["metric"]["enum"]) == {"operating_margin", "revenue_growth"}
    assert ts["get_financials"].input_schema["required"] == ["corp_code", "year"]


def test_resolve_years_returns_structured_result_for_a_valid_call():
    r = call("resolve_years", {"kind": "explicit", "values": [2024, 2023]})
    assert not r.is_error and r.structured_content["status"] == "ok" and r.structured_content["years"] == [2023, 2024]


@pytest.mark.parametrize("args, code", [({"kind": "relative", "expr": "올해"}, "YEAR_NOT_PUBLISHED"), ({"kind": "explicit", "values": [2010]}, "YEAR_OUT_OF_RANGE"),
                                        ({"kind": "recent", "n": 11}, "TOO_MANY_YEARS"), ({"kind": "explicit"}, "INVALID_YEAR_EXPR")])
def test_business_errors_come_back_as_structured_results_not_protocol_errors(args, code):
    r = call("resolve_years", args)
    assert not r.is_error and r.structured_content["status"] == "error" and r.structured_content["code"] == code and r.structured_content["message"]


@pytest.mark.parametrize("name, args", [("get_financials", {"corp_code": "00126380", "year": 2024, "basis": "CFS"}),          # 열거형 위반
                                        ("get_financials", {"corp_code": "00126380", "year": "2024년"}),                         # 타입 위반
                                        ("get_financials", {"year": 2024}),                                                      # 필수 인자 누락
                                        ("compute_ratio", {"metric": "sharpe", "corp_code": "00126380", "year": 2024}),
                                        ("resolve_years", {"kind": "bogus"})])
def test_malformed_arguments_are_rejected_at_the_protocol_level(name, args):
    r = call(name, args)
    assert r.is_error and "validation" in r.content[0].text.lower()


def test_quarter_request_is_unsupported_without_touching_opendart():
    r = call("get_financials", {"corp_code": "00126380", "year": 2024, "period": "분기"})        # fixture 없이도 네트워크를 쓰지 않는다
    assert r.structured_content["status"] == "unsupported" and r.structured_content["code"] == "UNSUPPORTED_PERIOD"


def test_resolve_company_confirms_famous_alias_and_never_uses_ai_suggestions(offline, monkeypatch):
    real, seen = T.resolve_company, []

    def spy(name, *a, **k):          # MCP 서버가 AI 제안(suggest)을 켜지 않고 호출하는지 기록한다
        seen.append(k.get("suggest", "기본값(AI 제안 사용)"))
        return real(name, *a, **k)
    monkeypatch.setattr(T, "resolve_company", spy)
    r = call("resolve_company", {"name": "삼전"})
    s = r.structured_content
    assert s["status"] == "ok" and s["company"] == "삼성전자" and s["corp_code"] == "00126380" and s["resolved_by"] == "유명 별칭"
    r = call("resolve_company", {"name": "포스코"})
    assert r.structured_content["status"] == "candidates" and r.structured_content["candidates"][0]["name"] == "POSCO홀딩스"
    r = call("resolve_company", {"name": "전혀없는회사명"})
    assert r.structured_content["status"] == "error" and r.structured_content["code"] == "COMPANY_NOT_FOUND"
    assert seen == [None, None, None]


def test_compute_ratio_does_the_needed_lookups_itself(offline):
    r = call("compute_ratio", {"metric": "operating_margin", "corp_code": "00126380", "year": 2024}).structured_content
    assert r["status"] == "ok" and r["value_pct"] == pytest.approx(10.88, abs=0.01) and r["basis"] == "연결"
    g = call("compute_ratio", {"metric": "revenue_growth", "corp_code": "00126380", "year": 2024}).structured_content
    assert g["status"] == "ok" and g["value_pct"] == pytest.approx(16.20, abs=0.01)             # 전년도(2023)를 서버가 조회해서 계산


def test_compute_ratio_passes_lookup_failures_through(offline):
    r = call("compute_ratio", {"metric": "revenue_growth", "corp_code": "00126380", "year": 2023}).structured_content     # 2022 데이터 없음
    assert r["status"] == "error" and r["code"] == "DATA_MISSING"
    q = call("compute_ratio", {"metric": "operating_margin", "corp_code": "00126380", "year": 2099}).structured_content
    assert q["status"] == "error"


def test_server_describes_its_scope_and_limits():
    async def go():
        async with Client(mcp_server.mcp) as c:
            return c.instructions
    text = asyncio.run(go()) or ""
    assert "연결" in text and "분기" in text and "투자" in text
