# FinPilot — OpenDART 조회 + 질문 해석(Gemini)

상장사(회사명 입력) 사업보고서의 연간 매출액·영업이익을 OpenDART에서 조회하고, 영업이익률·매출 성장률을 계산하는 Streamlit 화면입니다. 질문 입력란에 자연어를 쓰면 Gemini가 기업·연도·작업만 추출하고, 숫자는 OpenDART 조회와 코드 계산으로만 구합니다. RAG는 아직 없습니다.

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## 설정

OpenDART 인증키를 환경변수 `DART_API_KEY` 또는 프로젝트 루트의 `.env`에 둡니다 (`.env.example` 참고). `.env`는 `.gitignore`에 포함되어 있으며 키는 화면·오류 메시지에 표시하지 않습니다.

```
DART_API_KEY=발급받은_키
GEMINI_API_KEY=발급받은_키
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=발급받은_키
LANGSMITH_PROJECT=finpilot-dev
```

## 실행

```bash
streamlit run chat_app.py     # 챗봇형(에이전트, LangGraph)
streamlit run app.py          # 입력 폼형(단일 요청 파이프라인, 기준선)
```

챗봇은 여러 회사·연도를 한 번에 묻고, 빠진 정보는 모아서 되묻고, 이전 대화의 조건을 이어받습니다. 숫자·표·되묻기·거절 문구는 코드가 만들고 LLM은 도구 선택과 짧은 설명 문장만 맡습니다. 설계는 `docs/backlog/agent_design.md`입니다.

## 테스트

```bash
python -m pytest              # 오프라인 단위 테스트
python -m pytest tests_live   # 실제 OpenDART 호출(키 필요), 사용자가 원문 대조한 수치와 비교
```

테스트는 가상·고정 응답을 사용하므로 네트워크와 키가 필요 없습니다. 통과해도 실제 OpenDART 연동 성공을 뜻하지는 않으며, 실제 연동은 화면 실행으로 확인합니다.

## 조회 기준

- 엔드포인트 `fnlttSinglAcntAll`, 사업보고서(11011), 연결재무제표(CFS)만 조회합니다. 연결 자료가 없어도 별도로 대체하지 않습니다.
- 매출액 `ifrs-full_Revenue`, 영업이익 `dart_OperatingIncomeLoss` (손익계산서 IS/CIS)를 계정 ID로 정확히 한 건 선택합니다. 후보가 0건 또는 2건 이상이면 오류입니다.
- 각 연도 사업보고서의 당기 금액만 사용합니다. 이듬해 보고서의 전기(재작성) 수치와 섞지 않습니다. 성장률의 전기 매출은 전년도 사업보고서의 당기 금액입니다.
- 통화는 KRW만 허용하고 금액은 원 단위 정수로 다룹니다. 타임아웃·네트워크 오류만 1회 재시도합니다.

## 회사 선택

- 정확한 상장사명을 입력합니다(예: `SK하이닉스`). 최초 실행 때 OpenDART `corpCode.xml`로 상장사 목록을 받아 `.cache/corp_codes.json`에 저장합니다(신규 상장·사명 변경 반영은 이 파일을 지우면 됩니다).
- 후보는 별칭 사전(`네이버`→NAVER 등), 우선주(`삼성전자우`→삼성전자), 영문명, AI 제안(Gemini가 낸 이름 중 상장사 목록에 정확히 있는 것만)을 합쳐 최대 5개이고 버튼에 출처가 표시됩니다. **누구나 쓰는 유명 별칭·초성(삼전·하닉·닉스·네이버 등)은 바로 확정**하고 화면에 "입력 → 해석"을 표시합니다. 그 밖의 별칭, 모호한 이름, AI 제안은 자동 확정하지 않고 사용자가 눌러야 진행합니다("처음엔 되묻기"). AI가 해외·비상장 기업으로 분류하고 강한 후보(별칭·영문명·AI 확인)가 없으면 약한 후보(철자·약칭 추정 등)를 버리고 "조회할 수 없다"고 안내합니다(`COMPANY_NOT_SUPPORTED`). 평가는 `python -m eval.run_alias_eval`입니다.
- 공백·대소문자만 다른 경우(`sk 하이닉스`, `naver`)는 한 곳으로 확정합니다. 약칭·부분 이름·오타(`삼전`, `하이닉스`)는 자동으로 고르지 않고 후보 버튼을 보여 주며, 사용자가 고르면 같은 연도·작업으로 다시 조회합니다(선택은 실행 기록에 남음). 후보는 순위 신호가 없어 노이즈가 섞일 수 있습니다. 이름이 같은 상장사가 둘 이상이면 오류를 보여줍니다.
- 은행·보험·증권사처럼 매출 계정(`ifrs-full_Revenue`)이 없는 회사는 `ACCOUNT_NOT_UNIQUE` 오류로 중단합니다. 업종별 계정 매핑은 아직 없습니다.

