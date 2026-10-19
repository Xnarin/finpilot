"""챗봇형 에이전트(LangGraph). 설계: docs/backlog/agent_design.md

LLM은 도구를 골라 호출하지만, 도구 실행·검증·한도·답변 조립은 모두 코드가 한다.
- 숫자·표·되묻기·거절 문구는 코드가 만든다. LLM의 설명 문장은 숫자가 하나라도 있으면 버린다.
- 사용자가 말하지 않은 값(연도·회사·별도·분기)은 근거 인용(evidence) 검사로 거부한다.
"""
import json
import operator
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Callable, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ValidationError

import tools as T

MODEL = "gemini-3.5-flash-lite"
MAX_REQUESTS = 10     # 한 질문(턴)당 회사×연도 요청 수
MAX_CALLS = 40        # 한 질문(턴)당 도구 호출 수
MAX_GUARD_HITS = 4    # 한 질문에서 검증 오류가 이만큼 쌓이면 LLM이 헛돌고 있다고 보고 되묻는다
HISTORY_TURNS = 12    # 모델에 전달하는 최근 사용자 턴 수(자세한 길이는 추후 조정)

SYSTEM = """너는 한국 상장사의 연간 재무(매출액·영업이익·영업이익률·매출 성장률)를 조회하는 챗봇이다.
규칙:
1. 숫자는 도구 결과로만 안다. 숫자를 지어내지 마라. 최종 답변 문장에는 숫자를 하나도 쓰지 마라(숫자와 표는 코드가 붙인다). 한두 문장으로 요약만 한다.
2. 사용자가 말한 값만 쓴다. 회사·연도·작업 중 사용자가 말하지 않은 것을 추측하거나 다른 값으로 바꾸지 마라. 빠진 것이 있으면 한 번에 모아 ask_user를 호출한다.
3. 회사는 resolve_company로 먼저 확정하고 그 corp_code만 쓴다. 연도는 직접 계산하지 말고 resolve_years에 표현만 넘긴다. evidence에는 사용자 문장에서 그대로 인용한 부분을 적는다.
4. 후보(candidates)가 나오면 ask_user(candidate)로 사용자에게 고르게 한다. 도구가 unsupported·error를 돌려주면 다른 값으로 바꿔 다시 시도하지 말고 그 결과를 따른다.
5. 분기·반기·월 단위, 투자 판단·추천, 주가·실적 예측, 연간 재무와 무관한 요청은 decline을 호출한다.
6. 이전 대화에서 사용자가 말한 회사·연도·작업은 이어받을 수 있다(예: "그럼 삼성전자는?").
7. 일부 요청만 확정되고 나머지가 불확실하면(예: 한 회사는 확정, 다른 회사는 후보), 확정된 요청의 조회·계산을 먼저 모두 끝낸 뒤 마지막에 ask_user를 호출한다.
8. 통화 환산·단위 변환(달러 등) 요청은 decline(UNSUPPORTED_METRIC)을 호출한다. 사용자가 어떤 지표를 원하는지 말하지 않았으면(예: "삼성전자 2024") 지표를 정해서 조회하지 말고 ask_user(task)를 호출한다.
9. 사용자가 실적·매출·영업이익을 말하면 그것이 지표를 말한 것이다(get_financials로 조회). 이때는 지표를 되묻지 마라.
10. 이전 대화에서 말한 연도·지표를 이어받을 때도 resolve_years를 다시 호출하고, evidence에는 사용자가 그 연도를 말한 표현(예: '2024년')을 이전 대화에서 그대로 인용한다. 이어받을 수 있는 값을 되묻지 마라.
11. 사용자가 말한 모든 회사·연도에 대해 결과를 만들어야 한다. 하나라도 빠뜨리지 마라.
12. 도구 호출은 필요한 만큼만 한다."""

ASK_TEXT = {"company": "어느 회사인지", "year": "어느 사업연도인지", "task": "무엇을 알려 드릴지(실적, 영업이익률, 매출 성장률 중)",
            "basis": "연결/별도 중 어느 기준인지", "candidate": "아래 후보 중 어느 회사인지"}
