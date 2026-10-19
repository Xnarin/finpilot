import streamlit as st
from langsmith.utils import tracing_is_enabled

from finance import DATA_KIND, TASKS, YEARS, ask, pick_company, run
from question import suggest_companies

st.set_page_config(page_title="FinPilot", layout="wide")
st.title("FinPilot")
st.info("OpenDART 사업보고서(상장사, 연결) 조회 결과입니다. 질문 해석에만 Gemini를 쓰고, 금융 수치는 OpenDART 조회와 코드 계산으로만 구합니다.")

with st.form("question"):
    text = st.text_input("질문으로 조회", placeholder="예: SK하이닉스 2023년 영업이익률 알려줘")
    asked = st.form_submit_button("질문 실행")
if asked and text.strip():
    st.session_state["rec"] = ask(text.strip())

with st.form("input"):
    c1, c2, c3 = st.columns(3)
    company = c1.text_input("기업(정확한 상장사명)", "삼성전자")
    year = c2.selectbox("사업연도", YEARS, index=2)
    task = c3.selectbox("작업", TASKS)
    submitted = st.form_submit_button("실행")

if submitted:
    st.session_state["rec"] = run(task, year, company, suggest=suggest_companies)

rec = st.session_state.get("rec")
if not rec:
    st.info("조건을 고르고 실행을 눌러 주세요.")
    st.stop()


def won(n):
    return f"{n:,}원 ({n / 1e8:,.1f}억원)"


st.subheader("선택한 입력값")
st.json(rec["inputs"])
st.caption(f"LangSmith tracing: {'켜짐' if tracing_is_enabled() else '꺼짐'} (전송 성공 여부는 SDK가 백그라운드로 처리해 여기서 확인하지 못함)")

st.subheader("결과")
if rec["error_code"]:
    st.error(f"[{rec['error_code']}] {rec['error_message']}")
    for name in rec.get("candidates") or []:
        if rec["error_code"] == "COMPANY_NOT_FOUND":
            st.button(f"{name}(으)로 조회 · {rec.get('candidate_sources', {}).get(name, '')}", key=f"pick-{rec['run_id']}-{name}",
                      on_click=lambda n=name: st.session_state.update(rec=pick_company(rec, n)))
else:
    r = rec["result"]
    st.caption(f"기업 {r['company']} · {r['year']}사업연도 · {r['basis']}재무제표 · 단위 {r['unit']} · {DATA_KIND}")
    st.caption(f"접수번호 {r['rcept_no']} · 조회 시점 {r['fetched_at']}")
    a, b = st.columns(2)
    a.metric("매출액", won(r["revenue"]))
    b.metric("영업이익", won(r["operating_profit"]))
    if "operating_margin_pct" in r:
        st.metric("영업이익률", f"{r['operating_margin_pct']:.2f}%")
        st.caption("영업이익 ÷ 매출액 × 100")
    if "revenue_growth_pct" in r:
        st.metric("매출 성장률", f"{r['revenue_growth_pct']:.2f}%")
        st.caption(f"(당기 매출액 − 전기 매출액) ÷ 전기 매출액 × 100 · 전기 매출액 {won(r['prev_revenue'])}")

st.subheader("실행 기록")
st.caption(f"실행 ID `{rec['run_id']}` · 시작 {rec['started_at']} · 전체 {rec['total_ms']:.2f}ms "
           f"(이번 실행의 조회·계산 시간이며 성능 평가가 아님) · 데이터 종류: {rec['data_kind']}")
for s in rec["steps"]:
    with st.expander(f"{'✅' if s['status'] == '성공' else '❌'} {s['name']} — {s['status']} ({s['ms']:.2f}ms)"):
        if s["data"] is not None:
            st.write(s["data"])
        else:
            st.write(f"오류 코드 {rec['error_code']}: {rec['error_message']}")
