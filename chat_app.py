"""챗봇형 화면: streamlit run chat_app.py   (설계: docs/backlog/agent_design.md)

대화는 화면 세션 메모리에만 보관한다(새로고침하면 사라짐). 숫자·표·되묻기·거절 문구는 코드가 만들고, LLM은 도구 선택과 짧은 설명 문장만 맡는다.
"""
import uuid

import pandas as pd
import streamlit as st

from agent_core import build_graph, chat, make_llm

st.set_page_config(page_title="FinPilot 챗봇", layout="wide")
st.title("FinPilot 챗봇")
st.caption("한국 상장사의 연간(사업보고서, 연결 기본) 매출액·영업이익·영업이익률·매출 성장률을 OpenDART로 조회합니다. 투자 판단·예측은 하지 않습니다.")


@st.cache_resource
def get_graph():
    return build_graph(make_llm())


def won(n):
    return f"{n:,}원 ({n / 1e12:,.2f}조 원)"


def render_reply(r, key):
    for t in r["interpretations"]:
        st.caption(t)
    if r["carried"]:
        st.caption("이어받은 조건: " + ", ".join(r["carried"]))
    if r["rows"]:
        df = pd.DataFrame([{
            "회사": x["company"], "사업연도": x["year"], "기준": x["basis"], "매출액": won(x["revenue"]), "영업이익": won(x["operating_profit"]),
            "영업이익률": f"{x['operating_margin_pct']:.2f}%" if "operating_margin_pct" in x else "",
            "매출 성장률": f"{x['revenue_growth_pct']:.2f}%" if "revenue_growth_pct" in x else "",
            "접수번호": x["rcept_no"], "접수일": x.get("rcept_date") or "", "정정": "정정본" if x.get("is_amended") else ("" if x.get("is_amended") is False else "확인 못함")}
            for x in r["rows"]])
        st.dataframe(df, hide_index=True, width="stretch")
    for n in r["notices"]:
        st.warning(n)
    if r["decline"]:
        st.info(r["decline"]["text"])
    if r["sentence"]:
        st.write(r["sentence"])
    if r["llm_error"]:
        st.error(f"질문을 해석하지 못했어요 ({r['llm_error']}). 잠시 후 다시 시도해 주세요.")
    if r["ask"]:
        st.info(r["ask"]["text"])
        for i, c in enumerate(r["ask"]["candidates"]):
            st.button(f"{c['name']} ({c.get('stock_code') or ''}) · {c['source']}", key=f"{key}-cand-{i}", on_click=lambda n=c["name"]: st.session_state.update(pending=n))
    with st.expander(f"실행 기록 (도구 호출 {r['calls']}회)"):
        if r["tool_log"]:
            st.dataframe(pd.DataFrame([{"도구": e["tool"], "인자": str(e["args"]), "상태": e["status"], "코드": e["code"] or "", "캐시": e["cached"], "이어받음": e["inherited"],
                                         "ms": e["ms"]} for e in r["tool_log"]]), hide_index=True, width="stretch")
        else:
            st.write("도구를 호출하지 않았어요.")


if "thread" not in st.session_state:
    st.session_state.thread = str(uuid.uuid4())
    st.session_state.history = []
    st.session_state.pending = None

for i, h in enumerate(st.session_state.history):
    with st.chat_message(h["role"]):
        if h["role"] == "user":
            st.write(h["text"])
        else:
            render_reply(h["reply"], f"h{i}")

typed = st.chat_input("예: 삼전이랑 닉스 2024년 영업이익률 알려줘")
text = typed or st.session_state.pop("pending", None)
if text:
    st.session_state.history.append({"role": "user", "text": text})
    with st.chat_message("user"):
        st.write(text)
    with st.chat_message("assistant"):
        with st.spinner("조회 중…"):
            reply = chat(get_graph(), st.session_state.thread, text)
        render_reply(reply, f"h{len(st.session_state.history)}")
    st.session_state.history.append({"role": "assistant", "reply": reply})
    st.session_state.pending = None