DECLINE_TEXT = {
    "OFF_TOPIC": "저는 상장사의 연간 재무(매출액·영업이익·영업이익률·매출 성장률) 조회만 도와드릴 수 있어요.",
    "INVESTMENT_ADVICE": "투자 판단이나 추천은 드릴 수 없어요. 대신 연간 실적 숫자는 조회해 드릴 수 있어요.",
    "PRICE_FORECAST": "주가나 실적 예측은 하지 않아요. 공시된 연간 실적은 조회해 드릴 수 있어요.",
    "UNSUPPORTED_METRIC": "지원하는 지표는 매출액, 영업이익, 영업이익률, 매출 성장률이에요.",
    "UNSUPPORTED_PERIOD": "분기·반기·월 단위는 아직 지원하지 않아요. 연간 사업보고서 기준만 조회할 수 있어요.",
}
REL_WORDS = {"올해": ("올해", "금년", "올 "), "작년": ("작년", "지난해", "전년", "지난 해"), "재작년": ("재작년", "그저께")}
TASK_WORDS = {"operating_margin": ("이익률", "이익율", "영업익률", "마진", "이익 비율"),
              "revenue_growth": ("성장", "증가", "늘", "올랐", "올라", "신장", "상승", "변화", "전년 대비", "전년대비", "yoy", "감소", "줄"),
              "level": ("실적", "매출", "영업이익", "영업익", "이익", "수익", "재무", "벌었", "벌어", "돈", "손실", "손익", "적자", "흑자")}
GUARD_PREFIX = "GUARD_"   # LLM에게만 돌려주고 사용자에게는 보여 주지 않는 검증 오류


# ---------------------------------------------------------------- 도구 스키마(LLM에 보여 주는 인자 형식)
class ResolveYearsArgs(BaseModel):
    kind: Literal["explicit", "range", "relative", "recent"]
    evidence: str
    values: Optional[list[int]] = None
    start: Optional[int] = None
    end: Optional[int] = None
    expr: Optional[Literal["올해", "작년", "재작년"]] = None
    n: Optional[int] = None


class ResolveCompanyArgs(BaseModel):
    name: str
    evidence: str


class GetFinancialsArgs(BaseModel):
    corp_code: str
    year: int
    basis: Literal["연결", "별도"] = "연결"
    period: Literal["연간", "분기", "반기", "월"] = "연간"


class ComputeRatioArgs(BaseModel):
    metric: Literal["operating_margin", "revenue_growth"]
    corp_code: str
    year: int
    basis: Literal["연결", "별도"] = "연결"


class AskUserArgs(BaseModel):
    missing: list[Literal["company", "year", "task", "basis", "candidate"]]


class DeclineArgs(BaseModel):
    reason: Literal["OFF_TOPIC", "INVESTMENT_ADVICE", "PRICE_FORECAST", "UNSUPPORTED_METRIC", "UNSUPPORTED_PERIOD"]


SPECS = {
    "resolve_years": (ResolveYearsArgs, "연도 표현을 사업연도 목록으로 바꾼다. kind: explicit(values) / range(start,end) / relative(expr: 올해·작년·재작년) / recent(n=최근 n년). evidence는 사용자 문장에서 그대로 인용한 연도 표현."),
    "resolve_company": (ResolveCompanyArgs, "회사명을 확정한다. status=ok면 corp_code를 쓰고, candidates면 사용자에게 고르게 하고(ask_user candidate), unsupported면 조회할 수 없는 회사다. evidence는 사용자 문장에서 그대로 인용한 회사 표현."),
    "get_financials": (GetFinancialsArgs, "확정된 회사(corp_code)의 연간 매출액·영업이익을 조회한다. year는 resolve_years가 준 값만 쓴다. basis 별도·period 분기는 사용자가 말한 경우에만."),
    "compute_ratio": (ComputeRatioArgs, "영업이익률(operating_margin) 또는 매출 성장률(revenue_growth)을 계산한다. 필요한 조회는 내부에서 처리한다."),
    "ask_user": (AskUserArgs, "사용자에게 되물어야 할 때 호출한다. missing에 빠진 항목을 모두 모아 넣는다(company·year·task·basis·candidate). 질문 문구는 코드가 만든다."),
    "decline": (DeclineArgs, "지원하지 않는 요청을 거절한다. 문구는 코드가 만든다."),
}
TOOL_SPECS = [StructuredTool.from_function(func=lambda **kw: "", name=n, description=d, args_schema=m) for n, (m, d) in SPECS.items()]


