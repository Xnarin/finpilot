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
streamlit run app.py
```

## 테스트

```bash
python -m pytest
```

테스트는 가상·고정 응답을 사용하므로 네트워크와 키가 필요 없습니다. 통과해도 실제 OpenDART 연동 성공을 뜻하지는 않으며, 실제 연동은 화면 실행으로 확인합니다.

## 조회 기준

- 엔드포인트 `fnlttSinglAcntAll`, 사업보고서(11011), 연결재무제표(CFS)만 조회합니다. 연결 자료가 없어도 별도로 대체하지 않습니다.
- 매출액 `ifrs-full_Revenue`, 영업이익 `dart_OperatingIncomeLoss` (손익계산서 IS/CIS)를 계정 ID로 정확히 한 건 선택합니다. 후보가 0건 또는 2건 이상이면 오류입니다.
- 각 연도 사업보고서의 당기 금액만 사용합니다. 이듬해 보고서의 전기(재작성) 수치와 섞지 않습니다. 성장률의 전기 매출은 전년도 사업보고서의 당기 금액입니다.
- 통화는 KRW만 허용하고 금액은 원 단위 정수로 다룹니다. 타임아웃·네트워크 오류만 1회 재시도합니다.

## 회사 선택

- 정확한 상장사명을 입력합니다(예: `SK하이닉스`). 최초 실행 때 OpenDART `corpCode.xml`로 상장사 목록을 받아 `.cache/corp_codes.json`에 저장합니다(신규 상장·사명 변경 반영은 이 파일을 지우면 됩니다).
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
| 2026-10-17 | 질문 해석 2차 평가(어려운 질문 20개 추가, 프롬프트 v4) | dev 13/14, dev_hard 10/10, final 11/11, final_hard 7/10. 상세·실패 사례는 `docs/eval_results.md` |

원문 대조 방법: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=<접수번호>` → 연결 손익계산서의 당기 열, 단위(백만원) 환산 후 비교. 새 회사나 계정 규칙을 추가할 때마다 같은 방법으로 대조하고 이 표에 추가한다.

## 질문 해석과 모니터링

- `question.py`: 모델 `gemini-3.5-flash-lite`(temperature 0, 구조화 JSON 출력)로 {company, year, task}만 추출합니다. 연도 없음·"작년/올해" 같은 상대 연도·복수 회사·지원 밖 작업은 `null`로 두고, 하나라도 비면 추측하지 않고 `QUESTION_INCOMPLETE`로 멈춥니다. 회사명은 약칭 보정 없이 쓰인 그대로 넘기고, 못 찾으면 회사 후보를 되묻습니다. 한 번에 하나의 작업만 지원하므로 복수 작업·연도 간 우열 비교는 task를 비웁니다.
- LangSmith: `ask` → `parse_question`(llm) → `run` → `fetch_financials`(tool) 흐름이 한 요청의 trace로 남습니다. 전송 입력은 질문 문장과 회사·연도·작업뿐이며 키는 포함하지 않습니다. 화면은 tracing 켜짐/꺼짐만 보여 주고, 전송 성공 여부는 SDK가 백그라운드로 처리해 확인하지 못합니다. 이 trace는 실제 실행 관찰용이며 품질 평가가 아닙니다.
- 평가: `python -m eval.run_eval dev|final|all` (실제 Gemini 호출, LangSmith 프로젝트 `finpilot-eval`). 질문 45개(`eval/questions.json`: dev 14·final 11·dev_hard 10·final_hard 10)의 정답은 사람이 정했고 필드별 일치를 코드로 판정합니다. 결과·모델·프롬프트/데이터셋 해시는 `eval/results/`에 저장됩니다.

## 구조

`app.py` 화면 · `finance.py` 계산·실행 기록·`ask` · `dart.py` OpenDART 조회 · `question.py` 질문 해석 · `eval/` 평가셋과 실행기 · `tests/test_finance.py`

실행 기록(실행 ID, 시각, 단계 상태, 오류 코드)은 현재 화면에서만 확인하며 저장하지 않습니다. 표시 시간은 이번 실행의 조회·계산 시간이며 성능 평가가 아닙니다.
