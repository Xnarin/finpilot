"""에이전트에 어려운 질문을 던지고 질문·답변·도구 호출·판정을 문서로 남긴다.
사용: python -m eval.run_agent_qa [--cases=agent_cases_hard.json] [--repeats=2] [--out=docs/evaluation/agent_hard_qa.md]
실제 Gemini와 OpenDART를 호출한다. 오늘 날짜는 2026-10-19로 고정한다. 답변은 화면에 나오는 것과 같은 내용(표·안내·되묻기·거절·설명 문장)을 글로 옮긴 것이다."""
import json
import os
import sys
import time
import uuid
import warnings
from datetime import datetime
from pathlib import Path

os.environ["LANGSMITH_TRACING"] = "false"
warnings.filterwarnings("ignore")

import agent_core  # noqa: E402
from eval.run_agent_eval import FIXED_TODAY, business_calls, check_turn, corp_names  # noqa: E402

ROOT = Path(__file__).parent


def jo(n):
    return f"{n / 1e12:,.2f}조 원"


def render(reply):
    """화면에 보이는 응답을 줄 단위 글로 옮긴다."""
    lines = []
    for t in reply["interpretations"]:
        lines.append(f"- (해석) {t}")
    if reply["carried"]:
        lines.append("- (이어받은 조건) " + ", ".join(reply["carried"]))
    for r in reply["rows"]:
        s = f"- **{r['company']} {r['year']}사업연도 {r['basis']}**: 매출액 {jo(r['revenue'])}, 영업이익 {jo(r['operating_profit'])}"
        if "operating_margin_pct" in r:
            s += f", 영업이익률 {r['operating_margin_pct']:.2f}%"
        if "revenue_growth_pct" in r:
            s += f", 매출 성장률 {r['revenue_growth_pct']:.2f}%"
        s += f" (접수번호 {r['rcept_no']}{', 정정본' if r.get('is_amended') else ''})"
        lines.append(s)
    for n in reply["notices"]:
        lines.append(f"- (안내) {n}")
    if reply["decline"]:
        lines.append(f"- (거절) {reply['decline']['text']}")
    if reply["ask"]:
        c = reply["ask"]["candidates"]
        lines.append(f"- (되묻기) {reply['ask']['text']}" + (" 후보: " + ", ".join(x["name"] for x in c) if c else ""))
    if reply["sentence"]:
        lines.append(f"- (설명 문장) {reply['sentence']}")
    if reply["sentence_dropped_for_digits"]:
        lines.append("- (설명 문장은 숫자가 있어 버려짐)")
    if reply["llm_error"]:
        lines.append(f"- (오류) {reply['llm_error']}")
    return lines or ["- (응답 없음)"]


def describe(expect):
    if "any_of" in expect:
        return " 또는 ".join(describe(e) for e in expect["any_of"])
    parts = []
    if expect.get("rows"):
        parts.append("표: " + ", ".join(f"{r['company']} {r['year']}" + (" 영업이익률" if r.get("metric") == "operating_margin" else " 매출 성장률" if r.get("metric") == "revenue_growth" else "") + (" 별도" if r.get("basis") == "별도" else "") for r in expect["rows"]))
    if expect.get("no_rows"):
        parts.append("표 없음")
    if "ask" in expect:
        parts.append("되묻기: " + "·".join(expect["ask"]))
    if expect.get("decline"):
        parts.append("거절: " + expect["decline"])
    if expect.get("decline_any"):
        parts.append("거절")
    if expect.get("mention"):
        parts.append("안내에 '" + "', '".join(expect["mention"]) + "' 포함")
    return ", ".join(parts) or "(표·되묻기 없음)"


def signature(reply):
    return json.dumps([[(r["company"], r["year"], r["basis"], round(r.get("operating_margin_pct", 0), 2), round(r.get("revenue_growth_pct", 0), 2)) for r in reply["rows"]],
                       reply["ask"] and reply["ask"]["missing"], reply["decline"] and reply["decline"]["reason"], len(reply["notices"])], ensure_ascii=False, sort_keys=True)


