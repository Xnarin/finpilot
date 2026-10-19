import pytest

from agent_core import DECLINE_TEXT, build_graph, chat
from tests.fakes import FakeFinancials, ScriptedChat, ai, call, deps


def run(script, *texts, d=None):
    """가짜 LLM 응답 스크립트로 에이전트를 돌려 턴마다의 응답을 돌려준다."""
    llm = ScriptedChat(script=list(script))
    graph = build_graph(llm, d or deps())
    replies = [chat(graph, "t1", t) for t in texts]
    assert llm.idx == len(script), f"스크립트 {len(script)}개 중 {llm.idx}개만 소비됨"
    return replies, llm


def happy(text="삼전 2024 영업이익률", sentence="영업이익률을 정리했어요."):
    return [
        ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
        ai(call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)),
        ai(text=sentence),
    ]


# ---------------- 정상 흐름과 답변 조립
def test_happy_path_numbers_come_from_code_not_llm():
    (r,), _ = run(happy(), "삼전 2024 영업이익률 알려줘")
    row = r["rows"][0]
    assert (row["company"], row["year"], row["basis"], row["revenue"], row["operating_profit"]) == ("삼성전자", 2024, "연결", 300_870_903, 32_725_961)
    assert row["operating_margin_pct"] == pytest.approx(10.88, abs=0.01)
    assert r["interpretations"] == ["'삼전'을(를) 삼성전자(으)로 해석했습니다."]
    assert r["sentence"] == "영업이익률을 정리했어요." and not r["ask"] and not r["decline"]
    assert [e["tool"] for e in r["tool_log"]] == ["resolve_company", "resolve_years", "compute_ratio"]


def test_sentence_with_any_digit_is_dropped_but_table_stays():
    (r,), _ = run(happy(sentence="영업이익률은 10.9%예요."), "삼전 2024 영업이익률")
    assert r["sentence"] is None and r["sentence_dropped_for_digits"] and r["rows"]


def test_multiple_companies_in_one_turn_and_growth():
    script = [
        ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_company", name="닉스", evidence="닉스"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
        ai(call("compute_ratio", metric="revenue_growth", corp_code="1", year=2024), call("compute_ratio", metric="revenue_growth", corp_code="2", year=2024)),
        ai(text="두 회사의 매출 성장률이에요."),
    ]
    (r,), _ = run(script, "삼전이랑 닉스 2024 매출 성장률")
    assert {row["company"] for row in r["rows"]} == {"삼성전자", "SK하이닉스"}
    g = {row["company"]: row["revenue_growth_pct"] for row in r["rows"]}
    assert g["삼성전자"] == pytest.approx(16.20, abs=0.01) and g["SK하이닉스"] == pytest.approx(102.02, abs=0.01)


# ---------------- 조용한 추측 방지(근거 인용)
def test_year_not_said_by_user_is_rejected_and_llm_must_ask():
    script = [
        ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="relative", expr="올해", evidence="올해")),   # 사용자는 올해라고 말하지 않음
        ai(call("ask_user", missing=["year"])),
    ]
    (r,), _ = run(script, "삼전 영업이익률 알려줘")
    assert r["ask"]["missing"] == ["year"] and "사업연도" in r["ask"]["text"] and not r["rows"]
    guard = [e for e in r["tool_log"] if e["tool"] == "resolve_years"][0]
    assert guard["code"] == "GUARD_NO_EVIDENCE"
    assert r["notices"] == []                  # 검증 오류는 사용자에게 보이지 않는다


def test_company_not_said_by_user_is_rejected():
    script = [ai(call("resolve_company", name="삼성전자", evidence="삼성전자")), ai(call("ask_user", missing=["company"]))]
    (r,), _ = run(script, "2024 영업이익률 알려줘")
    assert r["ask"]["missing"] == ["company"]
    assert [e["code"] for e in r["tool_log"]][0] == "GUARD_NO_EVIDENCE"


def test_year_must_come_from_resolve_years_and_company_must_be_resolved():
    script = [
        ai(call("get_financials", corp_code="1", year=2024)),                     # 아직 회사·연도를 확정하지 않음
        ai(call("resolve_company", name="삼전", evidence="삼전")),
        ai(call("get_financials", corp_code="1", year=2024)),                     # 연도를 resolve_years로 확정하지 않음
        ai(call("ask_user", missing=["year"])),
    ]
    (r,), _ = run(script, "삼전 실적")
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "get_financials"] == ["GUARD_UNRESOLVED_COMPANY", "GUARD_YEAR_NOT_RESOLVED"]


