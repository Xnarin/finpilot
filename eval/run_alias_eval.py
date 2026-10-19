"""회사명 후보 평가: python -m eval.run_alias_eval [반복횟수]. 코드 후보만 / AI 제안 포함을 같은 입력으로 비교한다(Gemini 호출)."""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

os.environ.setdefault("LANGSMITH_PROJECT", "finpilot-eval")

from dart import famous_match, load_corps  # noqa: E402
from finance import candidates_for  # noqa: E402
from question import suggest_companies  # noqa: E402

ROOT = Path(__file__).parent


def score(expected, names, kind=None):
    if expected is None:
        return {"clean": not names, "flagged": not names and kind in ("foreign", "korean_unlisted")}
    return {"hit1": bool(names) and names[0] == expected, "hit5": expected in names}


def main(repeats=3):
    cases = json.loads((ROOT / "alias_cases.json").read_text(encoding="utf-8"))["items"]
    corps = load_corps()
    rows = []
    for c in cases:
        fm = famous_match(c["input"], corps)
        if fm:  # 유명 별칭·초성은 후보 단계 없이 바로 확정된다. 정답과 다르면 "조용히 잘못 확정"이다.
            names = [fm[1]]
            one = {"names": names, "sources": {fm[1]: "유명 별칭"}, "ai_proposed": [], "ai_verified": [], "ai_error": False, "kind": None, "ms": 0.0,
                   "auto": True, **score(c["expected"], names)}
            rows.append({**c, "auto": True, "code_only": {"names": names, **score(c["expected"], names)}, "runs": [one] * repeats})
            continue
        code_names, _, _ = candidates_for(c["input"], corps)
        runs = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            names, src, ai = candidates_for(c["input"], corps, suggest=suggest_companies)
            runs.append({"names": names, "sources": src, "ai_proposed": ai["proposed"], "ai_verified": ai["verified"], "ai_error": ai.get("error", False),
                         "kind": ai.get("kind"), "ms": (time.perf_counter() - t0) * 1000, **score(c["expected"], names, ai.get("kind"))})
        rows.append({**c, "code_only": {"names": code_names, **score(c["expected"], code_names)}, "runs": runs})
    summary = defaultdict(dict)
    for g in sorted({r["group"] for r in rows}):
        rs = [r for r in rows if r["group"] == g]
        keys = ("clean", "flagged") if rs[0]["expected"] is None else ("hit1", "hit5")
        summary[g] = {"cases": len(rs), **{f"code_only_{k}": sum(r["code_only"].get(k, 0) for r in rs) for k in keys if k != "flagged"},
                      **{f"ai_{k}_runs": sum(x[k] for r in rs for x in r["runs"]) for k in keys}, "runs_total": len(rs) * repeats}
    autos = [r for r in rows if r.get("auto")]
    auto_wrong = [(r["input"], r["expected"], r["code_only"]["names"][0]) for r in autos if r["code_only"]["names"][0] != r["expected"]]
    allruns = [x for r in rows for x in r["runs"]]
    # 한국 상장사 입력인데 해외·비상장으로 잘못 분류되어 후보가 사라진 경우(치명적 오류)
    false_foreign = [(r["input"], x["kind"]) for r in rows if r["expected"] is not None for x in r["runs"] if x["kind"] in ("foreign", "korean_unlisted") and not x["names"]]
    summary["_ai"] = {"proposed_total": sum(len(x["ai_proposed"]) for x in allruns), "dropped_not_in_list": sum(len(x["ai_proposed"]) - len(x["ai_verified"]) for x in allruns),
                      "ai_errors": sum(x["ai_error"] for x in allruns), "auto_confirmed_inputs": len(autos), "auto_confirmed_wrong": len(auto_wrong), "auto_confirmed_wrong_examples": auto_wrong,
                      "false_foreign_runs": len(false_foreign), "false_foreign_examples": false_foreign[:10], "mean_ms_per_resolve": sum(x["ms"] for x in allruns) / len(allruns)}
    meta = {"run_at": datetime.now().isoformat(timespec="seconds"), "repeats": repeats, "corps": len(corps),
            "alias_dict_size": len(__import__("dart").ALIASES)}
    out = ROOT / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-alias-x{repeats}.json"
    out.write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in rows:
        bad = r["expected"] is not None and (not r["code_only"]["hit5"] or any(not x["hit5"] for x in r["runs"]))
        flag = r["expected"] is not None and (not r["code_only"]["hit1"] or any(not x["hit1"] for x in r["runs"]))
        if bad or flag or (r["expected"] is None and not all(x["flagged"] for x in r["runs"])):
            print(("MISS" if bad else "NOT-FIRST" if flag else "NOT-FLAGGED"), r["id"], r["group"], r["input"], "| 기대", r["expected"], "| 코드", r["code_only"]["names"][:3], "| AI포함", r["runs"][0]["names"][:3])
    print("saved", out)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