# ---------------------------------------------------------------- 상태
class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    tool_log: Annotated[list, operator.add]   # 대화 전체의 도구 호출 기록(평가·실행 기록 화면용)
    cache: dict                               # (도구, 인자) -> 결과, 같은 호출은 재사용
    resolved: dict                            # corp_code -> 이 대화에서 확정된 회사 정보
    years_ok: list                            # resolve_years가 돌려준 연도(이것만 get_financials에 허용)
    candidates: list                          # 마지막 회사 후보(사용자 선택 대기)
    turn: dict                                # 이번 질문의 카운터·플래그
    reply: dict                               # 이번 질문의 응답(표·되묻기·안내)


@dataclass
class Deps:
    """외부 호출(OpenDART·날짜)을 바꿔 끼우는 지점. 테스트에서는 가짜를 넣는다."""
    resolve_years: Callable = T.resolve_years
    resolve_company: Callable = T.resolve_company
    get_financials: Callable = T.get_financials
    compute_ratio: Callable = T.compute_ratio
    today: Callable = date.today
    max_calls: int = MAX_CALLS
    max_requests: int = MAX_REQUESTS


def _norm(s):
    return re.sub(r"\s+", "", str(s)).casefold()


def _user_texts(messages):
    return [m.content if isinstance(m.content, str) else str(m.content) for m in messages if isinstance(m, HumanMessage)]


def _ai_text(msg):
    c = msg.content
    if isinstance(c, str):
        return c
    return "".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text") if isinstance(c, list) else str(c)


def _guard(code, message):
    return {"status": "error", "code": GUARD_PREFIX + code, "message": message}


