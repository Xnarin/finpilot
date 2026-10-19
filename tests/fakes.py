"""에이전트 테스트용 가짜 LLM(정해 둔 응답을 순서대로 돌려준다)과 가짜 외부 호출."""
import itertools
from datetime import date
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

import tools as T
from agent_core import Deps

_ids = itertools.count(1)


def call(tool_name, /, **args):
    return {"name": tool_name, "args": args, "id": f"c{next(_ids)}", "type": "tool_call"}


def ai(*calls, text=""):
    return AIMessage(content=text, tool_calls=list(calls))


class ScriptedChat(BaseChatModel):
    """script의 AIMessage(또는 예외)를 호출 순서대로 돌려준다. seen에는 모델이 받은 메시지를 기록한다."""
    script: list[Any] = Field(default_factory=list)
    seen: list[Any] = Field(default_factory=list)
    idx: int = 0

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        if self.idx >= len(self.script):
            raise AssertionError("스크립트에 남은 응답이 없습니다(에이전트가 예상보다 많이 호출했습니다).")
        item = self.script[self.idx]
        self.idx += 1
        if isinstance(item, Exception):
            raise item
        return ChatResult(generations=[ChatGeneration(message=item)])


FIN = {"1": ("삼성전자", {2023: (258_935_494, 6_566_976), 2024: (300_870_903, 32_725_961)}),
       "2": ("SK하이닉스", {2023: (32_765_719, -7_730_313), 2024: (66_192_960, 23_467_319)})}


def fake_resolve_company(name):
    n = name.replace(" ", "")
    if n in ("삼전", "삼성전자"):
        return {"status": "ok", "company": "삼성전자", "corp_code": "1", "stock_code": "005930", "resolved_by": "유명 별칭" if n == "삼전" else "정확 일치",
                "note": "'삼전'을(를) 삼성전자(으)로 해석했습니다." if n == "삼전" else None}
    if n in ("닉스", "SK하이닉스"):
        return {"status": "ok", "company": "SK하이닉스", "corp_code": "2", "stock_code": "000660", "resolved_by": "유명 별칭", "note": f"'{n}'을(를) SK하이닉스(으)로 해석했습니다."}
    if n == "포스코":
        return {"status": "candidates", "reason": "NOT_FOUND", "message": "후보", "candidates": [{"name": "POSCO홀딩스", "stock_code": "005490", "source": "별칭 사전"}]}
    if n == "애플":
        return {"status": "unsupported", "code": "COMPANY_NOT_SUPPORTED", "message": "'애플'은(는) 해외 기업으로 보여 OpenDART 상장사 공시로 조회할 수 없습니다."}
    return {"status": "error", "code": "COMPANY_NOT_FOUND", "message": f"상장사 '{name}'을(를) 찾지 못했습니다."}


class FakeFinancials:
    def __init__(self):
        self.calls = []

    def __call__(self, corp_code, year, basis="연결", period="연간", today=None, **kw):
        self.calls.append((corp_code, year, basis, period))
        if period != "연간":
            return {"status": "unsupported", "code": "UNSUPPORTED_PERIOD", "message": "분기·반기·월 단위 조회는 아직 지원하지 않습니다."}
        name, by_year = FIN[corp_code]
        if year not in by_year:
            return {"status": "error", "code": "DATA_MISSING", "message": f"{name} {year}년 {basis} 사업보고서 데이터가 없습니다."}
        rev, op = by_year[year]
        return {"status": "ok", "company": name, "corp_code": corp_code, "year": year, "basis": basis, "unit": "원", "revenue": rev, "operating_profit": op,
                "rcept_no": f"R{corp_code}{year}", "fetched_at": "t", "report_name": "사업보고서", "rcept_date": f"{year + 1}0315", "is_amended": False, "meta_available": True}


def deps(max_calls=40, max_requests=10, fin=None):
    fin = fin or FakeFinancials()
    d = Deps(resolve_company=fake_resolve_company, get_financials=fin, today=lambda: date(2026, 10, 19), max_calls=max_calls, max_requests=max_requests)
    d.fin = fin
    return d