def test_separate_basis_only_when_user_said_so():
    d = deps()
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("get_financials", corp_code="1", year=2024, basis="별도")),
              ai(call("get_financials", corp_code="1", year=2024)),
              ai(text="조회했어요.")]
    (r,), _ = run(script, "삼전 2024 실적", d=d)
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "get_financials"][0] == "GUARD_BASIS_NOT_REQUESTED"
    assert d.fin.calls == [("1", 2024, "연결", "연간")]


def test_separate_basis_is_allowed_when_user_asked():
    d = deps()
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("get_financials", corp_code="1", year=2024, basis="별도")), ai(text="조회했어요.")]
    (r,), _ = run(script, "삼전 2024 별도 기준 실적", d=d)
    assert d.fin.calls == [("1", 2024, "별도", "연간")] and r["rows"][0]["basis"] == "별도"


def test_quarter_request_is_refused_with_tool_message_not_annual_value():
    d = deps()
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("get_financials", corp_code="1", year=2024, period="분기")), ai(text="분기는 지원하지 않아요.")]
    (r,), _ = run(script, "삼전 2024년 1분기 영업이익", d=d)
    assert not r["rows"] and any("분기" in n for n in r["notices"])
    assert d.fin.calls == [("1", 2024, "연결", "분기")] or d.fin.calls[0][3] == "분기"


def test_quarter_period_without_user_asking_is_guarded():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("get_financials", corp_code="1", year=2024, period="분기")), ai(call("ask_user", missing=["task"]))]
    (r,), _ = run(script, "삼전 2024 영업이익", d=deps())
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "get_financials"] == ["GUARD_PERIOD_NOT_REQUESTED"]


def test_invalid_enum_argument_returns_guard_error_to_llm():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("get_financials", corp_code="1", year=2024, basis="CFS")),
              ai(call("get_financials", corp_code="1", year=2024)), ai(text="됐어요.")]
    (r,), llm = run(script, "삼전 2024 실적")
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "get_financials"][0] == "GUARD_INVALID_ARGS" and r["rows"]


# ---------------- 도구가 준 이유는 코드가 그대로, 거절·되묻기 문구는 템플릿
def test_unsupported_company_message_comes_from_tool_not_llm():
    script = [ai(call("resolve_company", name="애플", evidence="애플")), ai(text="조회할 수 없어요.")]
    (r,), _ = run(script, "애플 2024 영업이익")
    assert any("해외 기업" in n for n in r["notices"]) and not r["rows"]


def test_year_not_published_is_shown_to_user_with_latest_year():
    script = [ai(call("resolve_years", kind="relative", expr="올해", evidence="올해")), ai(call("ask_user", missing=["year"]))]
    (r,), _ = run(script, "삼성전자 올해 영업이익률")
    assert any("아직 나오지 않았" in n and "2025" in n for n in r["notices"])


@pytest.mark.parametrize("reason", sorted(DECLINE_TEXT))
def test_decline_uses_fixed_template(reason):
    (r,), _ = run([ai(call("decline", reason=reason))], "아무 말")
    assert r["decline"] == {"reason": reason, "text": DECLINE_TEXT[reason]} and not r["rows"]


def test_ask_user_collects_all_missing_into_one_template_question():
    (r,), _ = run([ai(call("ask_user", missing=["company", "year", "task", "year"]))], "영업이익률")
    assert r["ask"]["missing"] == ["company", "year", "task"] and r["ask"]["text"].startswith("다음을 알려 주세요: 어느 회사인지, 어느 사업연도인지")


def test_candidates_are_given_to_the_ui_when_asking_user_to_choose():
    script = [ai(call("resolve_company", name="포스코", evidence="포스코")), ai(call("ask_user", missing=["candidate", "year"]))]
    (r,), _ = run(script, "포스코 영업이익률")
    assert r["ask"]["candidates"] == [{"name": "POSCO홀딩스", "stock_code": "005490", "source": "별칭 사전"}]
    assert r["ask"]["missing"] == ["candidate", "year"]


def test_partial_results_first_then_ask_in_the_same_reply():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_company", name="포스코", evidence="포스코"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)),
              ai(call("ask_user", missing=["candidate"]))]
    (r,), _ = run(script, "삼전이랑 포스코 2024 영업이익률")
    assert r["rows"][0]["company"] == "삼성전자" and r["ask"]["candidates"][0]["name"] == "POSCO홀딩스"


