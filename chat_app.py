"""챗봇형 화면: streamlit run chat_app.py   (설계: docs/backlog/agent_design.md)

대화는 화면 세션 메모리에만 보관한다(새로고침하면 사라짐). 숫자·표·되묻기·거절 문구는 코드가 만들고, LLM은 도구 선택과 짧은 설명 문장만 맡는다.
화면은 질문을 제목으로, 그 아래에 숫자 카드·요약·그래프·표·출처를 차례로 놓는다(색은 .streamlit/config.toml과 CSS 토큰).
"""
import re
import uuid
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from agent_core import build_graph, chat, make_llm, metric_value, pick_metric

EXAMPLES = ["삼전 2024 영업이익률", "삼성전자랑 SK하이닉스 최근 4년간 영업이익률 변화", "삼전이랑 닉스랑 현대차 2024 영업이익률 비교해줘"]
DART_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
FONT = "Pretendard Variable"
INK, SUB, LINE, SOFT = "#191F28", "#8B95A1", "#F2F4F6", "#F9FAFB"
UP, DOWN = "#F04452", "#3182F6"   # 국내 증권 관례: 상승 빨강, 하락 파랑
SERIES = ["#3182F6", "#F04452", "#00B8A9", "#FFB400", "#8B95A1"]

CSS = f"""<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css");
.stApp, .stApp button, .stApp input, .stApp textarea {{ font-family: "{FONT}", Pretendard, -apple-system, sans-serif; letter-spacing: -0.01em; }}
.block-container {{ padding-top: 3rem; }}
.fp-brand {{ font-size: 18px; font-weight: 700; color: {INK}; }}
.fp-tag {{ color: {SUB}; font-size: 14px; margin-top: 2px; }}
.fp-hero {{ font-size: 28px; font-weight: 700; color: {INK}; line-height: 1.35; margin: 56px 0 6px; letter-spacing: -0.03em; }}
.fp-q {{ font-size: 22px; font-weight: 700; color: {INK}; margin: 32px 0 2px; letter-spacing: -0.02em; }}
.fp-meta {{ color: {SUB}; font-size: 13px; margin-bottom: 8px; }}
.fp-title {{ font-size: 15px; color: {INK}; margin: 6px 0 10px; }}
.fp-title b {{ font-weight: 700; }}
.fp-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 12px; }}
.fp-card {{ background: {SOFT}; border-radius: 16px; padding: 18px 20px; }}
.fp-card .l {{ color: {SUB}; font-size: 13px; margin-bottom: 6px; }}
.fp-card .v {{ color: {INK}; font-size: 26px; font-weight: 700; letter-spacing: -0.03em; }}
.fp-sum {{ background: {SOFT}; border-radius: 16px; padding: 14px 20px; margin-bottom: 12px; }}
.fp-sum div {{ color: #4E5968; font-size: 14px; line-height: 1.9; }}
.fp-sum b {{ color: {INK}; font-weight: 600; }}
.fp-label {{ color: {SUB}; font-size: 13px; font-weight: 600; margin: 14px 0 6px; }}
.fp-up {{ color: {UP}; font-weight: 600; }} .fp-down {{ color: {DOWN}; font-weight: 600; }}
.fp-chip {{ display: inline-block; padding: 6px 12px; margin: 0 6px 6px 0; border-radius: 999px; background: {LINE}; color: #4E5968 !important;
           font-size: 13px; text-decoration: none !important; }}
.fp-chip:hover {{ background: #E5E8EB; }}
.fp-turn {{ border-top: 1px solid {LINE}; margin-top: 36px; }}
.stButton button {{ border-radius: 999px; border: 1px solid #E5E8EB; color: #333D4B; background: #fff; }}
.stButton button:hover {{ border-color: #3182F6; color: #3182F6; }}
[data-testid="stExpander"] details {{ border: none; background: {SOFT}; border-radius: 12px; }}
</style>"""

st.set_page_config(page_title="FinPilot", layout="centered")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown('<div class="fp-brand">FinPilot</div><div class="fp-tag">OpenDART 공시로 확인하는 상장사 연간 실적. 숫자는 모두 공시에서 코드가 계산하고, 투자 판단·예측은 하지 않아요.</div>',
            unsafe_allow_html=True)


@st.cache_resource
def get_graph():
    return build_graph(make_llm())


def jo(n):
    return f"{n / 1e12:,.2f}조 원"


