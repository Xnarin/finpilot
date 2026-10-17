"""질문 해석 평가: python -m eval.run_eval [dev|final|dev_hard|final_hard|all] [반복횟수]. 실제 Gemini를 호출하며 결과를 eval/results/에 저장한다."""
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("LANGSMITH_PROJECT", "finpilot-eval")  # 평가 실행은 개발 실행과 분리해 추적

import question  # noqa: E402  (.env 로딩과 LangSmith 설정 이후 import)

ROOT = Path(__file__).parent
FIELDS = ("company", "year", "task")


def outcome(got, expected, ok):
    """correct / risky(불완전해야 할 질문이나 다른 요청이 완전한 요청으로 실행됨) / over_null(완전해야 하는데 비워 되묻기) / harmless(둘 다 불완전, 값만 다름)"""
    if all(ok.values()):
        return "correct"
    if all(v is not None for v in got.values()):
        return "risky"
    return "over_null" if all(v is not None for v in expected.values()) else "harmless"


def main(split="dev", repeats=1):
    data = json.loads((ROOT / "questions.json").read_text(encoding="utf-8"))
    items = [i for i in data["items"] if split == "all" or i["split"] == split]
    rows = []
    for it in items:
        runs = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            try:
                r = question.parse_question(it["question"])
                got, err, usage = r["parsed"], None, r["usage"]
            except Exception as e:  # 호출 실패도 오답으로 집계하고 원인을 남긴다
                got, err, usage = {k: None for k in FIELDS}, getattr(e, "code", type(e).__name__), None
            ok = {k: got[k] == it["expected"][k] for k in FIELDS}
            runs.append({"got": got, "error": err, "field_ok": ok, "all_ok": all(ok.values()), "outcome": outcome(got, it["expected"], ok), "ms": (time.perf_counter() - t0) * 1000, "usage": usage})
        rows.append({"id": it["id"], "category": it.get("category"), "pending_policy": bool(it.get("pending_policy")), "question": it["question"], "expected": it["expected"], "runs": runs,
                     "always_ok": all(r["all_ok"] for r in runs), "consistent": len({json.dumps(r["got"], sort_keys=True) for r in runs}) == 1})
    def summarize(rs):
        allruns = [r for row in rs for r in row["runs"]]
        n = max(len(allruns), 1)
        toks = [r["usage"] for r in allruns if r["usage"]]
        cnt = lambda o: sum(r["outcome"] == o for r in allruns)
        return {"questions": len(rs), "runs": len(allruns),
                "run_accuracy_all_fields": sum(r["all_ok"] for r in allruns) / n,
                **{f"run_accuracy_{k}": sum(r["field_ok"][k] for r in allruns) / n for k in FIELDS},
                "risky_runs": cnt("risky"), "over_null_runs": cnt("over_null"), "harmless_wrong_runs": cnt("harmless"),
                "questions_always_correct": sum(r["always_ok"] for r in rs),
                "questions_inconsistent": sum(not r["consistent"] for r in rs),
                "call_errors": sum(bool(r["error"]) for r in allruns),
                "mean_ms": sum(r["ms"] for r in allruns) / n,
                "input_tokens_per_call": sum(t["input_tokens"] for t in toks) / max(len(toks), 1),
                "output_tokens_per_call": sum(t["output_tokens"] for t in toks) / max(len(toks), 1)}

    scored = [r for r in rows if not r["pending_policy"]]
    summary = {"split": split, "repeats": repeats, **summarize(scored)}
    pending = [r for r in rows if r["pending_policy"]]
    if pending:
        summary["pending_policy_excluded"] = summarize(pending)
    cats = {c: summarize([r for r in scored if r["category"] == c]) for c in sorted({r["category"] for r in scored if r["category"]})}
    summary["by_category"] = {c: {k: v[k] for k in ("questions", "run_accuracy_all_fields", "risky_runs", "over_null_runs")} for c, v in cats.items()}
    meta = {"run_at": datetime.now().isoformat(timespec="seconds"), "model": question.MODEL, "temperature": 0,
            "prompt_sha256": hashlib.sha256(question.PROMPT.encode()).hexdigest()[:12],
            "dataset_sha256": hashlib.sha256((ROOT / "questions.json").read_bytes()).hexdigest()[:12],
            "langsmith_project": os.environ.get("LANGSMITH_PROJECT"), "repeats": repeats}
    out = ROOT / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-{split}-x{repeats}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    for row in rows:
        if (not row["always_ok"] or not row["consistent"]) and not row["pending_policy"]:
            bad = sum(not r["all_ok"] for r in row["runs"])
            print(f"{'INCONSISTENT' if not row['consistent'] else 'FAIL'} {row['id']} {row['question']} | wrong {bad}/{repeats} | expected {row['expected']} | got {[r['got'] for r in row['runs']][0]}")
    print("saved", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev", int(sys.argv[2]) if len(sys.argv) > 2 else 1)