# ---------------------------------------------------------------- 도구 실행(검증·한도·캐시·기록)
class Runner:
    def __init__(self, deps, state):
        self.d, self.s = deps, state
        self.cache = dict(state.get("cache") or {})
        self.resolved = dict(state.get("resolved") or {})
        self.years_ok = list(state.get("years_ok") or [])
        self.candidates = list(state.get("candidates") or [])
        self.turn = dict(state["turn"])
        self.user_all = [_norm(t) for t in _user_texts(state["messages"])]
        self.user_now = _norm(self.turn["user_text"])
        self.log = []

    # -- 근거 인용 검사
    def _evidence_ok(self, ev):
        e = _norm(ev or "")
        return bool(e) and any(e in t for t in self.user_all), bool(e) and e in self.user_now

    def _year_evidence_fits(self, a):
        """인용(evidence)이 말한 연도 표현과 실제로 맞는지: 연도 숫자, 상대 연도 단어, '최근'이 인용에 들어 있어야 한다."""
        ev, k = _norm(a["evidence"]), a["kind"]

        def has_year(y):
            y = str(y)
            return y in ev or (y[2:] in ev and "년" in ev)
        if k == "explicit":
            return bool(a.get("values")) and all(has_year(v) for v in a["values"])
        if k == "range":
            return a.get("start") is not None and a.get("end") is not None and has_year(a["start"]) and has_year(a["end"])
        if k == "relative":
            return any(_norm(w) in ev for w in REL_WORDS.get(a.get("expr"), ()))
        if k == "recent":
            return "최근" in ev or "지난" in ev
        return False

    def _task_said(self, metric):
        return self._said(TASK_WORDS["level" if metric is None else metric])

    def _said(self, words):
        return any(_norm(w) in t for t in self.user_all for w in words)

    def call(self, name, raw_args):
        t0 = time.perf_counter()
        self.turn["calls"] += 1
        if self.turn["calls"] > self.d.max_calls:
            self.turn["limit_hit"] = True
            res = {"status": "error", "code": "CALL_LIMIT", "message": f"한 번에 처리할 수 있는 도구 호출({self.d.max_calls}회)을 넘었어요. 요청을 줄여 다시 물어봐 주세요."}
            return self._finish(name, raw_args, res, t0, False, False)
        spec = SPECS.get(name)
        if not spec:
            return self._finish(name, raw_args, _guard("UNKNOWN_TOOL", f"알 수 없는 도구입니다: {name}"), t0, False, False)
        try:
            args = spec[0](**(raw_args or {}))
        except ValidationError as e:
            allowed = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:4])
            return self._finish(name, raw_args, _guard("INVALID_ARGS", f"인자 형식이 올바르지 않습니다 ({allowed})."), t0, False, False)
        a = args.model_dump(exclude_none=True)
        cached = False
        inherited = False
        key = json.dumps([name, a], ensure_ascii=False, sort_keys=True)
        if name in ("ask_user", "decline"):
            res = self._pseudo(name, a)
        elif key in self.cache:
            res, cached = self.cache[key], True
        else:
            res = getattr(self, "_" + name)(a)
            if res.get("status") in ("ok", "candidates", "unsupported") or (
                    res.get("status") == "error" and not str(res.get("code", "")).startswith(GUARD_PREFIX) and res.get("code") not in ("NETWORK_ERROR", "API_ERROR")):
                self.cache[key] = res
        if name in ("resolve_years", "resolve_company") and a.get("evidence"):
            any_ok, now_ok = self._evidence_ok(a["evidence"])
            inherited = any_ok and not now_ok
        return self._finish(name, a, res, t0, cached, inherited)

    def _finish(self, name, args, res, t0, cached, inherited):
        if str(res.get("code", "")).startswith(GUARD_PREFIX):
            self.turn["guard_hits"] = self.turn.get("guard_hits", 0) + 1
        self.log.append({"turn": self.turn["n"], "tool": name, "args": args, "status": res.get("status"), "code": res.get("code"), "cached": cached,
                         "inherited": inherited, "ms": round((time.perf_counter() - t0) * 1000, 1), "result": res})
        return res

    # -- 개별 도구
    def _resolve_years(self, a):
        any_ok, _ = self._evidence_ok(a["evidence"])
        if not any_ok:
            return _guard("NO_EVIDENCE", "evidence가 사용자 문장에 없습니다. 사용자가 말하지 않은 연도를 추측하지 말고 ask_user(year)로 물어보세요.")
        if not self._year_evidence_fits(a):
            return _guard("BAD_EVIDENCE", "evidence가 연도 표현과 맞지 않습니다. 사용자 문장에서 연도를 말한 부분(예: '2024년', '작년', '최근 3년')을 그대로 인용하세요. 사용자가 연도를 말하지 않았다면 ask_user(year)를 호출하세요.")
        expr = {"kind": a["kind"]}
        for k in ("values", "start", "end", "expr", "n"):
            if k in a:
                expr[k] = a[k]
        res = self.d.resolve_years(expr, today=self.d.today())
        if res.get("status") == "ok":
            self.years_ok = sorted(set(self.years_ok) | set(res["years"]))
        return res

    def _resolve_company(self, a):
        any_ok, _ = self._evidence_ok(a["evidence"])
        if not any_ok:
            return _guard("NO_EVIDENCE", "evidence가 사용자 문장에 없습니다. 사용자가 말하지 않은 회사를 추측하지 말고 ask_user(company)로 물어보세요.")
        n, e = _norm(a["name"]), _norm(a["evidence"])
        picked = a["name"] in {c["name"] for c in self.candidates}      # 직전에 보여 준 후보 중 하나를 사용자가 고른 경우("1번", "첫 번째")
        if n not in e and e not in n and not picked:
            return _guard("NAME_EVIDENCE_MISMATCH", "name은 사용자가 쓴 표현 그대로여야 합니다(evidence와 같은 말). 별칭을 정식 이름으로 바꾸지 마세요.")
        res = self.d.resolve_company(a["name"])
        if res.get("status") == "ok":
            self.resolved[res["corp_code"]] = {k: res.get(k) for k in ("company", "stock_code", "resolved_by", "note")}
            self.candidates = []
        elif res.get("status") == "candidates":
            self.candidates = res["candidates"]
        return res

    def _check_company_year(self, a):
        if a["corp_code"] not in self.resolved:
            return _guard("UNRESOLVED_COMPANY", "이 대화에서 resolve_company로 확정되지 않은 corp_code입니다. 먼저 회사를 확정하세요.")
        if a["year"] not in self.years_ok:
            return _guard("YEAR_NOT_RESOLVED", "resolve_years가 돌려주지 않은 연도입니다. 먼저 resolve_years로 연도를 확정하세요(사용자가 말한 연도만).")
        if a.get("basis") == "별도" and not self._said(("별도", "개별")):
            return _guard("BASIS_NOT_REQUESTED", "사용자가 별도 기준을 요청하지 않았습니다. 기본은 연결입니다.")
        if a.get("period", "연간") != "연간" and not self._said(("분기", "반기", "월", "Q", "q")):
            return _guard("PERIOD_NOT_REQUESTED", "사용자가 분기·반기·월 단위를 요청하지 않았습니다. 기본은 연간입니다.")
        metric = a.get("metric")
        if not self._task_said(metric):
            what = "영업이익률" if metric == "operating_margin" else "매출 성장률" if metric == "revenue_growth" else "실적(매출·영업이익)"
            return _guard("TASK_NOT_STATED", f"사용자가 {what}을(를) 말하지 않았습니다. 지표를 추측하지 말고 ask_user(task)로 물어보세요.")
        req = (a["corp_code"], a["year"])
        reqs = self.turn["requests"]
        if req not in [tuple(r) for r in reqs]:
            if len(reqs) >= self.d.max_requests:
                self.turn["limit_hit"] = True
                return {"status": "error", "code": "REQUEST_LIMIT", "message": f"한 번에 처리할 수 있는 요청({self.d.max_requests}개)을 넘었어요. 회사나 연도를 줄여 다시 물어봐 주세요."}
            reqs.append(list(req))
        return None

    def _fetch(self, corp_code, year, basis, period="연간"):
        key = json.dumps(["_fetch", corp_code, year, basis, period], ensure_ascii=False)
        if key in self.cache:
            return self.cache[key]
        res = self.d.get_financials(corp_code, year, basis, period, today=self.d.today())
        if res.get("code") not in ("NETWORK_ERROR", "API_ERROR"):   # 일시 오류는 캐시하지 않아 다시 시도할 수 있게 한다
            self.cache[key] = res
        return res

    def _get_financials(self, a):
        bad = self._check_company_year(a)
        if bad:
            return bad
        res = self._fetch(a["corp_code"], a["year"], a.get("basis", "연결"), a.get("period", "연간"))
        return res

    def _compute_ratio(self, a):
        bad = self._check_company_year(a)
        if bad:
            return bad
        basis = a.get("basis", "연결")
        cur = self._fetch(a["corp_code"], a["year"], basis)
        if cur.get("status") != "ok":
            return cur
        prev = None
        if a["metric"] == "revenue_growth":
            prev = self._fetch(a["corp_code"], a["year"] - 1, basis)
            if prev.get("status") != "ok":
                return prev
        return self.d.compute_ratio(a["metric"], cur, prev)

    def _pseudo(self, name, a):
        if name == "ask_user":
            if "candidate" in a["missing"] and not self.candidates:
                return _guard("NO_CANDIDATES", "보여 줄 후보가 없습니다. 후보를 물으려면 먼저 resolve_company로 후보를 받아야 합니다(회사를 아직 확정하지 않았다면 resolve_company를 호출하세요).")
            self.turn["final"] = {"kind": "ask", "missing": a["missing"]}
        else:
            self.turn["final"] = {"kind": "decline", "reason": a["reason"]}
        return {"status": "ok", "message": "사용자에게 전달됩니다. 이 턴을 끝내세요."}