def signed(text):
    """비교 문장 속 '(+8.34%p)' 같은 변화량에 상승 빨강·하락 파랑을 입힌다."""
    s = re.sub(r"\(([+-][\d,.]+)(%p|조 원)\)", lambda m: f'(<span class="fp-{"up" if m[1][0] == "+" else "down"}">{m[1]}{m[2]}</span>)', escape(text))
    return re.sub(r"^([^:]+):", r"<b>\1</b>:", s)   # 콜론 앞 제목(연도·회사·지표)을 굵게 해 훑어보기 쉽게


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def render_cards(x):
    cards = [("매출액", jo(x["revenue"]), None), ("영업이익", jo(x["operating_profit"]), None)]
    if "operating_margin_pct" in x:
        cards.append(("영업이익률", f"{x['operating_margin_pct']:.2f}%", None))
    if "revenue_growth_pct" in x:
        g = x["revenue_growth_pct"]
        cards.append(("매출 성장률", f"{g:+.2f}%", "fp-up" if g > 0 else "fp-down" if g < 0 else None))
    html(f'<div class="fp-title"><b>{escape(x["company"])}</b> · {x["year"]}사업연도 · {escape(x["basis"])}</div><div class="fp-cards">'
         + "".join(f'<div class="fp-card"><div class="l">{l}</div><div class="v {c or ""}">{v}</div></div>' for l, v, c in cards) + "</div>")


def render_chart(rows):
    """여러 연도면 연도별 선 그래프, 한 연도면 회사별 막대 그래프. 값은 표와 같은 행에서 코드가 꺼낸다."""
    key, label, unit = pick_metric(rows)
    df = pd.DataFrame([{"연도": str(x["year"]), "회사": x["company"] + ("" if x["basis"] == "연결" else f"({x['basis']})"), "값": metric_value(x, key)}
                       for x in rows if metric_value(x, key) is not None])
    if len(df) < 2:
        return
    html(f'<div class="fp-label">{label} ({unit})</div>')
    y = alt.Y("값:Q", title=None, axis=alt.Axis(tickCount=5))
    tip = ["회사", "연도", alt.Tooltip("값:Q", format=",.2f", title=label)]
    text = alt.Text("값:Q", format=",.2f")
    if df["연도"].nunique() > 1:
        df["위"] = (df["값"] == df.groupby("연도")["값"].transform("max")) & (df["값"] >= 0)
        base = alt.Chart(df).encode(x=alt.X("연도:O", title=None, axis=alt.Axis(labelAngle=0)), y=y,
                                    color=alt.Color("회사:N", scale=alt.Scale(range=SERIES), legend=alt.Legend(orient="top", title=None, symbolType="circle")))
        # 값 라벨은 그 해 가장 높은 양수 값만 점 위, 나머지는 점 아래에 둬서 비슷한 값끼리·선과 겹치지 않게 한다
        marks = (base.mark_line(point=alt.OverlayMarkDef(size=60, filled=True), strokeWidth=2.5).encode(tooltip=tip)
                 + base.transform_filter("datum.위").mark_text(dy=-13, fontSize=12, fontWeight=600).encode(text=text)
                 + base.transform_filter("!datum.위").mark_text(dy=15, fontSize=12, fontWeight=600).encode(text=text))
    else:
        base = alt.Chart(df).encode(x=alt.X("회사:N", title=None, sort="-y", axis=alt.Axis(labelAngle=0)), y=y)
        marks = (base.mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, size=44, color=SERIES[0]).encode(tooltip=tip)
                 + base.mark_text(dy=-10, fontSize=13, fontWeight=600, color=INK).encode(text=text))
    if (df["값"] < 0).any():   # 적자 연도가 있으면 0 기준선을 그어 음수임을 분명히 한다
        marks += alt.Chart(pd.DataFrame({"값": [0]})).mark_rule(color=SUB, strokeDash=[4, 4]).encode(y="값:Q")
    chart = (marks.properties(height=300, background="transparent")
             .configure_axis(grid=True, gridColor=LINE, domain=False, ticks=False, labelColor=SUB, labelFont=FONT, labelFontSize=12, labelPadding=8)
             .configure_axisX(grid=False).configure_view(stroke=None)
             .configure_legend(labelColor="#4E5968", labelFont=FONT, labelFontSize=13).configure_text(font=FONT))
    st.altair_chart(chart, width="stretch", theme=None)


def render_table(rows):
    df = pd.DataFrame([{"회사": x["company"], "연도": str(x["year"]), "기준": x["basis"], "매출액": x["revenue"] / 1e12, "영업이익": x["operating_profit"] / 1e12,
                        "영업이익률": x.get("operating_margin_pct"), "매출 성장률": x.get("revenue_growth_pct")} for x in rows])
    df = df.dropna(axis=1, how="all")   # 계산하지 않은 비율 칸은 숨긴다
    if (df["기준"] == "연결").all():
        df = df.drop(columns="기준")
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "매출액": st.column_config.NumberColumn("매출액(조 원)", format="%.2f"), "영업이익": st.column_config.NumberColumn("영업이익(조 원)", format="%.2f"),
        "영업이익률": st.column_config.NumberColumn(format="%.2f%%"), "매출 성장률": st.column_config.NumberColumn(format="%.2f%%")})