# ---------------- 한도·중복·오류
def test_duplicate_calls_use_cache_and_hit_opendart_once():
    d = deps()
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("get_financials", corp_code="1", year=2024), call("get_financials", corp_code="1", year=2024),
                 call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)),
              ai(text="됐어요.")]
    (r,), _ = run(script, "삼전 2024 영업이익률 실적", d=d)
    assert d.fin.calls == [("1", 2024, "연결", "연간")]
    assert [e["cached"] for e in r["tool_log"] if e["tool"] == "get_financials"] == [False, True]


def test_request_limit_is_enforced_without_silent_truncation():
    d = deps(max_requests=1)
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_company", name="닉스", evidence="닉스"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("compute_ratio", metric="operating_margin", corp_code="1", year=2024), call("compute_ratio", metric="operating_margin", corp_code="2", year=2024)),
              ai(text="일부만 했어요.")]
    (r,), _ = run(script, "삼전 닉스 2024 영업이익률", d=d)
    assert len(r["rows"]) == 1 and r["limit_hit"] and any("한도" in n or "넘었" in n for n in r["notices"])
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "compute_ratio"] == [None, "REQUEST_LIMIT"]


def test_call_limit_stops_the_loop_and_tells_the_user():
    d = deps(max_calls=3)
    script = [ai(call("resolve_company", name="삼전", evidence="삼전")), ai(call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("resolve_years", kind="explicit", values=[2023], evidence="2024")), ai(call("resolve_years", kind="explicit", values=[2022], evidence="2024"))]
    (r,), _ = run(script, "삼전 2024", d=d)
    assert r["limit_hit"] and r["calls"] == 4 and any("한도" in n or "넘었" in n for n in r["notices"])


def test_llm_failure_is_reported_without_exception_details():
    llm = ScriptedChat(script=[RuntimeError("secret-key-in-url")])
    graph = build_graph(llm, deps())
    r = chat(graph, "t", "삼전 2024 영업이익률")
    assert r["llm_error"] == "RuntimeError" and not r["rows"] and "secret" not in str(r)


def test_transient_fetch_errors_are_not_cached():
    class Flaky(FakeFinancials):
        n = 0

        def __call__(self, *a, **k):
            self.n += 1
            if self.n == 1:
                return {"status": "error", "code": "NETWORK_ERROR", "message": "일시 오류"}
            return super().__call__(*a, **k)
    d = deps(fin=Flaky())
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("get_financials", corp_code="1", year=2024)), ai(call("get_financials", corp_code="1", year=2024)), ai(text="됐어요.")]
    (r,), _ = run(script, "삼전 2024 실적", d=d)
    assert d.fin.n == 2 and r["rows"]            # 첫 일시 오류는 캐시되지 않아 다시 조회했다


# ---------------- 대화 이어받기
def test_followup_inherits_year_and_task_and_marks_it():
    script = happy() + [
        ai(call("resolve_company", name="닉스", evidence="닉스"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
        ai(call("compute_ratio", metric="operating_margin", corp_code="2", year=2024)),
        ai(text="이어서 정리했어요."),
    ]
    (r1, r2), llm = run(script, "삼전 2024 영업이익률", "그럼 닉스는?")
    assert r2["rows"][0]["company"] == "SK하이닉스" and r2["carried"] == ["2024"]
    assert r1["carried"] == []
    roles = [type(m).__name__ for m in llm.seen[3]]
    assert "HumanMessage" in roles and roles.count("HumanMessage") == 2          # 두 번째 턴에는 이전 대화가 함께 전달된다


def test_answer_to_ask_user_continues_the_conversation():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전")), ai(call("ask_user", missing=["year"])),
              ai(call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)), ai(text="영업이익률이에요.")]
    (r1, r2), _ = run(script, "삼전 영업이익률", "2024")
    assert r1["ask"]["missing"] == ["year"] and r2["rows"][0]["operating_margin_pct"] == pytest.approx(10.88, abs=0.01)


def test_llm_only_chat_without_tools_returns_sentence_only():
    (r,), _ = run([ai(text="안녕하세요. 상장사 연간 재무를 조회해 드려요.")], "안녕")
    assert r["sentence"].startswith("안녕하세요") and not r["rows"] and not r["ask"]


def test_generic_off_topic_decline_is_suppressed_when_tool_already_gave_the_reason():
    script = [ai(call("resolve_company", name="애플", evidence="애플")), ai(call("decline", reason="OFF_TOPIC"))]
    (r,), _ = run(script, "애플 2024 영업이익")
    assert r["decline"] is None and any("해외 기업" in n for n in r["notices"])
    (r2,), _ = run([ai(call("decline", reason="OFF_TOPIC"))], "오늘 날씨")
    assert r2["decline"]["reason"] == "OFF_TOPIC"


