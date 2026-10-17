"""평가 결과 JSON의 모델 해석을 실제 파이프라인(OpenDART 조회·계산)에 그대로 넣어 시스템 응답을 문서로 만든다.
사용: python -m eval.export_responses <결과.json> [<결과.json> ...]  -> docs/evaluation/eval_responses.md
Gemini는 다시 호출하지 않고 저장된 해석을 재사용하며, OpenDART는 실제로 호출한다. LangSmith 전송은 끈다."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["LANGSMITH_TRACING"] = "false"

from finance import ask  # noqa: E402

ROOT = Path(__file__).parent
cache = {}


def interp(g):
    return " / ".join("(비움)" if g[k] is None else str(g[k]) for k in ("company", "year", "task"))


def respond(text, got):
    key = json.dumps(got, sort_keys=True, ensure_ascii=False)
    if key not in cache:
        rec = ask(text, parse=lambda t: {"parsed": got, "model": "저장된 해석", "ms": 0.0})
        r = rec["result"]
        if rec["error_code"]:
            cache[key] = f"되묻기·중단 `{rec['error_code']}`: {rec['error_message']}"
        else:
            jo = lambda n: f"{n / 1e12:,.2f}조 원"
            s = f"{r['company']} {r['year']}사업연도 {r['basis']}재무제표: 매출액 {jo(r['revenue'])}, 영업이익 {jo(r['operating_profit'])}"
            if "operating_margin_pct" in r:
                s += f", 영업이익률 {r['operating_margin_pct']:.2f}%"
            if "revenue_growth_pct" in r:
                s += f", 매출 성장률 {r['revenue_growth_pct']:.2f}% (전기 매출 {jo(r['prev_revenue'])})"
            cache[key] = "실행 → " + s
    return cache[key]


def main(files):
    q = {i["id"]: i for i in json.loads((ROOT / "questions.json").read_text(encoding="utf-8"))["items"]}
    rows = {}
    for f in files:
        for r in json.loads(Path(f).read_text(encoding="utf-8"))["rows"]:
            rows[r["id"]] = r
    out = ["# 질문별 모델 해석과 시스템 응답\n",
           f"생성 {datetime.now():%Y-%m-%d %H:%M}. 원본 결과: " + ", ".join(f"`{Path(f).name}`" for f in files) + ".\n",
           "**모델 해석**은 평가 때 Gemini가 낸 `기업 / 연도 / 작업`(3회 반복, 같으면 ×3으로 묶음)이다. **시스템 응답**은 그 해석을 그대로 파이프라인에 넣었을 때 실제로 나온 응답이며, 이 문서를 만들면서 OpenDART를 실제로 호출했다(Gemini는 재호출하지 않음). 금액은 조 원으로 줄여 표시했다. 정답 열이 틀린 해석에는 ❌, 정답이면 ✅를 붙였다. ⚠️는 정답이 불완전한 요청(비워서 멈춰야 함)인데 실행되어 값이 나온 경우다.\n",
           "정답은 Claude가 작성했고 사람 검토 전이다.\n",
           "| ID | 질문 | 정답 | 모델 해석(3회) | 시스템 응답 |\n|---|---|---|---|---|"]
    for iid, it in q.items():
        if iid not in rows:
            continue
        row = rows[iid]
        exp = it["expected"]
        groups = {}
        for run in row["runs"]:
            groups.setdefault(json.dumps(run["got"], sort_keys=True, ensure_ascii=False), []).append(run["got"])
        cells, resp = [], []
        for k, gs in groups.items():
            got = gs[0]
            ok = all(got[f] == exp[f] for f in exp)
            warn = "⚠️ " if (not ok and all(v is not None for v in got.values()) and any(v is None for v in exp.values())) else ""
            cells.append(f"{'✅' if ok else '❌'} {interp(got)} ×{len(gs)}")
            resp.append(f"{warn}{respond(it['question'], got)}" + (f" ({len(gs)}회)" if len(groups) > 1 else ""))
        qtxt = it["question"] if len(it["question"]) < 60 else it["question"][:12] + "… (같은 말 30회 반복) …" + it["question"][-14:]
        if it.get("pending_policy"):
            qtxt += " *(정책 미정)*"
        out.append(f"| {iid} | {qtxt} | {interp(exp)} | " + "<br>".join(cells) + " | " + "<br>".join(resp) + " |")
    (ROOT.parent / "docs" / "evaluation" / "eval_responses.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("rows:", len(out) - 7, "unique pipeline runs:", len(cache))


if __name__ == "__main__":
    main(sys.argv[1:])
