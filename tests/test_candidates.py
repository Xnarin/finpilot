import pytest

from dart import ALIASES, candidate_list, find_company, FinError
from finance import AI_SOURCE, candidates_for, run
from question import suggest_companies

# [고유번호, 회사명, 종목코드, 영문명]
CORPS = [
    ["1", "삼성전자", "005930", "SAMSUNG ELECTRONICS CO.,LTD."],
    ["2", "삼성전기", "009150", "SAMSUNG ELECTRO-MECHANICS CO.,LTD."],
    ["3", "SK하이닉스", "000660", "SK hynix Inc."],
    ["4", "NAVER", "035420", "NAVER Corporation"],
    ["5", "현대자동차", "005380", "Hyundai Motor Company"],
    ["6", "삼성전자서비스", "000001", ""],
    ["9", "POSCO홀딩스", "005490", "POSCO Holdings Inc."],
    ["10", "포스코퓨처엠", "003670", "POSCO FUTURE M"],
]


def test_alias_comes_first_with_source():
    assert candidate_list("포스코", CORPS)[0] == ("POSCO홀딩스", "별칭 사전")      # 모호한 별칭은 후보로만


def test_alias_target_missing_from_list_is_not_suggested():
    assert "POSCO홀딩스" not in [c for c, _ in candidate_list("포스코", [c for c in CORPS if c[1] != "POSCO홀딩스"])]


def test_preferred_stock_maps_to_common_stock_company_with_note():
    assert candidate_list("삼성전자우", CORPS)[0] == ("삼성전자", "우선주 → 해당 회사 재무제표")
    assert candidate_list("삼성전자2우B", CORPS)[0][0] == "삼성전자"


def test_english_name_candidates():
    assert candidate_list("Samsung Electronics", CORPS)[0] == ("삼성전자", "영문명")
    assert candidate_list("sk hynix", CORPS)[0][0] == "SK하이닉스"
    assert candidate_list("Tesla Motors", CORPS) == []               # 해외 회사는 후보 없음


def test_formatting_only_difference_is_still_accepted_directly():
    assert find_company("sk 하이닉스", [c for c in CORPS]) == ("3", "SK하이닉스")


def test_alias_is_never_auto_confirmed():
    with pytest.raises(FinError) as e:
        find_company("포스코", CORPS)
    assert e.value.code == "COMPANY_NOT_FOUND" and e.value.candidates[0] == "POSCO홀딩스"
    assert e.value.sources["POSCO홀딩스"] == "별칭 사전"


def test_all_alias_keys_are_normalized_form():
    assert all(k == k.casefold() and " " not in k for k in ALIASES)


def test_ai_suggestions_are_verified_against_official_list():
    out = suggest_companies("하닉", CORPS, _llm=lambda n: '{"names": ["SK하이닉스", "에스케이하이닉스", "없는회사"]}')
    assert out["proposed"] == ["SK하이닉스", "에스케이하이닉스", "없는회사"]
    assert out["verified"] == ["SK하이닉스"]          # 목록에 정확히 있는 것만 남김


def test_ai_suggestion_failure_or_bad_output_is_harmless():
    def boom(n):
        raise FinError("LLM_ERROR", "x")
    assert suggest_companies("x", CORPS, _llm=boom) == {"proposed": [], "verified": [], "kind": "unclear", "error": True}
    assert suggest_companies("x", CORPS, _llm=lambda n: "not json")["verified"] == []


def test_candidates_for_order_alias_then_ai_then_rest_with_sources():
    names, src, ai = candidates_for("포스코", CORPS, suggest=lambda n, c: {"proposed": ["포스코퓨처엠"], "verified": ["포스코퓨처엠"]})
    assert names[:2] == ["POSCO홀딩스", "포스코퓨처엠"]
    assert src["POSCO홀딩스"] == "별칭 사전" and src["포스코퓨처엠"] == AI_SOURCE


def test_run_adds_candidates_and_ai_step_but_never_picks_one():
    def f(company, year, basis="연결"):
        raise FinError("COMPANY_NOT_FOUND", "없음", [], {})
    cf = lambda name, suggest=None: candidates_for(name, CORPS, suggest=suggest)
    r = run("실적 조회", 2024, "포스코", fetch=f, suggest=lambda n, c: {"proposed": ["POSCO홀딩스"], "verified": ["POSCO홀딩스"]}, candidates_fn=cf)
    assert r["error_code"] == "COMPANY_NOT_FOUND" and r["result"] is None      # 자동으로 회사를 고르지 않는다
    assert r["candidates"][0] == "POSCO홀딩스" and r["candidate_sources"]["POSCO홀딩스"] == "별칭 사전"
    assert r["steps"][-1]["name"].startswith("회사 후보 제안") and r["steps"][-1]["data"]["목록에 있는 것"] == ["POSCO홀딩스"]


APPLE_CORPS = CORPS + [["7", "애니플러스", "310200", "Aniplus Inc."], ["8", "비디아이", "148780", "VIDI"]]


def ai(kind, verified=()):
    return lambda n, c: {"proposed": list(verified), "verified": list(verified), "kind": kind}


def test_weak_candidates_exist_without_ai_classification():
    # 애플 -> 약칭 추정으로 애니플러스가 나오는 소음의 원인(AI 분류가 없을 때)
    assert [c for c, _ in candidate_list("애플", APPLE_CORPS)] == ["애니플러스"]
    assert candidates_for("애플", APPLE_CORPS)[0] == ["애니플러스"]
    assert candidates_for("애플", APPLE_CORPS, suggest=ai("unclear"))[0] == ["애니플러스"]


def test_foreign_classification_drops_weak_candidates():
    for kind in ("foreign", "korean_unlisted"):
        assert candidates_for("애플", APPLE_CORPS, suggest=ai(kind))[0] == []


def test_foreign_classification_keeps_strong_candidates():
    # 별칭 사전·영문명·AI 확인 후보는 AI가 해외라고 해도 지우지 않는다(사용자가 확인)
    assert candidates_for("포스코", CORPS, suggest=ai("foreign"))[0][0] == "POSCO홀딩스"
    assert candidates_for("Samsung Electronics", CORPS, suggest=ai("foreign"))[0][0] == "삼성전자"


def test_run_reports_unsupported_company_with_reason_and_no_buttons():
    def f(company, year, basis="연결"):
        raise FinError("COMPANY_NOT_FOUND", "없음", [], {})
    cf = lambda name, suggest=None: candidates_for(name, APPLE_CORPS, suggest=suggest)
    r = run("실적 조회", 2024, "애플", fetch=f, suggest=ai("foreign"), candidates_fn=cf)
    assert r["error_code"] == "COMPANY_NOT_SUPPORTED" and "해외 기업" in r["error_message"] and r["candidates"] == []
    assert r["steps"][-1]["data"]["AI 분류"] == "foreign"


def test_run_keeps_not_found_with_candidates_when_ai_says_unclear():
    def f(company, year, basis="연결"):
        raise FinError("COMPANY_NOT_FOUND", "없음", [], {})
    cf = lambda name, suggest=None: candidates_for(name, APPLE_CORPS, suggest=suggest)
    r = run("실적 조회", 2024, "애플", fetch=f, suggest=ai("unclear"), candidates_fn=cf)
    assert r["error_code"] == "COMPANY_NOT_FOUND" and r["candidates"] == ["애니플러스"]
