"""MCP 서버를 실제 별도 프로세스(stdio)로 띄우고 MCP 클라이언트로 호출하는 테스트. DART_API_KEY 필요(기본 `pytest`에는 포함되지 않음)."""
import asyncio
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parent.parent
PARAMS = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server.py")], cwd=ROOT)


def session(fn):
    async def go():
        async with Client(PARAMS) as c:
            return await fn(c)
    return asyncio.run(go())


def test_separate_process_server_lists_tools_and_returns_real_verified_values():
    async def scenario(c):
        names = [t.name for t in (await c.list_tools()).tools]
        who = (await c.call_tool("resolve_company", {"name": "삼전"})).structured_content
        fin = (await c.call_tool("get_financials", {"corp_code": who["corp_code"], "year": 2024})).structured_content
        ratio = (await c.call_tool("compute_ratio", {"metric": "operating_margin", "corp_code": who["corp_code"], "year": 2024})).structured_content
        bad = await c.call_tool("get_financials", {"corp_code": who["corp_code"], "year": 2024, "basis": "CFS"})
        quarter = (await c.call_tool("get_financials", {"corp_code": who["corp_code"], "year": 2024, "period": "분기"})).structured_content
        return names, who, fin, ratio, bad, quarter
    names, who, fin, ratio, bad, quarter = session(scenario)
    assert names == ["resolve_years", "resolve_company", "get_financials", "compute_ratio"]
    assert who["status"] == "ok" and who["company"] == "삼성전자" and who["resolved_by"] == "유명 별칭"
    # 사용자가 DART 원문과 대조한 값(삼성전자 2024)
    assert (fin["revenue"], fin["operating_profit"], fin["rcept_no"]) == (300_870_903_000_000, 32_725_961_000_000, "20250311001085")
    assert ratio["value_pct"] == pytest.approx(10.88, abs=0.01)
    assert bad.is_error                                                         # 열거형 위반은 프로토콜 오류
    assert quarter["status"] == "unsupported" and quarter["code"] == "UNSUPPORTED_PERIOD"


def test_separate_process_server_handles_unsupported_and_not_found_companies():
    async def scenario(c):
        return [(await c.call_tool("resolve_company", {"name": n})).structured_content for n in ("삼성물산", "포스코", "없는회사이름xyz")]
    same_name, ambiguous, missing = session(scenario)
    assert same_name["status"] == "ok" and same_name["stock_code"] == "028260"      # 같은 이름 중 현재 상장 법인(삼성물산)
    assert ambiguous["status"] == "candidates" and ambiguous["candidates"][0]["name"] == "POSCO홀딩스"
    assert missing["status"] in ("error", "candidates")
