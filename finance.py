"""조회·계산·실행 기록. 화면(app.py)과 분리. 금액은 원 단위 정수, 비율은 %."""
import time
import uuid
from datetime import datetime

from dart import SRC_ALIAS, SRC_ENGLISH, SRC_PREFERRED, FinError, candidate_list, fetch_financials, load_corps
from langsmith import traceable
from question import parse_question, suggest_companies

DATA_KIND = "OpenDART 실제 데이터"
YEARS = [2022, 2023, 2024, 2025]

TASKS = ["실적 조회", "영업이익률 계산", "매출 성장률 계산"]


def operating_margin(rec):
    if rec["revenue"] <= 0:
        raise FinError("INVALID_DENOMINATOR", "매출액이 0 또는 음수라서 영업이익률을 계산할 수 없습니다.")
    return rec["operating_profit"] / rec["revenue"] * 100


def revenue_growth(cur, prev):
    for k, label in (("company", "기업"), ("basis", "연결/별도 기준"), ("unit", "단위")):
        if cur[k] != prev[k]:
            raise FinError("BASIS_MISMATCH", f"당기와 전기의 {label}이 달라 비교할 수 없습니다 ({prev[k]} ≠ {cur[k]}).")
    if prev["year"] != cur["year"] - 1:
        raise FinError("PERIOD_MISMATCH", f"전기 데이터가 직전 연도가 아닙니다 ({prev['year']} → {cur['year']}).")
    if prev["revenue"] <= 0:
        raise FinError("INVALID_DENOMINATOR", "전기 매출액이 0 또는 음수라서 매출 성장률을 계산할 수 없습니다.")
    return (cur["revenue"] - prev["revenue"]) / prev["revenue"] * 100


AI_SOURCE = "AI 제안 (상장사 목록에서 확인됨)"
STRONG_SOURCES = (SRC_ALIAS, SRC_PREFERRED, SRC_ENGLISH, AI_SOURCE)  # 이 출처가 하나라도 있으면 신뢰할 수 있는 후보로 본다
KIND_LABEL = {"foreign": "해외 기업", "korean_unlisted": "한국 비상장 기업"}


def candidates_for(name, corps=None, suggest=None):
    """되묻기 후보 (이름 목록, 출처 dict, AI 단계 기록). 별칭·우선주 -> AI(목록 검증됨) -> 나머지 순, 최대 5개. 확정은 사용자가 한다."""
    corps = corps if corps is not None else load_corps()
    cl = candidate_list(name, corps)
    ai = suggest(name, corps) if suggest else None
    first = [c for c in cl if c[1] in (SRC_ALIAS, SRC_PREFERRED)]
    mid = [(v, AI_SOURCE) for v in (ai["verified"] if ai else [])]
    merged = []
    for c, s in first + mid + [c for c in cl if c not in first]:
        if c not in [m[0] for m in merged]:
            merged.append((c, s))
    # 철자·약칭 추정 같은 약한 후보는 AI가 해외·비상장이라고 판단하고 강한 후보가 없을 때 버린다("애플"→"애니플러스" 방지)
    if ai and ai.get("kind") in KIND_LABEL and not any(s in STRONG_SOURCES for _, s in merged):
        merged = []
    return [m[0] for m in merged[:5]], dict(merged[:5]), ai


