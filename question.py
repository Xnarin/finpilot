"""자연어 질문 -> {기업, 연도, 작업} 해석(Gemini). LLM은 해석만 하고 금융 수치는 다루지 않는다."""
import os
import time
from typing import Literal, Optional

from pydantic import BaseModel, ValidationError

from dart import FinError, load_env

load_env()  # LangSmith SDK가 첫 추적 호출 전에 .env의 LANGSMITH_*를 읽도록 import 시점에 채운다
from langsmith import traceable  # noqa: E402

MODEL = "gemini-3.5-flash-lite"
TASKS = ["실적 조회", "영업이익률 계산", "매출 성장률 계산"]

PROMPT = """너는 한국 상장사 재무 질문에서 조회 조건을 추출하는 분류기다. 숫자나 사실을 답하지 말고 JSON만 낸다.
- company: 질문에 쓰인 회사명을 쓰인 그대로(약칭·띄어쓰기 보정 금지). 회사가 없거나 둘 이상이면 null.
- year: 질문에 명시된 4자리 사업연도. "작년·올해"처럼 상대적 표현이거나 연도가 없으면 null. 두 연도를 비교하는 질문이면 더 최근 연도.
- task: 아래 셋 중 하나, 해당하지 않으면 null.
  "실적 조회": 매출액·영업이익 값을 보여 달라는 요청
  "영업이익률 계산": 영업이익률(영업이익이 매출에서 차지하는 비율)
  "매출 성장률 계산": 전년 대비 매출 증가·성장률
  주가 예측, 투자 판단·추천, 그 밖의 요청은 null.
  한 번에 하나의 작업만 지원한다: 둘 이상의 작업을 함께 요청했거나 두 연도 중 어느 쪽이 더 높은지 묻는 질문이면 task만 null로 하고 company·year는 위 규칙대로 채운다. 회사가 둘 이상이면 company만 null이고 task는 요청 내용대로 추출한다. "전년 대비 몇 % 늘었나"는 매출 성장률이다.
확실하지 않은 필드는 추측하지 말고 null로 둔다."""


class Parsed(BaseModel):
    company: Optional[str] = None
    year: Optional[int] = None
    task: Optional[Literal["실적 조회", "영업이익률 계산", "매출 성장률 계산"]] = None


def call_gemini(text):
    from google import genai
    from google.genai import types
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])  # 변수에 유지해야 호출 중 닫히지 않는다
        resp = client.models.generate_content(
            model=MODEL, contents=text,
            config=types.GenerateContentConfig(system_instruction=PROMPT, temperature=0, response_mime_type="application/json",
                                               response_json_schema=Parsed.model_json_schema()))
        u = resp.usage_metadata
        return resp.text, {"input_tokens": u.prompt_token_count, "output_tokens": u.candidates_token_count, "total_tokens": u.total_token_count}
    except KeyError:
        raise FinError("NO_API_KEY", "GEMINI_API_KEY가 설정되지 않았습니다.") from None
    except Exception as e:  # 예외 문자열에 요청 정보가 섞일 수 있어 종류만 보고한다
        raise FinError("LLM_ERROR", f"질문 해석 호출에 실패했습니다 ({type(e).__name__}).") from None


@traceable(name="parse_question", run_type="llm", metadata={"model": MODEL}, process_inputs=lambda i: {"text": i["text"]})
def parse_question(text, _llm=call_gemini):
    """{"parsed": {company, year, task}, "model", "ms"} 반환. 빠진 필드는 None(판단은 호출자)."""
    t0 = time.perf_counter()
    out = _llm(text)
    raw, usage = out if isinstance(out, tuple) else (out, None)  # 테스트용 가짜 LLM은 문자열만 돌려줘도 된다
    try:
        parsed = Parsed.model_validate_json(raw)
    except ValidationError:
        raise FinError("LLM_BAD_OUTPUT", "질문 해석 결과가 정해진 형식이 아닙니다.") from None
    return {"parsed": parsed.model_dump(), "model": MODEL, "ms": (time.perf_counter() - t0) * 1000, "usage": usage}


SUGGEST_PROMPT = """한국 상장사의 별칭·약칭·영문명을 OpenDART에 등록된 정식 상장사명으로 바꾼 후보를 최대 3개 낸다(names). 해외·비상장 회사이거나 짐작할 수 없으면 빈 목록을 낸다. 지어내지 말고, 확실한 것만 적는다.
입력 그대로 다시 적지 말고 정식 상장사명으로 바꾼다.
추가로 입력이 가리키는 회사의 종류를 kind로 분류한다: korean_listed(한국 상장사), foreign(해외 기업), korean_unlisted(한국 비상장 기업), unclear(여러 회사가 가능하거나 모름). 한국에 상장된 회사가 아니라고 확신할 때만 foreign 또는 korean_unlisted로 한다."""


class Suggestion(BaseModel):
    names: list[str] = []
    kind: Literal["korean_listed", "foreign", "korean_unlisted", "unclear"] = "unclear"


def call_suggest(name):
    from google import genai
    from google.genai import types
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        return client.models.generate_content(model=MODEL, contents=name, config=types.GenerateContentConfig(
            system_instruction=SUGGEST_PROMPT, temperature=0, response_mime_type="application/json",
            response_json_schema=Suggestion.model_json_schema())).text
    except Exception as e:  # 실패해도 코드 후보만으로 되묻는다. 종류만 보고한다
        raise FinError("LLM_ERROR", f"회사 후보 제안 호출에 실패했습니다 ({type(e).__name__}).") from None


@traceable(name="suggest_companies", run_type="llm", metadata={"model": MODEL}, process_inputs=lambda i: {"name": i["name"]})
def suggest_companies(name, corps, _llm=call_suggest):
    """LLM이 낸 후보 중 상장사 목록에 정확히 있는 이름만 남긴다. 목록에 없는 제안은 버린다."""
    try:
        s = Suggestion.model_validate_json(_llm(name))
        proposed, kind = s.names[:3], s.kind
    except (FinError, ValidationError):
        return {"proposed": [], "verified": [], "kind": "unclear", "error": True}
    listed = {c[1] for c in corps}
    return {"proposed": proposed, "verified": [p for p in dict.fromkeys(proposed) if p in listed], "kind": kind}