def render_sources(rows):
    """Perplexity의 출처 칩처럼, 쓴 공시마다 DART 원문 링크를 단다."""
    chips = "".join(f'<a class="fp-chip" href="{DART_VIEWER}{x["rcept_no"]}" target="_blank">{escape(x["company"])} {x["year"]} 사업보고서'
                    f'{" (정정)" if x.get("is_amended") else ""} · {x["rcept_no"]}</a>' for x in rows)
    html(f'<div class="fp-label">출처</div><div>{chips}</div>')


def render_reply(r, key):
    meta = list(r["interpretations"]) + (["이어받은 조건: " + ", ".join(r["carried"])] if r["carried"] else [])
    if meta:
        html(f'<div class="fp-meta">{" · ".join(escape(m) for m in meta)}</div>')
    if r["sentence"]:
        st.write(r["sentence"])
    rows = r["rows"]
    if len(rows) == 1:
        render_cards(rows[0])
    if r.get("comparisons"):   # 이전 세션에 저장된 답변에는 없을 수 있다
        html('<div class="fp-sum">' + "".join(f"<div>{signed(c)}</div>" for c in r["comparisons"]) + "</div>")
    if len(rows) > 1:
        render_chart(rows)
        render_table(rows)
    for n in r["notices"]:
        st.warning(n)
    if r["decline"]:
        st.info(r["decline"]["text"])
    if r["llm_error"]:
        st.error(f"질문을 해석하지 못했어요 ({r['llm_error']}). 잠시 후 다시 시도해 주세요.")
    if r["ask"]:
        st.info(r["ask"]["text"])
        for i, c in enumerate(r["ask"]["candidates"]):
            st.button(f"{c['name']} ({c.get('stock_code') or ''}) · {c['source']}", key=f"{key}-cand-{i}", disabled=bool(st.session_state.pending), on_click=lambda n=c["name"]: st.session_state.update(pending=n))
    if rows:
        render_sources(rows)
    with st.expander(f"실행 기록 · 도구 호출 {r['calls']}회"):
        if rows:
            st.dataframe(pd.DataFrame([{"회사": x["company"], "연도": x["year"], "매출액(원)": f"{x['revenue']:,}", "영업이익(원)": f"{x['operating_profit']:,}",
                                        "접수번호": x["rcept_no"], "접수일": x.get("rcept_date") or "",
                                        "정정": "정정본" if x.get("is_amended") else ("원본" if x.get("is_amended") is False else "확인 못함")} for x in rows]),
                         hide_index=True, width="stretch")
        if r["tool_log"]:
            st.dataframe(pd.DataFrame([{"도구": e["tool"], "인자": str(e["args"]), "상태": e["status"], "코드": e["code"] or "", "캐시": e["cached"], "이어받음": e["inherited"],
                                         "ms": e["ms"]} for e in r["tool_log"]]), hide_index=True, width="stretch")
        else:
            st.write("도구를 호출하지 않았어요.")


def render_question(text, first):
    html(("" if first else '<div class="fp-turn"></div>') + f'<div class="fp-q">{escape(text)}</div>')


if "thread" not in st.session_state:
    st.session_state.thread = str(uuid.uuid4())
    st.session_state.history = []
    st.session_state.pending = None

for i, h in enumerate(st.session_state.history):
    if h["role"] == "user":
        render_question(h["text"], i == 0)
    else:
        render_reply(h["reply"], f"h{i}")

# 예시는 매 실행 같은 자리의 빈칸에 둔다. 질문이 시작된 실행에서는 이 빈칸이 바로 비워져,
# 이전 실행의 버튼이 흐린 채 남아 조회 중에 다시 눌리는 일이 없다
examples = st.empty()
if not st.session_state.history and not st.session_state.pending:
    with examples.container():
        html('<div class="fp-hero">궁금한 회사의 실적을<br>물어보세요</div><div class="fp-tag" style="margin-bottom:20px">회사 이름은 줄임말도 괜찮아요. 연도와 지표를 함께 말해 주세요.</div>')
        for q in EXAMPLES:
            st.button(q, key=f"ex-{q}", on_click=lambda q=q: st.session_state.update(pending=q))

# 입력·예시·후보 버튼은 모두 pending에 질문을 넣고 다시 실행한다. pending이 있는 실행에서는 입력창을 막고 조회한 뒤,
# 다시 실행해 입력창을 연다(조회 중 새 질문이 들어와 진행 중인 조회가 끊기지 않게)
text = st.session_state.pending
st.chat_input("답변을 만들고 있어요" if text else "삼전이랑 닉스 2024년 영업이익률 알려줘", key="typed", disabled=bool(text),
              on_submit=lambda: st.session_state.update(pending=st.session_state.typed))
if text:
    render_question(text, not st.session_state.history)
    st.session_state.history.append({"role": "user", "text": text})
    with st.spinner("공시를 조회하고 있어요"):
        try:
            reply = chat(get_graph(), st.session_state.thread, text)
        finally:   # 오류가 나도 입력창이 막힌 채로 남지 않게
            st.session_state.pending = None
    st.session_state.history.append({"role": "assistant", "reply": reply})
    st.rerun()