# ---------------- 근거 인용이 실제로 해당 값에 대한 것인지(2026-10-19 평가에서 발견한 우회 방지)
def test_year_evidence_must_be_about_a_year_not_any_substring():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="relative", expr="올해", evidence="영업이익률")),   # 사용자 문장의 일부지만 연도 표현이 아님
              ai(call("ask_user", missing=["year"]))]
    (r,), _ = run(script, "삼전 영업이익률")
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "resolve_years"] == ["GUARD_BAD_EVIDENCE"] and r["ask"]["missing"] == ["year"]


@pytest.mark.parametrize("args, user", [
    (dict(kind="explicit", values=[2024], evidence="24년"), "삼전 24년 영업이익률"),
    (dict(kind="range", start=2023, end=2025, evidence="2023~2025"), "삼전 2023~2025 영업이익률"),
    (dict(kind="relative", expr="작년", evidence="작년"), "삼전 작년 영업이익률"),
    (dict(kind="relative", expr="재작년", evidence="재작년"), "삼전 재작년 영업이익률"),
    (dict(kind="recent", n=3, evidence="최근 3년"), "삼전 최근 3년 영업이익률"),
])
def test_valid_year_evidence_forms_are_accepted(args, user):
    script = [ai(call("resolve_years", **args)), ai(text="됐어요.")]
    (r,), _ = run(script, user)
    assert r["tool_log"][0]["status"] == "ok"


@pytest.mark.parametrize("args, user", [
    (dict(kind="explicit", values=[2024], evidence="삼전"), "삼전 2024 영업이익률"),            # 연도 숫자가 인용에 없음
    (dict(kind="relative", expr="작년", evidence="올해"), "삼전 올해 영업이익률"),              # 인용과 다른 상대 연도로 바꿈
    (dict(kind="recent", n=3, evidence="영업이익률"), "삼전 영업이익률"),
    (dict(kind="range", start=2023, end=2025, evidence="2023"), "삼전 2023 영업이익률"),        # 끝 연도 근거 없음
])
def test_year_evidence_that_does_not_match_the_year_is_rejected(args, user):
    script = [ai(call("resolve_years", **args)), ai(call("ask_user", missing=["year"]))]
    (r,), _ = run(script, user)
    assert r["tool_log"][0]["code"] == "GUARD_BAD_EVIDENCE"


def test_company_name_must_be_what_the_user_wrote():
    script = [ai(call("resolve_company", name="삼성전자", evidence="삼전")), ai(call("resolve_company", name="삼전", evidence="삼전")), ai(call("ask_user", missing=["year"]))]
    (r,), _ = run(script, "삼전 영업이익률")
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "resolve_company"][0] == "GUARD_NAME_EVIDENCE_MISMATCH"
    assert r["tool_log"][1]["status"] == "ok"


# ---------------- 지표를 말하지 않으면 지표를 정해서 조회하지 않는다
def _lookup_script(tool_call):
    return [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
            ai(tool_call), ai(call("ask_user", missing=["task"]))]


def test_metric_not_stated_blocks_lookup_and_forces_a_question():
    (r,), _ = run(_lookup_script(call("get_financials", corp_code="1", year=2024)), "삼전 2024")
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "get_financials"] == ["GUARD_TASK_NOT_STATED"] and r["ask"]["missing"] == ["task"] and not r["rows"]
    (r,), _ = run(_lookup_script(call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)), "삼전 2024")
    assert r["tool_log"][2]["code"] == "GUARD_TASK_NOT_STATED"


@pytest.mark.parametrize("user, tool_call", [
    ("삼전 2024 실적", call("get_financials", corp_code="1", year=2024)),
    ("삼전 2024 영업이익 얼마야", call("get_financials", corp_code="1", year=2024)),
    ("삼전 2024 영업이익률", call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)),
    ("삼전 2024 마진", call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)),
    ("삼전 2024 매출 성장률", call("compute_ratio", metric="revenue_growth", corp_code="1", year=2024)),
    ("삼전 2024 매출이 얼마나 늘었어", call("compute_ratio", metric="revenue_growth", corp_code="1", year=2024)),
])
def test_metric_stated_in_any_common_wording_passes(user, tool_call):
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")), ai(tool_call), ai(text="됐어요.")]
    (r,), _ = run(script, user)
    assert r["rows"]


def test_ratio_wrong_for_what_user_asked_is_blocked():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("compute_ratio", metric="revenue_growth", corp_code="1", year=2024)), ai(call("ask_user", missing=["task"]))]
    (r,), _ = run(script, "삼전 2024 영업이익률")
    assert r["tool_log"][2]["code"] == "GUARD_TASK_NOT_STATED"


