"""에이전트 평가: python -m eval.run_agent_eval [반복횟수] [--baseline] [--cases=agent_cases_heldout.json]
실제 Gemini와 OpenDART를 호출한다. 오늘 날짜는 2026-10-19로 고정한다. 정답은 최종 표 + 도구 호출 집합이고, 같은 질문을 반복해 일관성을 본다.
--baseline: 단일 요청 질문을 기존 파이프라인(baseline-single-request의 ask)으로도 돌려 같은 기준으로 비교한다."""
import hashlib
import json
import os
import sys
import time
import uuid
import warnings
from datetime import date, datetime
from pathlib import Path

os.environ["LANGSMITH_TRACING"] = "false"   # LangSmith 월 한도가 소진되어 있고, 평가는 도구 호출 기록(tool_log)으로 한다
warnings.filterwarnings("ignore")

import agent_core  # noqa: E402
from dart import load_corps  # noqa: E402

ROOT = Path(__file__).parent
FIXED_TODAY = date(2026, 10, 19)
TOL = 0.011


def corp_names():
    return {c[0]: c[1] for c in load_corps()}


def business_calls(tool_log, names):
    """OpenDART까지 간 조회·계산 호출의 집합. 검증으로 막힌 호출과 지원 불가로 돌려진 호출은 제외하고, 같은 (회사,연도,기준)의 get_financials는 계산 호출이 있으면 중복으로 본다."""
    s = set()
    for e in tool_log:
        if e["tool"] not in ("get_financials", "compute_ratio") or str(e.get("code") or "").startswith(agent_core.GUARD_PREFIX) or e["status"] == "unsupported":
            continue
        a = e["args"]
        s.add((names.get(a.get("corp_code"), a.get("corp_code")), a.get("year"), a.get("basis", "연결"), a.get("metric")))
    return {c for c in s if not (c[3] is None and (c[0], c[1], c[2]) in {(x[0], x[1], x[2]) for x in s if x[3]})}


def expected_calls(expect):
    if "calls" in expect:   # 정답 호출 집합을 직접 지정한 경우(표는 없지만 시도해야 하는 조회가 있을 때)
        return {(c["company"], c["year"], c.get("basis", "연결"), c.get("metric")) for c in expect["calls"]}
    return {(r["company"], r["year"], r.get("basis", "연결"), r.get("metric")) for r in expect.get("rows", [])}


def row_key(r):
    return (r["company"], r["year"], r["basis"])


def check_turn(expect, reply, names):
    if "any_of" in expect:   # 여러 정답 중 하나면 통과(예: 주입 시도는 올바른 행을 내거나 거절하면 둘 다 정답)
        outs = [check_turn(e, reply, names) for e in expect["any_of"]]
        best = next((o for o in outs if o["ok"]), min(outs, key=lambda o: o["unexpected_rows"]))
        return best
    res = {}
    exp_rows = expect.get("rows", [])
    got = {row_key(r): r for r in reply["rows"]}
    want = {(e["company"], e["year"], e.get("basis", "연결")): e for e in exp_rows}
    res["rows_match"] = set(got) == set(want) if "max_rows" not in expect else len(got) <= expect["max_rows"]
    ok_val = True
    for k, e in want.items():
        if k in got and e.get("metric") and e.get("value") is not None:
            v = got[k].get(e["metric"] + "_pct")
            ok_val &= v is not None and abs(v - e["value"]) <= TOL
        elif k in got and e.get("metric"):
            ok_val &= got[k].get(e["metric"] + "_pct") is not None
    res["values_match"] = ok_val
    res["unexpected_rows"] = len(set(got) - set(want)) if "max_rows" not in expect else 0       # 위험: 정답에 없는 값이 정상처럼 표시됨
    res["missing_rows"] = len(set(want) - set(got)) if "max_rows" not in expect else 0
    if "ask" in expect:
        res["ask_match"] = bool(reply["ask"]) and set(reply["ask"]["missing"]) == set(expect["ask"])
    else:
        res["ask_match"] = True
    if expect.get("decline_any"):
        res["decline_match"] = bool(reply["decline"])
    if "decline" in expect:
        res["decline_match"] = bool(reply["decline"]) and reply["decline"]["reason"] == expect["decline"]
    if "mention" in expect:
        text = " ".join(reply["notices"] + [reply["decline"]["text"] if reply["decline"] else "", reply["ask"]["text"] if reply["ask"] else "", reply["sentence"] or ""])
        res["mention_match"] = all(m in text for m in expect["mention"])
    if "limit_hit" in expect:
        res["limit_match"] = bool(reply["limit_hit"]) == expect["limit_hit"]
    if "carried" in expect:
        res["carried_match"] = bool(reply["carried"])
    got_calls, exp_calls = business_calls(reply["tool_log"], names), expected_calls(expect)
    res["calls_match"] = got_calls == exp_calls if "max_rows" not in expect else True
    res["extra_calls"] = len(got_calls - exp_calls) if "max_rows" not in expect else 0
    res["guard_hits"] = sum(1 for e in reply["tool_log"] if str(e.get("code") or "").startswith(agent_core.GUARD_PREFIX))
    res["ok"] = all(v for k, v in res.items() if k.endswith("_match")) and not res["unexpected_rows"]
    return res