def main(cases_file="agent_cases_hard.json", repeats=2, out_md="docs/evaluation/agent_hard_qa.md"):
    cases = json.loads((ROOT / cases_file).read_text(encoding="utf-8"))
    names = corp_names()
    graph = agent_core.build_graph(agent_core.make_llm(), agent_core.Deps(today=lambda: FIXED_TODAY))
    results = []
    for it in cases["items"]:
        runs = []
        for _ in range(repeats):
            tid, turns = str(uuid.uuid4()), []
            for t in it["turns"]:
                t0 = time.perf_counter()
                try:
                    reply = agent_core.chat(graph, tid, t["user"])
                except Exception as e:
                    reply = {"rows": [], "notices": [], "ask": None, "decline": None, "sentence": None, "sentence_dropped_for_digits": False, "interpretations": [],
                             "carried": [], "limit_hit": False, "llm_error": type(e).__name__, "calls": 0, "llm_calls": 0, "usage": {}, "tool_log": []}
                chk = check_turn(t["expect"], reply, names)
                turns.append({"user": t["user"], "expect": t["expect"], "reply": reply, "check": chk, "ms": (time.perf_counter() - t0) * 1000})
            runs.append(turns)
        results.append({"id": it["id"], "category": it["category"], "runs": runs})
    # 마크다운
    total = sum(len(r["runs"]) for r in results)
    ok = sum(all(t["check"]["ok"] for t in run) for r in results for run in r["runs"])
    unexpected = sum(t["check"]["unexpected_rows"] for r in results for run in r["runs"] for t in run)
    md = [f"# 에이전트 어려운 질문 Q&A ({datetime.now():%Y-%m-%d})\n",
          f"답변하기 어려울 것으로 예상한 질문 {len(results)}개를 실제 Gemini(`{agent_core.MODEL}`)와 OpenDART로 각각 {repeats}회 물어본 기록이다. 오늘 날짜는 {FIXED_TODAY}로 고정했다. 질문 원본은 `eval/{cases_file}`, 실행기는 `python -m eval.run_agent_qa`, 원본 결과는 `eval/results/`의 `*-agentqa-*.json`이다.\n",
          "답변은 챗봇 화면에 나오는 내용(표·안내·되묻기·거절·설명 문장)을 글로 옮긴 것이다. 표의 숫자·되묻기·거절 문구는 코드가 만들고, 설명 문장은 숫자가 있으면 버려진다. 판정의 정답은 Claude가 작성했고 사람 검토 전이다. 정답 중 '또는'은 여러 답이 모두 허용된다는 뜻이다(예: 의견을 묻는 질문은 숫자 표만 보여 주거나 거절하면 둘 다 정답).\n",
          f"**요약:** 질문×{repeats}회 {total}번 중 정답 {ok}번, **정답에 없는 표 행(틀린 값을 정상처럼 표시) {unexpected}건**.\n"]
    for r in results:
        passed = sum(all(t["check"]["ok"] for t in run) for run in r["runs"])
        md.append(f"## {r['id']} · {r['category']} — 정답 {passed}/{len(r['runs'])}\n")
        for ti, t in enumerate(r["runs"][0]):
            md.append(f"**질문{(' ' + str(ti + 1)) if len(r['runs'][0]) > 1 else ''}:** {t['user']}\n")
            md.append(f"**기대:** {describe(t['expect'])}\n")
            sigs = {}
            for run in r["runs"]:
                sigs.setdefault(signature(run[ti]["reply"]), []).append(run[ti])
            for k, (sig, ts) in enumerate(sigs.items(), 1):
                tag = f"(같은 답 {len(ts)}/{len(r['runs'])}회)" if len(sigs) == 1 else f"(답 {k}: {len(ts)}/{len(r['runs'])}회)"
                verdict = "✅ 정답" if ts[0]["check"]["ok"] else "❌ 오답: " + ", ".join(k2 for k2, v in ts[0]["check"].items() if (k2.endswith("_match") and not v) or (k2 in ("unexpected_rows", "missing_rows", "extra_calls") and v))
                md.append(f"**답변** {tag} {verdict}\n")
                md.extend(render(ts[0]["reply"]))
                calls = [f"{e['tool']}({', '.join(f'{a}={b}' for a, b in e['args'].items() if a != 'evidence')})→{e['status']}{(':' + e['code']) if e['code'] else ''}" for e in ts[0]["reply"]["tool_log"]]
                md.append("\n  <details><summary>도구 호출 " + str(len(calls)) + "회</summary>\n\n  - " + "\n  - ".join(calls) + "\n\n  </details>\n")
        md.append("")
    Path(ROOT.parent / out_md).write_text("\n".join(md) + "\n", encoding="utf-8")
    raw = ROOT / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-agentqa-x{repeats}.json"
    raw.write_text(json.dumps([{"id": r["id"], "category": r["category"], "runs": [[{"user": t["user"], "check": t["check"], "ms": t["ms"],
                                "reply": {k: v for k, v in t["reply"].items() if k != "tool_log"}} for t in run] for run in r["runs"]]} for r in results], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"질문 {len(results)}개 x {repeats}회: 정답 {ok}/{total}, 정답에 없는 행 {unexpected}건. 문서 {out_md}, 결과 {raw.name}")
    for r in results:
        bad = [i for i, run in enumerate(r["runs"]) if not all(t["check"]["ok"] for t in run)]
        if bad:
            print("  오답:", r["id"], r["runs"][bad[0]][-1]["user"][:30], f"{len(bad)}/{len(r['runs'])}회")


if __name__ == "__main__":
    kw = {a.split("=", 1)[0][2:]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    main(kw.get("cases", "agent_cases_hard.json"), int(kw.get("repeats", 2)), kw.get("out", "docs/evaluation/agent_hard_qa.md"))
