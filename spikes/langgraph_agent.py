"""스파이크(2026-10-19): 설계 확인용 일회성 시험 스크립트. 실행에는 requirements.txt 외에 langgraph, langchain, langchain-google-genai가 필요하다(아직 requirements.txt에 넣지 않음). Gemini와 OpenDART를 실제로 호출한다."""
import json, os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LANGSMITH_TRACING"] = "false"
from dart import load_env
load_env()

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver

import tools as T

LOG = []          # tool_log: 평가용 호출 기록
_cache = {}


def logged(name, args, result):
    LOG.append({"tool": name, "args": args, "status": result.get("status") if isinstance(result, dict) else "?", "code": result.get("code") if isinstance(result, dict) else None})
    return result


@tool
def resolve_years(kind: str, values: list[int] | None = None, start: int | None = None, end: int | None = None, expr: str | None = None, n: int | None = None) -> dict:
    """연도 표현을 사업연도 목록으로 바꾼다. kind: explicit(values) / range(start,end) / relative(expr: 올해·작년·재작년) / recent(n)."""
    e = {"kind": kind, **{k: v for k, v in dict(values=values, start=start, end=end, expr=expr, n=n).items() if v is not None}}
    return logged("resolve_years", e, T.resolve_years(e))


@tool
def resolve_company(name: str) -> dict:
    """회사명을 확정한다. status가 candidates면 사용자에게 후보를 보여 줘야 하고, unsupported면 조회할 수 없는 회사다."""
    return logged("resolve_company", {"name": name}, T.resolve_company(name))


@tool
def get_financials(corp_code: str, year: int, basis: str = "연결", period: str = "연간") -> dict:
    """확정된 회사(corp_code)의 연간 매출액·영업이익을 조회한다. period는 연간만 지원."""
    key = (corp_code, year, basis, period)
    if key not in _cache:
        _cache[key] = T.get_financials(corp_code, year, basis, period)
    return logged("get_financials", {"corp_code": corp_code, "year": year, "basis": basis, "period": period}, _cache[key])


@tool
def compute_ratio(metric: str, corp_code: str, year: int, basis: str = "연결") -> dict:
    """영업이익률(operating_margin) 또는 매출 성장률(revenue_growth)을 계산한다. 필요한 조회는 내부에서 처리한다."""
    cur = _cache.setdefault((corp_code, year, basis, "연간"), T.get_financials(corp_code, year, basis, "연간"))
    if cur.get("status") != "ok":
        return logged("compute_ratio", {"metric": metric, "corp_code": corp_code, "year": year}, cur)
    prev = None
    if metric == "revenue_growth":
        prev = _cache.setdefault((corp_code, year - 1, basis, "연간"), T.get_financials(corp_code, year - 1, basis, "연간"))
        if prev.get("status") != "ok":
            return logged("compute_ratio", {"metric": metric, "corp_code": corp_code, "year": year}, prev)
    return logged("compute_ratio", {"metric": metric, "corp_code": corp_code, "year": year}, T.compute_ratio(metric, cur, prev))


@tool
def ask_user(missing: list[str]) -> str:
    """사용자에게 되물어야 할 때 호출한다. missing은 company(회사)·year(연도)·task(작업)·candidate(후보 선택) 중 빠진 항목들. 질문 문구는 코드가 만든다."""
    LOG.append({"tool": "ask_user", "args": {"missing": missing}, "status": "ask", "code": None})
    return "질문이 사용자에게 전달된다. 이 턴을 끝내라."


@tool
def decline(reason: str) -> str:
    """지원하지 않는 요청을 거절할 때 호출한다. reason: OFF_TOPIC·INVESTMENT_ADVICE·PRICE_FORECAST·UNSUPPORTED_METRIC·UNSUPPORTED_PERIOD. 문구는 코드가 만든다."""
    LOG.append({"tool": "decline", "args": {"reason": reason}, "status": "decline", "code": None})
    return "거절 안내가 사용자에게 전달된다. 이 턴을 끝내라."


SYSTEM = """너는 한국 상장사의 연간 재무(매출액·영업이익·영업이익률·매출 성장률)를 조회하는 도우미다.
- 숫자는 반드시 도구 결과로만 안다. 도구 결과에 없는 숫자를 만들지 마라.
- 연도는 직접 계산하지 말고 resolve_years에 표현만 넘겨라. 회사는 resolve_company로 먼저 확정하고 그 corp_code만 써라.
- 회사·연도·작업 중 빠진 것이 있으면 한 번에 모아 ask_user를 호출한다. 후보가 여러 개이면 ask_user(candidate)를 호출한다.
- 분기·월 단위, 투자 판단, 주가 예측, 연간 재무와 무관한 요청은 decline을 호출한다.
- 이전 대화의 회사·연도·작업을 이어받을 수 있다.
- 최종 문장에는 숫자를 쓰지 마라(숫자와 표는 코드가 붙인다). 한두 문장으로 요약만 한다."""

llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", temperature=0, google_api_key=os.environ["GEMINI_API_KEY"])
agent = create_agent(llm, tools=[resolve_years, resolve_company, get_financials, compute_ratio, ask_user, decline], system_prompt=SYSTEM, checkpointer=InMemorySaver())


def run(label, turns):
    tid = str(uuid.uuid4())
    for t in turns:
        LOG.clear()
        t0 = time.perf_counter()
        try:
            out = agent.invoke({"messages": [{"role": "user", "content": t}]}, config={"configurable": {"thread_id": tid}, "recursion_limit": 25})
            last = out["messages"][-1]
            text = last.content if isinstance(last.content, str) else str(last.content)
        except Exception as e:
            text = f"ERROR {type(e).__name__}: {str(e)[:200]}"
        ms = (time.perf_counter() - t0) * 1000
        print(f"[{label}] 사용자: {t}")
        for c in LOG:
            print("    -", c["tool"], json.dumps(c["args"], ensure_ascii=False), "->", c["status"], c["code"] or "")
        print(f"    답변문장: {text[:120]!r} | 도구 호출 {len(LOG)}회 | {ms:.0f}ms")


if __name__ == "__main__":
    run("S1 복수·유명별칭", ["삼전이랑 닉스 2024년 영업이익률 알려줘"])
    run("S2 되묻고 이어가기", ["삼성전자 영업이익률 알려줘", "2024"])
    run("S3 분기", ["삼성전자 2024년 1분기 영업이익 알려줘"])
    run("S4 올해", ["삼성전자 올해 영업이익률은?"])
    run("S5 해외", ["애플 2024년 영업이익 알려줘"])
    run("S6 후속질문", ["SK하이닉스 2024년 매출 성장률", "그럼 삼성전자는?"])