def test_ask_candidate_without_candidates_is_guarded_and_must_resolve_first():
    script = [ai(call("ask_user", missing=["candidate"])),
              ai(call("resolve_company", name="포스코", evidence="포스코")), ai(call("ask_user", missing=["candidate"]))]
    (r,), _ = run(script, "포스코 영업이익률")
    assert [e["code"] for e in r["tool_log"] if e["tool"] == "ask_user"][0] == "GUARD_NO_CANDIDATES"
    assert r["ask"]["candidates"][0]["name"] == "POSCO홀딩스"


def test_company_resolved_but_never_shown_is_reported_not_silently_dropped():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_company", name="닉스", evidence="닉스"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)),     # 닉스를 빠뜨림
              ai(text="정리했어요.")]
    (r,), _ = run(script, "삼전이랑 닉스 2024 영업이익률")
    assert [x["company"] for x in r["rows"]] == ["삼성전자"] and any("SK하이닉스" in n and "만들지 못" in n for n in r["notices"])


def test_no_omission_notice_when_asking_or_when_a_notice_already_explains():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전")), ai(call("ask_user", missing=["year"]))]
    (r,), _ = run(script, "삼전 영업이익률")
    assert r["notices"] == []


def test_candidates_without_a_follow_up_question_get_an_automatic_ask():
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_company", name="포스코", evidence="포스코"), call("resolve_years", kind="explicit", values=[2024], evidence="2024")),
              ai(call("compute_ratio", metric="operating_margin", corp_code="1", year=2024)),
              ai(text="삼성전자만 정리했어요.")]            # 포스코 후보를 되묻지 않고 끝냄
    (r,), _ = run(script, "삼전이랑 포스코 2024 영업이익률")
    assert r["rows"][0]["company"] == "삼성전자" and r["ask"]["missing"] == ["candidate"] and r["ask"]["candidates"][0]["name"] == "POSCO홀딩스"


def test_user_can_pick_a_shown_candidate_by_ordinal_but_not_an_unshown_name():
    script = [ai(call("resolve_company", name="포스코", evidence="포스코")), ai(call("ask_user", missing=["candidate"])),
              ai(call("resolve_company", name="POSCO홀딩스", evidence="1번")),        # 후보 목록에 있는 이름을 서수로 고름
              ai(call("resolve_company", name="삼성전자", evidence="1번")),           # 후보에 없던 이름은 서수로 고를 수 없음
              ai(call("ask_user", missing=["company"]))]
    (r1, r2), _ = run(script, "포스코 영업이익률", "1번")
    codes = [e["code"] for e in r2["tool_log"] if e["tool"] == "resolve_company"]
    assert codes[0] != "GUARD_NAME_EVIDENCE_MISMATCH"                  # 후보 중 하나를 고른 것은 통과(가짜 조회기는 이 이름을 모르므로 NOT_FOUND)
    assert codes[-1] == "GUARD_NAME_EVIDENCE_MISMATCH"


def test_repeated_guard_errors_stop_the_loop_and_ask_the_user():
    bad = lambda: ai(call("get_financials", corp_code="9", year=2024))        # 확정되지 않은 회사 코드를 계속 시도
    script = [bad(), bad(), bad(), bad(), ai(text="여기까지 오면 안 된다")]
    (r,), llm = run(script[:4], "삼전 2024 영업이익")
    assert r["ask"]["text"].startswith("질문을 이해하지 못했어요") and not r["rows"] and llm.idx == 4


def test_graph_recursion_error_becomes_a_user_message_not_an_exception():
    from langgraph.errors import GraphRecursionError
    llm = ScriptedChat(script=[ai(call("resolve_years", kind="explicit", values=[2024], evidence="2024")) for _ in range(40)])
    graph = build_graph(llm, deps(max_calls=1000))
    import agent_core
    r = agent_core.chat(graph, "t", "삼전 2024 영업이익")
    assert r["llm_error"] == "GraphRecursionError" and r["ask"]["text"] and not r["rows"]


@pytest.mark.parametrize("user", ["삼전 2023 영업손실이야?", "삼전 2023 적자였어?", "삼전 2023 흑자야?"])
def test_loss_or_profit_wording_counts_as_stating_the_metric(user):
    script = [ai(call("resolve_company", name="삼전", evidence="삼전"), call("resolve_years", kind="explicit", values=[2023], evidence="2023")),
              ai(call("get_financials", corp_code="1", year=2023)), ai(text="조회했어요.")]
    (r,), _ = run(script, user)
    assert r["rows"] and r["rows"][0]["year"] == 2023
