"""FinPilot 금융 도구를 MCP 서버로 제공한다. 실행: python mcp_server.py  (stdio)

MCP 클라이언트(예: Claude Desktop, MCP Inspector, 자체 클라이언트)가 이 서버의 도구를 발견하고 호출할 수 있다.
도구는 tools.py와 같은 함수를 쓰고, 입력 검증과 오류 반환(status/code/message)도 같다.
- 이 서버에는 LLM이 없다. 회사 확정은 코드(정확 일치·유명 별칭·초성·우선주·영문명)만 쓰고 AI 제안은 쓰지 않는다.
- 에이전트(agent_core.py)의 근거 인용 검사·호출 한도·답변 조립은 에이전트 쪽 보호 장치라서 여기에는 없다. 서버는 값의 범위·형식·기준을 검증한다.
- 서버는 상태가 없다. 호출마다 OpenDART를 조회한다(캐시 없음).
"""
from typing import Any, Literal, Optional

from mcp.server.mcpserver import MCPServer

import tools as T

mcp = MCPServer(
    "finpilot",
    instructions=("한국 상장사의 연간(사업보고서) 매출액·영업이익을 OpenDART에서 조회하고 영업이익률·매출 성장률을 계산한다. "
                  "기본은 연결재무제표이고 분기·반기·월은 지원하지 않는다. 회사는 resolve_company로 먼저 확정하고 그 corp_code를 쓴다. "
                  "모든 도구는 예외 대신 status(ok/candidates/unsupported/error)와 사용자용 message를 돌려준다. 투자 판단·예측은 하지 않는다."),
)


@mcp.tool(structured_output=True)
def resolve_years(kind: Literal["explicit", "range", "relative", "recent"], values: Optional[list[int]] = None, start: Optional[int] = None,
                  end: Optional[int] = None, expr: Optional[Literal["올해", "작년", "재작년"]] = None, n: Optional[int] = None) -> dict[str, Any]:
    """연도 표현을 사업연도 목록으로 바꾼다(오늘 날짜 기준). kind: explicit(values) / range(start,end) / relative(expr) / recent(n=최근 n년).
    올해·미래 연도는 아직 공시 전이라 오류와 가장 최근 공시 연도(latest_published_year)를 돌려준다. 한 번에 최대 10개 연도."""
    expr_dict = {"kind": kind, **{k: v for k, v in dict(values=values, start=start, end=end, expr=expr, n=n).items() if v is not None}}
    return T.resolve_years(expr_dict)


@mcp.tool(structured_output=True)
def resolve_company(name: str) -> dict[str, Any]:
    """상장사명을 확정한다. 정확히 일치하거나 유명 별칭·초성(삼전, 닉스, 네이버 등)이면 status=ok와 corp_code를 준다.
    모호하면 status=candidates와 후보 목록(사용자가 고르게 해야 함), 해외·비상장은 unsupported, 못 찾으면 error."""
    return T.resolve_company(name, suggest=None)


@mcp.tool(structured_output=True)
def get_financials(corp_code: str, year: int, basis: Literal["연결", "별도"] = "연결", period: Literal["연간", "분기", "반기", "월"] = "연간") -> dict[str, Any]:
    """확정된 회사(corp_code)의 연간 매출액·영업이익(원 단위 정수)을 조회한다. 같은 연도 보고서가 여럿이면 OpenDART가 주는 최신 정정본이고
    접수번호·접수일·정정 여부를 함께 준다. period가 연간이 아니면 조회하지 않고 unsupported를 돌려준다."""
    return T.get_financials(corp_code, year, basis, period)


@mcp.tool(structured_output=True)
def compute_ratio(metric: Literal["operating_margin", "revenue_growth"], corp_code: str, year: int, basis: Literal["연결", "별도"] = "연결") -> dict[str, Any]:
    """영업이익률(operating_margin = 영업이익 ÷ 매출액 × 100) 또는 매출 성장률(revenue_growth = (당기−전기) ÷ 전기 × 100)을 계산한다.
    필요한 조회(성장률은 전년도 포함)는 내부에서 한다. 분모가 0 이하이거나 기준·연도가 다르면 계산하지 않고 이유를 돌려준다."""
    cur = T.get_financials(corp_code, year, basis, "연간")
    if cur.get("status") != "ok":
        return cur
    prev = None
    if metric == "revenue_growth":
        prev = T.get_financials(corp_code, year - 1, basis, "연간")
        if prev.get("status") != "ok":
            return prev
    return T.compute_ratio(metric, cur, prev)


if __name__ == "__main__":
    mcp.run(transport="stdio")