# ---------------------------------------------------------------- 그래프 노드
def build_graph(llm, deps=None, checkpointer=None):
    deps = deps or Deps()
    bound = llm.bind_tools(TOOL_SPECS)

    def start_turn(state):
        n = len([m for m in state["messages"] if isinstance(m, HumanMessage)])
        return {"turn": {"n": n, "calls": 0, "requests": [], "final": None, "limit_hit": False, "llm_error": None,
                         "user_text": _user_texts(state["messages"])[-1], "log_start": len(state.get("tool_log") or [])}, "reply": None}

    def agent(state):
        msgs = state["messages"]
        humans = [i for i, m in enumerate(msgs) if isinstance(m, HumanMessage)]
        window = msgs[humans[-HISTORY_TURNS]:] if len(humans) > HISTORY_TURNS else msgs
        try:
            ai = bound.invoke([("system", SYSTEM)] + list(window))
        except Exception as e:  # LLM 호출 실패는 사용자에게 알리고 임의 값으로 대체하지 않는다. 예외 문자열은 쓰지 않는다
            turn = dict(state["turn"])
            turn["llm_error"] = type(e).__name__
            return {"turn": turn}
        turn = dict(state["turn"])
        um = getattr(ai, "usage_metadata", None) or {}
        turn["usage"] = {k: turn.get("usage", {}).get(k, 0) + (um.get(k) or 0) for k in ("input_tokens", "output_tokens", "total_tokens")}
        turn["llm_calls"] = turn.get("llm_calls", 0) + 1
        return {"messages": [ai], "turn": turn}

    def route_after_agent(state):
        if state["turn"].get("llm_error"):
            return "finish"
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "finish"

    def tools_node(state):
        runner = Runner(deps, state)
        out = []
        for call in state["messages"][-1].tool_calls:
            res = runner.call(call["name"], call.get("args"))
            slim = {k: v for k, v in res.items() if k != "note" or res.get("status") != "ok"}
            out.append(ToolMessage(content=json.dumps(slim, ensure_ascii=False, default=str), tool_call_id=call["id"], name=call["name"]))
        return {"messages": out, "tool_log": runner.log, "cache": runner.cache, "resolved": runner.resolved, "years_ok": runner.years_ok,
                "candidates": runner.candidates, "turn": runner.turn}

    def route_after_tools(state):
        t = state["turn"]
        if t.get("guard_hits", 0) >= MAX_GUARD_HITS and not t.get("final"):   # 같은 검증 오류를 반복하며 헛돌면 멈추고 사용자에게 되묻는다
            t["gave_up"] = True
            return "finish"
        return "finish" if t.get("final") or (t.get("limit_hit") and t["calls"] > deps.max_calls) else "agent"

    def finish(state):
        return {"reply": build_reply(state)}

    g = StateGraph(State)
    g.add_node("start_turn", start_turn)
    g.add_node("agent", agent)
    g.add_node("tools", tools_node)
    g.add_node("finish", finish)
    g.add_edge(START, "start_turn")
    g.add_edge("start_turn", "agent")
    g.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "finish": "finish"})
    g.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