def main(repeats=3, baseline=False, cases_file="agent_cases.json"):
    cases = json.loads((ROOT / cases_file).read_text(encoding="utf-8"))
    names = corp_names()
    deps = agent_core.Deps(today=lambda: FIXED_TODAY)
    graph = agent_core.build_graph(agent_core.make_llm(), deps)
    rows = []
    for it in cases["items"]:
        runs = []
        for _ in range(repeats):
            tid, turns = str(uuid.uuid4()), []
            for t in it["turns"]:
                t0 = time.perf_counter()
                try:
                    reply = agent_core.chat(graph, tid, t["user"])
                except Exception as e:  # 그래프 오류도 오답으로 집계하고 원인 종류를 남긴다
                    reply = {"rows": [], "notices": [], "ask": None, "decline": None, "sentence": None, "limit_hit": False, "carried": [], "tool_log": [], "calls": 0,
                             "llm_calls": 0, "usage": {}, "llm_error": type(e).__name__}
                ms = (time.perf_counter() - t0) * 1000
                c = check_turn(t["expect"], reply, names)
                turns.append({"user": t["user"], "check": c, "ms": ms, "calls": reply["calls"], "llm_calls": reply["llm_calls"], "usage": reply["usage"], "llm_error": reply["llm_error"],
                              "got": {"rows": [{k: v for k, v in r.items() if k in ("company", "year", "basis", "operating_margin_pct", "revenue_growth_pct")} for r in reply["rows"]],
                                      "ask": reply["ask"] and reply["ask"]["missing"], "decline": reply["decline"] and reply["decline"]["reason"], "notices": reply["notices"],
                                      "calls": sorted(map(str, business_calls(reply["tool_log"], names)))}})
            runs.append({"ok": all(x["check"]["ok"] for x in turns), "turns": turns})
        rows.append({"id": it["id"], "category": it["category"], "runs": runs, "always_ok": all(r["ok"] for r in runs),
                     "consistent": len({json.dumps([[x["got"]["rows"], x["got"]["ask"], x["got"]["decline"]] for x in r["turns"]], sort_keys=True, ensure_ascii=False) for r in runs}) == 1})
    allturns = [t for r in rows for run in r["runs"] for t in run["turns"]]
    n = max(len(allturns), 1)
    cat = {}
    for r in rows:
        c = cat.setdefault(r["category"], {"cases": 0, "case_runs": 0, "ok_runs": 0})
        c["cases"] += 1
        c["case_runs"] += len(r["runs"])
        c["ok_runs"] += sum(run["ok"] for run in r["runs"])
    summary = {"cases": len(rows), "repeats": repeats, "case_runs": sum(len(r["runs"]) for r in rows), "ok_case_runs": sum(run["ok"] for r in rows for run in r["runs"]),
               "cases_always_ok": sum(r["always_ok"] for r in rows), "cases_inconsistent": sum(not r["consistent"] for r in rows),
               "unexpected_rows_total": sum(t["check"]["unexpected_rows"] for t in allturns), "missing_rows_total": sum(t["check"]["missing_rows"] for t in allturns),
               "extra_business_calls_total": sum(t["check"]["extra_calls"] for t in allturns), "guard_hits_total": sum(t["check"]["guard_hits"] for t in allturns),
               "llm_errors": sum(bool(t["llm_error"]) for t in allturns), "mean_turn_ms": sum(t["ms"] for t in allturns) / n,
               "mean_tool_calls_per_turn": sum(t["calls"] for t in allturns) / n, "mean_llm_calls_per_turn": sum(t["llm_calls"] for t in allturns) / n,
               "mean_tokens_per_turn": sum(t["usage"].get("total_tokens", 0) for t in allturns) / n, "by_category": cat}
    meta = {"run_at": datetime.now().isoformat(timespec="seconds"), "model": agent_core.MODEL, "temperature": 0, "repeats": repeats, "fixed_today": FIXED_TODAY.isoformat(),
            "system_prompt_sha256": hashlib.sha256(agent_core.SYSTEM.encode()).hexdigest()[:12], "dataset": cases_file, "dataset_sha256": hashlib.sha256((ROOT / cases_file).read_bytes()).hexdigest()[:12],
            "max_calls": agent_core.MAX_CALLS, "max_requests": agent_core.MAX_REQUESTS}
    out = ROOT / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-agent-x{repeats}.json"
    out.write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "by_category"}, ensure_ascii=False))
    for c, v in cat.items():
        print(f"  {c}: {v['ok_runs']}/{v['case_runs']}")
    for r in rows:
        if not r["always_ok"] or not r["consistent"]:
            bad = [(i, t["user"], {k: v for k, v in t["check"].items() if (k.endswith("_match") and not v) or (k in ("unexpected_rows", "missing_rows", "extra_calls") and v)}, t["got"])
                   for run in r["runs"] for i, t in enumerate(run["turns"]) if not t["check"]["ok"]][:1]
            print("FAIL" if not r["always_ok"] else "INCONSISTENT", r["id"], r["category"], sum(not run["ok"] for run in r["runs"]), "/", len(r["runs"]), json.dumps(bad, ensure_ascii=False)[:420])
    print("saved", out)
    if baseline:
        run_baseline(cases, names, repeats)