@traceable(name="run", run_type="chain", process_inputs=lambda i: {k: i[k] for k in ("task", "year", "company")})
def run(task, year, company, fetch=fetch_financials, suggest=None, candidates_fn=candidates_for):
    """한 번의 실행을 기록 dict로 반환. 오류는 단계 상태와 error_*에 담긴다."""
    t0 = time.perf_counter()
    rec = {"run_id": uuid.uuid4().hex[:8], "started_at": datetime.now().isoformat(timespec="seconds"),
           "data_kind": DATA_KIND, "inputs": {"기업": company, "사업연도": year, "작업": task},
           "steps": [], "result": None, "error_code": None, "error_message": None, "candidates": None, "candidate_sources": {}}

    def step(name, fn):
        s = time.perf_counter()
        try:
            out = fn()
            rec["steps"].append({"name": name, "status": "성공", "ms": (time.perf_counter() - s) * 1000, "data": out})
            return out
        except FinError as e:
            rec["steps"].append({"name": name, "status": "실패", "ms": (time.perf_counter() - s) * 1000, "data": None})
            rec["error_code"], rec["error_message"], rec["candidates"], rec["candidate_sources"] = e.code, e.message, e.candidates, e.sources
            raise

    try:
        if task not in TASKS:
            raise FinError("INVALID_TASK", f"지원하지 않는 작업입니다: {task}")
        cur = step("당기 데이터 조회", lambda: fetch(company, year))
        res = {"company": cur["company"], "year": year, "basis": cur["basis"], "unit": cur["unit"],
               "revenue": cur["revenue"], "operating_profit": cur["operating_profit"],
               "rcept_no": cur["rcept_no"], "fetched_at": cur["fetched_at"]}
        if task == "영업이익률 계산":
            res["operating_margin_pct"] = step("영업이익률 계산", lambda: operating_margin(cur))
        elif task == "매출 성장률 계산":
            prev = step("전기 데이터 조회", lambda: fetch(cur["company"], year - 1, cur["basis"]))
            res["prev_revenue"] = prev["revenue"]
            res["revenue_growth_pct"] = step("매출 성장률 계산", lambda: revenue_growth(cur, prev))
        rec["result"] = res
    except FinError:
        if rec["error_code"] == "COMPANY_NOT_FOUND" and candidates_fn:  # 후보에 별칭·AI 제안을 합친다(확정은 사용자)
            s0 = time.perf_counter()
            try:
                rec["candidates"], rec["candidate_sources"], ai = candidates_fn(company, suggest=suggest)
                rec["error_message"] = f"상장사 '{company.strip()}'을(를) 찾지 못했습니다." + (f" 혹시 {', '.join(rec['candidates'])} 중 하나인가요?" if rec["candidates"] else "")
                if ai is not None:
                    rec["steps"].append({"name": "회사 후보 제안 (AI, 목록 검증)", "status": "실패" if ai.get("error") else "성공",
                                         "ms": (time.perf_counter() - s0) * 1000,
                                         "data": {"제안": ai["proposed"], "목록에 있는 것": ai["verified"], "AI 분류": ai.get("kind")}})
                    if ai.get("kind") in KIND_LABEL and not rec["candidates"]:  # 후보 없이 해외·비상장으로 분류된 경우만 지원 불가로 안내
                        rec["error_code"] = "COMPANY_NOT_SUPPORTED"
                        rec["error_message"] = (f"'{company.strip()}'은(는) {KIND_LABEL[ai["kind"]]}으로 보여 OpenDART 상장사 공시로 조회할 수 없습니다. "
                                                "한국 상장사인데 잘못 판단했다면 정식 회사명으로 다시 입력해 주세요.")
            except FinError:
                pass  # 후보 보강 실패는 기존 코드 후보로 되묻는다
    # 표시 시간은 이번 실행의 OpenDART 조회·계산 시간이며 성능 평가가 아니다.
    rec["total_ms"] = (time.perf_counter() - t0) * 1000
    return rec


@traceable(name="ask", run_type="chain", process_inputs=lambda i: {"text": i["text"]})
def ask(text, parse=parse_question, suggest=suggest_companies):
    """자연어 질문 -> 해석 -> run. 해석이 불완전하면 추측하지 않고 빠진 필드를 알려 주며 멈춘다."""
    s = time.perf_counter()
    try:
        p = parse(text)
        missing = [k for k in ("company", "year", "task") if p["parsed"][k] is None]
        if missing:
            labels = {"company": "기업(한 곳)", "year": "사업연도(4자리)", "task": "지원하는 작업(실적 조회·영업이익률·매출 성장률)"}
            raise FinError("QUESTION_INCOMPLETE", "질문에서 확인하지 못한 항목: " + ", ".join(labels[k] for k in missing))
    except FinError as e:
        return {"run_id": uuid.uuid4().hex[:8], "started_at": datetime.now().isoformat(timespec="seconds"),
                "data_kind": DATA_KIND, "inputs": {"질문": text}, "result": None, "error_code": e.code, "error_message": e.message,
                "steps": [{"name": "질문 해석", "status": "실패", "ms": (time.perf_counter() - s) * 1000, "data": None}],
                "total_ms": (time.perf_counter() - s) * 1000}
    rec = run(p["parsed"]["task"], p["parsed"]["year"], p["parsed"]["company"], suggest=suggest)
    rec["inputs"] = {"질문": text, **rec["inputs"]}
    rec["steps"].insert(0, {"name": f"질문 해석 ({p['model']})", "status": "성공", "ms": p["ms"], "data": p["parsed"]})
    rec["total_ms"] = (time.perf_counter() - s) * 1000
    return rec


def pick_company(rec, name, fetch=fetch_financials):
    """되묻기에서 사용자가 후보를 고르면 같은 연도·작업으로 다시 실행한다(선택은 사용자가 확정)."""
    i = rec["inputs"]
    new = run(i["작업"], i["사업연도"], name, fetch=fetch)
    if "질문" in i:
        new["inputs"] = {"질문": i["질문"], **new["inputs"]}
    new["steps"].insert(0, {"name": "회사 후보 선택 (사용자 확인)", "status": "성공", "ms": 0.0, "data": {"입력": i["기업"], "선택": name}})
    return new