## 검증 기록

| 일자 | 내용 | 결과 |
|---|---|---|
| 2026-10-17 | 자동 테스트 (고정 응답, 네트워크 불필요; LLM 호출은 가짜 함수로 대체) | 32개 통과. 실제 연동 성공을 뜻하지는 않음 |
| 2026-10-17 | 실제 OpenDART 조회 후 손계산 대조 (삼성전자 2024: 영업이익률 10.88%, 매출 성장률 16.20%) | 일치 |
| 2026-10-17 | 실제 조회 확인: SK하이닉스·현대자동차 2024, 없는 회사·부분 이름·금융업(KB금융) 오류 처리 | 정상 조회 / 의도한 오류 코드로 중단 |
| 2026-10-17 | DART 사이트의 사업보고서 원문(접수번호 기준)과 화면 수치를 직접 대조 (확인자: 사용자). 대상: 삼성전자·SK하이닉스·현대자동차 각 2025·2024·2023·2022 | 일치 |
| 2026-10-17 | 화면에서 오류 상황 직접 확인 (확인자: 사용자): 없는 회사, 부분 이름, 금융업, 데이터 없음, 틀린 키(`API_ERROR`, 키 미노출) 등 | 의도한 오류 코드로 표시 |
| 2026-10-17 | 질문 해석 평가 (Gemini 실호출, 1회, 프롬프트 튜닝 없이 첫 버전) | dev 14/14, final 11/11 (기업·연도·작업 모두 일치). 표본이 작아 일반 정확도로 해석하지 말 것 |
| 2026-10-17 | 화면 로직 시뮬레이션(AppTest): 질문 → 해석 → 조회 → 계산, 연도 누락 질문 중단. LangSmith에 trace 도착 확인(API 조회) | 정상 |
| 2026-10-17 | 질문 해석 2차 평가(어려운 질문 20개 추가, 프롬프트 v4) | dev 13/14, dev_hard 10/10, final 11/11, final_hard 7/10. 상세·실패 사례는 `docs/evaluation/eval_results.md` |
| 2026-10-17 | 전체 45문항 3회 반복(135회) + 실제 OpenDART 회귀 테스트(12개 조합, 사용자 원문 대조값) + LangSmith trace 비밀값 점검(200 run) | 호출 단위 93.3%, 비일관 2문항 / 13개 통과 / 비밀값 0건. `docs/evaluation/eval_results.md`·`docs/verification/test_results.md` 참고 |
| 2026-10-18 | 평가 질문 114개의 정답을 사용자가 검토 (확인자: 사용자) | 이견 없음(별도 수정 메모 없음). 기준선 태그 `baseline-single-request` 생성 |
| 2026-10-19 | 회사 후보 평가(입력 57개, AI 제안 포함 3회) + 후보 단위 테스트 11개 | AI 포함 hit@1 사전 외 한글 별칭 43/48, 우선주 12/12, 오타 15/15. 상세는 `docs/evaluation/eval_results.md` 5차 |
| 2026-10-19 | 해외·비상장 기업 소음 제거(AI 분류) 평가: 입력 75개 3회 + 단위 테스트 5개 추가 | 해외 14개 42/42 안내, 비상장 4개 12/12, 한국 상장사 오분류 0건, 사전 외 한글 별칭 46/48. 프롬프트 1안은 후보 이름이 나빠져 2안으로 수정. `docs/evaluation/eval_results.md` 6차 |
| 2026-10-19 | 도구 함수 정의(`tools.py`) + 단위 테스트 62개(전체 110개) + 변이 점검 5건 + 실제 호출 테스트 9개(전체 22개) | 통과. 정정공시 확인: 조회는 최신 기재정정본을 주고 접수번호·접수일·정정 여부를 표시. 동명 회사(삼성물산)는 현재 상장 법인으로 확정. `docs/backlog/policies.md` |
| 2026-10-19 | 유명 별칭·초성 즉시 확정: 단위 테스트 28개 추가(전체 138개), 실제 목록 점검(오프라인 30개), 평가 91개 입력 3회 | 바로 확정 20개 중 오확정 0, 모호한 그룹명 10개 확정 0. 초성 ㅅㅅㅈㅈ·ㄴㅇㅂ는 다른 회사와 겹쳐 후보로만. `docs/evaluation/eval_results.md` 7차 |
| 2026-10-19 | 에이전트(LangGraph, 챗봇형) 구현 + 가짜 LLM 테스트 65개(전체 203개) + 변이 점검 10건 + 평가: dev 3회 120→123→126/126, held-out 65/75(평가셋 오류 정정 시 71/75), 정답에 없는 행 0건(기준선 18건) | `docs/evaluation/eval_results.md` 8차, `docs/backlog/agent_design.md` 10절. dev는 같은 질문으로 고쳤으므로 일반화는 held-out을 본다 |