def run_baseline(cases, names, repeats):
    """기존 단일 요청 파이프라인(ask)에 단일 턴 질문을 넣어 같은 기준(행·되묻기)으로 채점한다."""
    from finance import ask
    res, risky = [], 0
    for it in cases["items"]:
        if len(it["turns"]) != 1:
            continue
        t = it["turns"][0]
        got = []
        for _ in range(repeats):
            rec = ask(t["user"])
            rows = []
            if rec.get("result"):
                r = rec["result"]
                rows = [{"company": r["company"], "year": r["year"], "basis": r["basis"],
                         **({"operating_margin_pct": r["operating_margin_pct"]} if "operating_margin_pct" in r else {}), **({"revenue_growth_pct": r["revenue_growth_pct"]} if "revenue_growth_pct" in r else {})}]
            got.append(rows)
        want = {(e["company"], e["year"], e.get("basis", "연결")) for e in t["expect"].get("rows", [])}
        for rows in got:
            have = {(r["company"], r["year"], r["basis"]) for r in rows}
            ok = have == want if "max_rows" not in t["expect"] else True
            risky += len(have - want)
            res.append({"id": it["id"], "category": it["category"], "rows_ok": ok})
    n = max(len(res), 1)
    print(f"[baseline ask] 단일 턴 {len({r['id'] for r in res})}개 × {repeats}회: 행 일치 {sum(r['rows_ok'] for r in res)}/{len(res)}, 정답에 없는 행(위험) {risky}건")
    for c in sorted({r["category"] for r in res}):
        sub = [r for r in res if r["category"] == c]
        print(f"   {c}: {sum(r['rows_ok'] for r in sub)}/{len(sub)}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cf = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--cases=")), "agent_cases.json")
    main(int(args[0]) if args else 3, "--baseline" in sys.argv, cf)
