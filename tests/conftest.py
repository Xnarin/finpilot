"""테스트 실행은 LangSmith로 trace를 보내지 않는다(단위 테스트가 월 한도를 소모하지 않게)."""
import os

os.environ["LANGSMITH_TRACING"] = "false"
