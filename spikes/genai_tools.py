"""스파이크(2026-10-19): 설계 확인용 일회성 시험 스크립트. 실행에는 requirements.txt 외에 langgraph, langchain, langchain-google-genai가 필요하다(아직 requirements.txt에 넣지 않음). Gemini와 OpenDART를 실제로 호출한다."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LANGSMITH_TRACING"] = "false"
from dart import load_env
load_env()
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3.5-flash-lite"

get_fin = types.FunctionDeclaration(
    name="get_financials",
    description="회사의 연간 매출·영업이익 조회",
    parameters_json_schema={"type": "object", "properties": {"company": {"type": "string"}, "year": {"type": "integer"}}, "required": ["company", "year"]},
)
tool = types.Tool(function_declarations=[get_fin])


def show(label, resp):
    parts = resp.candidates[0].content.parts
    out = []
    for p in parts:
        if p.function_call:
            out.append(("CALL", p.function_call.name, dict(p.function_call.args)))
        elif p.text:
            out.append(("TEXT", p.text[:80]))
    print(label, out, "| usage", resp.usage_metadata.prompt_token_count, resp.usage_metadata.candidates_token_count)


# 1) 도구 호출만
r = client.models.generate_content(model=MODEL, contents="삼성전자와 SK하이닉스 2024년 매출 알려줘",
                                   config=types.GenerateContentConfig(tools=[tool], temperature=0))
show("1 tools only:", r)

# 2) 도구 + 구조화 출력(JSON) 동시
try:
    r = client.models.generate_content(model=MODEL, contents="삼성전자 2024년 매출 알려줘", config=types.GenerateContentConfig(
        tools=[tool], temperature=0, response_mime_type="application/json",
        response_json_schema={"type": "object", "properties": {"answer": {"type": "string"}}}))
    show("2 tools + json schema:", r)
except Exception as e:
    print("2 tools + json schema: ERROR", type(e).__name__, str(e)[:300])

# 3) 도구 결과를 돌려주는 2턴 루프
msgs = [types.Content(role="user", parts=[types.Part(text="삼성전자 2024년 매출 알려줘")])]
r = client.models.generate_content(model=MODEL, contents=msgs, config=types.GenerateContentConfig(tools=[tool], temperature=0))
fc = r.candidates[0].content.parts[0].function_call
msgs.append(r.candidates[0].content)
msgs.append(types.Content(role="user", parts=[types.Part.from_function_response(name=fc.name, response={"status": "ok", "revenue": 300870903000000})]))
r2 = client.models.generate_content(model=MODEL, contents=msgs, config=types.GenerateContentConfig(tools=[tool], temperature=0))
show("3 after tool result:", r2)
