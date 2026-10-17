"""질문 해석 평가: python -m eval.run_eval [dev|final|all]. 실제 Gemini를 호출하며 결과를 eval/results/에 저장한다."""
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


def main(split="dev"):
    data = json.loads((ROOT / "questions.json").read_text(encoding="utf-8"))
    items = [i for i in data["items"] if split == "all" or i["split"] == split]
    rows = []
    for it in items:
        t0 = time.perf_counter()
        try:
            got, err = question.parse_question(it["question"])["parsed"], None
        except Exception as e:  # 호출 실패도 오답으로 집계하고 원인을 남긴다
            got, err = {k: None for k in FIELDS}, getattr(e, "code", type(e).__name__)
        ok = {k: got[k] == it["expected"][k] for k in FIELDS}
        rows.append({"id": it["id"], "question": it["question"], "expected": it["expected"], "got": got, "error": err,
                     "field_ok": ok, "all_ok": all(ok.values()), "ms": (time.perf_counter() - t0) * 1000})
    n = len(rows)
    summary = {"split": split, "n": n, "all_correct": sum(r["all_ok"] for r in rows),
               **{f"{k}_correct": sum(r["field_ok"][k] for r in rows) for k in FIELDS},
               "errors": sum(bool(r["error"]) for r in rows),
               "mean_ms": sum(r["ms"] for r in rows) / max(n, 1)}
    meta = {"run_at": datetime.now().isoformat(timespec="seconds"), "model": question.MODEL, "temperature": 0,
            "prompt_sha256": hashlib.sha256(question.PROMPT.encode()).hexdigest()[:12],
            "dataset_sha256": hashlib.sha256((ROOT / "questions.json").read_bytes()).hexdigest()[:12],
            "langsmith_project": os.environ.get("LANGSMITH_PROJECT"), "repeats": 1}
    out = ROOT / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-{split}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    for r in rows:
        if not r["all_ok"]:
            print("FAIL", r["id"], r["question"], "| expected", r["expected"], "| got", r["got"], r["error"] or "")
    print("saved", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")
