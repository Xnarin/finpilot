import pytest

from dart import CHOSUNG_FAMOUS, FAMOUS, FinError, _chosung, _chosung_ko, candidate_list, famous_match, find_company

CORPS = [["1", "삼성전자", "005930", ""], ["2", "삼성전기", "009150", ""], ["3", "SK하이닉스", "000660", "SK hynix Inc."], ["4", "NAVER", "035420", ""],
         ["5", "현대자동차", "005380", ""], ["6", "카카오뱅크", "323410", ""], ["7", "삼성중공업", "010140", ""]]


@pytest.mark.parametrize("alias, expected", [("삼전", "삼성전자"), ("하닉", "SK하이닉스"), ("닉스", "SK하이닉스"), ("하이닉스", "SK하이닉스"),
                                             ("현차", "현대자동차"), ("현대차", "현대자동차"), ("네이버", "NAVER"), ("카뱅", "카카오뱅크"), (" 삼 전 ", "삼성전자")])
def test_famous_aliases_resolve_directly(alias, expected):
    assert find_company(alias, CORPS)[1] == expected


@pytest.mark.parametrize("name", ["삼성", "현대", "엘지", "포스코", "SK", "하이", "카카오"])
def test_ambiguous_or_short_names_are_never_confirmed_by_famous_table(name):
    assert famous_match(name, CORPS) is None


def test_ambiguous_short_names_are_not_in_the_famous_table():
    for bad in ("삼성", "현대", "엘지", "포스코", "한화", "롯데", "두산", "sk", "lg"):
        assert bad not in FAMOUS and bad not in CHOSUNG_FAMOUS


def test_famous_alias_is_not_used_when_target_missing_or_duplicated():
    assert famous_match("삼전", [c for c in CORPS if c[1] != "삼성전자"]) is None
    assert famous_match("삼전", CORPS + [["99", "삼성전자", "000001", ""]]) is None      # 같은 이름이 둘이면 확정하지 않음


def test_exact_name_takes_precedence_over_famous_table():
    corps = CORPS + [["8", "닉스", "111111", ""]]                                        # 실제로 '닉스'라는 회사가 있으면 그 회사
    assert find_company("닉스", corps)[0] == "8"


def test_chosung_of_full_name_resolves_only_when_unique_in_list():
    assert find_company("ㅅㅅㅈㅈ", CORPS)[1] == "삼성전자"
    assert find_company("ㅎㄷㅈㄷㅊ", CORPS)[1] == "현대자동차"
    assert find_company("ㅎㅇㄴㅅ", CORPS)[1] == "SK하이닉스"
    clash = CORPS + [["99", "소소지주", "000002", ""]]                                    # 초성이 ㅅㅅㅈㅈ로 겹치는 다른 회사가 있으면 확정하지 않음
    assert _chosung("소소지주") == "ㅅㅅㅈㅈ" and famous_match("ㅅㅅㅈㅈ", clash) is None


def test_unknown_chosung_gives_candidates_only():
    with pytest.raises(FinError) as e:
        find_company("ㅅㅅㅈㄱㅇ", CORPS)
    assert e.value.code == "COMPANY_NOT_FOUND" and e.value.sources.get("삼성중공업") == "초성 일치"


def test_chosung_function_handles_mixed_text():
    assert _chosung("SK하이닉스") == "skㅎㅇㄴㅅ" and _chosung("삼성 전자") == "ㅅㅅㅈㅈ"
    assert _chosung_ko("SK하이닉스") == "ㅎㅇㄴㅅ"      # 영문 접두어를 뺀 한글 초성


def test_famous_names_never_shadow_candidates_for_other_inputs():
    assert [c for c, _ in candidate_list("삼성", CORPS)][:3] != []