# ---------------------------------------------------------------- 응답 조립(숫자·표·문구는 코드)
def _row_key(d):
    return (d["corp_code"], d["year"], d["basis"])


def build_reply(state):
    turn = state["turn"]
    entries = (state.get("tool_log") or [])[turn["log_start"]:]
    cache = state.get("cache") or {}
    rows, notices, interp, carried = {}, [], [], []
    for e in entries:
        r = e["result"]
        if e["tool"] == "resolve_company" and r.get("status") == "ok" and r.get("note") and r.get("resolved_by") == "유명 별칭":
            interp.append(r["note"])
        if e["tool"] in ("resolve_years", "resolve_company") and e.get("inherited") and r.get("status") == "ok":
            carried.append(e["args"].get("evidence"))
        if e["tool"] in ("get_financials", "compute_ratio") and r.get("status") == "ok":
            a = e["args"]
            year, basis = a["year"], a.get("basis", "연결")
            cur = cache.get(json.dumps(["_fetch", a["corp_code"], year, basis, "연간"], ensure_ascii=False))
            if cur and cur.get("status") == "ok":
                row = rows.setdefault(_row_key(cur), {"company": cur["company"], "year": year, "basis": basis, "revenue": cur["revenue"],
                                                       "operating_profit": cur["operating_profit"], "rcept_no": cur["rcept_no"], "rcept_date": cur.get("rcept_date"),
                                                       "is_amended": cur.get("is_amended")})
                if e["tool"] == "compute_ratio":
                    row[r["metric"] + "_pct"] = r["value_pct"]
        elif r.get("status") in ("unsupported", "error") and not str(r.get("code", "")).startswith(GUARD_PREFIX):
            label = ""
            a = e["args"]
            if "corp_code" in a:
                label = f"{state.get('resolved', {}).get(a['corp_code'], {}).get('company', '')} {a.get('year', '')}: ".replace("  ", " ")
            msg = label + str(r.get("message", ""))
            if msg not in notices:
                notices.append(msg)
    ask = decline = None
    final = turn.get("final")
    if turn.get("gave_up") and not final:
        ask = {"missing": [], "candidates": [], "text": "질문을 이해하지 못했어요. 회사, 연도, 알고 싶은 지표(실적·영업이익률·매출 성장률)를 함께 알려 주세요."}
    pending = [e["result"]["candidates"] for e in entries if e["tool"] == "resolve_company" and e["result"].get("status") == "candidates"]
    if not final and pending and not ask:   # 후보가 나왔는데 LLM이 되묻지 않고 끝냈으면 코드가 되묻기를 붙인다(조용히 빠뜨리지 않음)
        ask = {"missing": ["candidate"], "candidates": pending[-1], "text": "다음을 알려 주세요: " + ASK_TEXT["candidate"] + "."}
    if final and final["kind"] == "ask":
        missing = list(dict.fromkeys(final["missing"]))
        cands = state.get("candidates") or []
        if "candidate" in missing and not cands:
            missing.remove("candidate")
        parts = [ASK_TEXT[m] for m in missing]
        ask = {"missing": missing, "candidates": cands if "candidate" in missing else [],
               "text": ("다음을 알려 주세요: " + ", ".join(parts) + "." if parts else "조금 더 자세히 알려 주세요.")}
    elif final and final["kind"] == "decline":
        decline = {"reason": final["reason"], "text": DECLINE_TEXT[final["reason"]]}
        if final["reason"] == "OFF_TOPIC" and notices:   # 도구가 이미 이유를 알려 줬으면 일반 거절 문구를 덧붙이지 않는다(결정 16)
            decline = None
    sentence = None
    dropped = False
    msgs = state["messages"]
    if msgs and isinstance(msgs[-1], AIMessage) and not msgs[-1].tool_calls:
        s = _ai_text(msgs[-1]).strip()
        if s and re.search(r"\d", s):
            dropped = True
        elif s:
            sentence = s
    if not final:   # 확정된 회사 중 표도 안내도 없는 회사가 있으면 조용히 빠뜨리지 않고 알린다
        said = " ".join(notices)
        shown = {r["company"] for r in rows.values()}
        for e in entries:
            r = e["result"]
            if e["tool"] == "resolve_company" and r.get("status") == "ok" and r["company"] not in shown and r["company"] not in said:
                msg = f"{r['company']}은(는) 조회 결과를 만들지 못했어요. 다시 물어봐 주세요."
                if msg not in notices:
                    notices.append(msg)
    if turn.get("limit_hit") and not any("한도" in n or "넘었" in n for n in notices):
        notices.append("요청이 한도를 넘어 일부만 처리했어요. 회사나 연도를 줄여 다시 물어봐 주세요.")
    return {"rows": list(rows.values()), "notices": notices, "ask": ask, "decline": decline, "sentence": sentence, "sentence_dropped_for_digits": dropped,
            "interpretations": list(dict.fromkeys(interp)), "carried": list(dict.fromkeys(c for c in carried if c)), "limit_hit": turn.get("limit_hit", False),
            "llm_error": turn.get("llm_error"), "calls": turn["calls"], "llm_calls": turn.get("llm_calls", 0), "usage": turn.get("usage", {}), "tool_log": [{k: v for k, v in e.items() if k != "result"} for e in entries]}


def make_llm(model=MODEL):
    import os
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=model, temperature=0, google_api_key=os.environ["GEMINI_API_KEY"])


def chat(graph, thread_id, text):
    from langgraph.errors import GraphRecursionError
    try:
        out = graph.invoke({"messages": [HumanMessage(text)]}, config={"configurable": {"thread_id": thread_id}, "recursion_limit": 60})
    except GraphRecursionError:   # 어떤 이유로든 도구 루프가 끝나지 않으면 예외를 그대로 내지 않고 안내한다
        return {"rows": [], "notices": [], "ask": {"missing": [], "candidates": [], "text": "질문을 처리하지 못했어요. 회사, 연도, 알고 싶은 지표를 다시 알려 주세요."}, "decline": None,
                "sentence": None, "sentence_dropped_for_digits": False, "interpretations": [], "carried": [], "limit_hit": False, "llm_error": "GraphRecursionError",
                "calls": 0, "llm_calls": 0, "usage": {}, "tool_log": []}
    return out["reply"]