원문 대조 방법: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=<접수번호>` → 연결 손익계산서의 당기 열, 단위(백만원) 환산 후 비교. 새 회사나 계정 규칙을 추가할 때마다 같은 방법으로 대조하고 이 표에 추가한다.

## 질문 해석과 모니터링

- `question.py`: 모델 `gemini-3.5-flash-lite`(temperature 0, 구조화 JSON 출력)로 {company, year, task}만 추출합니다. 연도 없음·"작년/올해" 같은 상대 연도·복수 회사·지원 밖 작업은 `null`로 두고, 하나라도 비면 추측하지 않고 `QUESTION_INCOMPLETE`로 멈춥니다. 회사명은 약칭 보정 없이 쓰인 그대로 넘기고, 못 찾으면 회사 후보를 되묻습니다. 한 번에 하나의 작업만 지원하므로 복수 작업·연도 간 우열 비교는 task를 비웁니다.
- LangSmith: `ask` → `parse_question`(llm) → `run` → `fetch_financials`(tool) 흐름이 한 요청의 trace로 남습니다. 전송 입력은 질문 문장과 회사·연도·작업뿐이며 키는 포함하지 않습니다. 화면은 tracing 켜짐/꺼짐만 보여 주고, 전송 성공 여부는 SDK가 백그라운드로 처리해 확인하지 못합니다. 이 trace는 실제 실행 관찰용이며 품질 평가가 아닙니다.
- 평가: `python -m eval.run_eval dev|final|dev_hard|final_hard|all [반복횟수]` (실제 Gemini 호출, LangSmith 프로젝트 `finpilot-eval`). 질문 45개(`eval/questions.json`: dev 14·final 11·dev_hard 10·final_hard 10, 검토용 목록 `docs/evaluation/eval_questions.md`, 질문별 응답 `docs/evaluation/eval_responses.md`, 답하지 못한 경우 백로그 `docs/backlog/unresolved_cases.md`)의 정답은 사람이 정했고 필드별 일치를 코드로 판정합니다. 결과·모델·프롬프트/데이터셋 해시는 `eval/results/`에 저장됩니다.

- 테스트(`pytest`)는 LangSmith로 trace를 보내지 않습니다(`tests/conftest.py`). 평가 실행과 화면 실행은 `.env` 설정대로 전송합니다.

## 문서 목차

모든 문서와 평가 결과 파일의 목차: [docs/index.md](docs/index.md)

## 구조

`chat_app.py` 챗봇 화면 · `agent_core.py` 에이전트(LangGraph 상태·도구 실행·검증·답변 조립) · `app.py` 입력 폼 화면 · `tools.py` 에이전트용 도구(연도 해석·회사 확정·재무 조회·비율 계산) · `finance.py` 계산·실행 기록·`ask` · `dart.py` OpenDART 조회 · `question.py` 질문 해석 · `eval/` 평가셋과 실행기 · `tests/test_finance.py`

실행 기록(실행 ID, 시각, 단계 상태, 오류 코드)은 현재 화면에서만 확인하며 저장하지 않습니다. 표시 시간은 이번 실행의 조회·계산 시간이며 성능 평가가 아닙니다.
