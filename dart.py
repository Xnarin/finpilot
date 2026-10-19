"""OpenDART 연간 재무제표 조회. 키는 환경변수 DART_API_KEY(없으면 .env)에서만 읽고 어디에도 출력하지 않는다."""
import difflib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

from langsmith import traceable

URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
CORP_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
COMPANY_URL = "https://opendart.fss.or.kr/api/company.json"  # 기업개황(상장 구분 corp_cls)
LIST_URL = "https://opendart.fss.or.kr/api/list.json"  # 공시검색(접수일·정정 여부)
CORP_CACHE = Path(__file__).with_name(".cache") / "corp_codes.json"
REPORT_ANNUAL = "11011"  # 사업보고서
FS_DIV = {"연결": "CFS", "별도": "OFS"}
ACCOUNTS = {"revenue": "ifrs-full_Revenue", "operating_profit": "dart_OperatingIncomeLoss"}


class FinError(Exception):
    def __init__(self, code, message, candidates=None, sources=None):
        super().__init__(message)
        self.code, self.message, self.candidates, self.sources = code, message, candidates, sources or {}


def load_env():
    """.env의 KEY=VALUE를 환경변수에 채운다(이미 설정된 값은 유지). 값은 어디에도 출력하지 않는다."""
    env = Path(__file__).with_name(".env")
    if env.exists():
        for k, v in re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S*)", env.read_text(encoding="utf-8"), re.M):
            os.environ.setdefault(k, v.strip("\"'"))


def _api_key():
    load_env()
    key = os.environ.get("DART_API_KEY")
    if not key:
        raise FinError("NO_API_KEY", "DART_API_KEY가 설정되지 않았습니다. 환경변수 또는 .env에 설정하세요.")
    return key


def http_get(params, endpoint=URL):
    """타임아웃·네트워크 오류만 최대 2회 시도. 예외 메시지에 URL(키)이 섞이지 않도록 종류만 보고한다."""
    url = endpoint + "?" + urllib.parse.urlencode({"crtfc_key": _api_key(), **params})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.load(resp)
        except (OSError, ValueError) as e:  # URLError·타임아웃·HTTP 오류·JSON 파싱 실패
            if attempt == 2:
                raise FinError("NETWORK_ERROR", f"OpenDART 요청에 실패했습니다 ({type(e).__name__}).") from None
            time.sleep(1)


def http_get_company(params):
    return http_get(params, endpoint=COMPANY_URL)


def http_get_list(params):
    return http_get(params, endpoint=LIST_URL)


def load_corps():
    """상장사 [고유번호, 회사명, 종목코드, 영문명] 목록. 최초 1회 corpCode.xml을 내려받아 .cache에 저장한다."""
    # ponytail: 캐시 만료 없음. 신규 상장·사명 변경이 필요하면 .cache/corp_codes.json을 지운다.
    if CORP_CACHE.exists():
        corps = json.loads(CORP_CACHE.read_text(encoding="utf-8"))
        if corps and len(corps[0]) >= 4:  # 영문명 열이 없는 이전 캐시는 다시 받는다
            return corps
    try:
        with urllib.request.urlopen(CORP_URL + "?" + urllib.parse.urlencode({"crtfc_key": _api_key()}), timeout=60) as resp:
            xml = zipfile.ZipFile(io.BytesIO(resp.read())).read("CORPCODE.xml")
    except (OSError, zipfile.BadZipFile, KeyError) as e:  # 잘못된 키는 zip 대신 오류 본문이 온다
        raise FinError("NETWORK_ERROR", f"회사 목록을 받지 못했습니다 ({type(e).__name__}). 키와 네트워크를 확인하세요.") from None
    corps = [[c.findtext("corp_code"), c.findtext("corp_name"), c.findtext("stock_code").strip(), (c.findtext("corp_eng_name") or "").strip()]
             for c in ET.fromstring(xml).iter("list") if (c.findtext("stock_code") or "").strip()]
    CORP_CACHE.parent.mkdir(exist_ok=True)
    CORP_CACHE.write_text(json.dumps(corps, ensure_ascii=False), encoding="utf-8")
    return corps


# 누구나 쓰고 하나로만 해석되는 유명 별칭 -> 상장사 정식명. 대상이 상장사 목록에 정확히 한 곳 있을 때만 **바로 확정**한다(화면에는 "입력 -> 해석"을 표시).
# 모호한 이름(삼성·현대·엘지·포스코 등)은 여기에 넣지 않는다.
FAMOUS = {"삼전": "삼성전자", "하닉": "SK하이닉스", "하이닉스": "SK하이닉스", "닉스": "SK하이닉스", "에스케이하이닉스": "SK하이닉스", "skhynix": "SK하이닉스",
          "현차": "현대자동차", "현대차": "현대자동차", "기아차": "기아", "네이버": "NAVER", "카뱅": "카카오뱅크",
          "엘지엔솔": "LG에너지솔루션", "엔솔": "LG에너지솔루션", "엘엔솔": "LG에너지솔루션", "엘지에너지솔루션": "LG에너지솔루션",
          "엘지화학": "LG화학", "엘지전자": "LG전자", "삼바": "삼성바이오로직스", "엔씨소프트": "NC", "kt&g": "케이티앤지", "삼성sds": "삼성에스디에스", "한전": "한국전력공사"}
# 정식명 전체의 초성. 상장사 목록 전체에서 이 초성이 하나뿐일 때만 바로 확정한다.
CHOSUNG_FAMOUS = {"ㅅㅅㅈㅈ": "삼성전자", "ㅎㄷㅈㄷㅊ": "현대자동차", "ㅎㅇㄴㅅ": "SK하이닉스", "ㄴㅇㅂ": "NAVER", "ㅋㅋㅇㅂㅋ": "카카오뱅크"}
# 후보로만 보여 주는 별칭(모호하거나 덜 흔함). 확정은 사용자가 한다.
ALIASES = {"포스코": "POSCO홀딩스", "셀트": "셀트리온", "엔씨": "NC", "두산에너빌": "두산에너빌리티", "에스케이텔레콤": "SK텔레콤", "케이비금융": "KB금융", "삼성에스디아이": "삼성SDI"}
_PREFERRED = re.compile(r"(\d?우[A-C]?|우\(전환\))$")
_ENG_SUFFIX = re.compile(r"(co|ltd|inc|corp|corporation|company|limited)+$")
SRC_ALIAS, SRC_PREFERRED, SRC_ENGLISH, SRC_FAMOUS = "별칭 사전", "우선주 → 해당 회사 재무제표", "영문명", "유명 별칭"


def _norm(s):
    return re.sub(r"\s+", "", s).casefold()


def _chosung(s):
    """한글 음절은 초성으로, 그 밖의 글자는 소문자로 바꾼다. 공백은 뺀다."""
    out = []
    for ch in re.sub(r"\s+", "", s):
        o = ord(ch) - 0xAC00
        out.append("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"[o // 588] if 0 <= o < 11172 else ch.casefold())
    return "".join(out)


def _chosung_ko(s):
    """한글 음절의 초성만(영문·숫자 제외). 'SK하이닉스' -> 'ㅎㅇㄴㅅ'."""
    return "".join(c for c in _chosung(re.sub(r"[^가-힣]", "", s)))


def _is_jamo(s):
    return bool(s) and all("\u3131" <= ch <= "\u314e" for ch in s)


def famous_match(name, corps):
    """유명 별칭·초성이면 상장사 행, 아니면 None. 목록에 대상이 정확히 한 곳이 아니거나(동명), 초성이 다른 회사와 겹치면 확정하지 않는다."""
    n = _norm(name)
    for table, unique_chosung in ((FAMOUS, False), (CHOSUNG_FAMOUS, True)):
        target = table.get(n)
        if not target:
            continue
        rows = [c for c in corps if c[1] == target]
        if len(rows) == 1 and (not unique_chosung or [c for c in corps if _chosung_ko(c[1]) == n] == rows):
            return rows[0]
    return None


def _eng_norm(s):
    return _ENG_SUFFIX.sub("", re.sub(r"[^a-z0-9]", "", s.casefold()))


def _is_abbrev(short, full):
    """'삼전' ⊂ '삼성전자': 첫 글자가 같고 나머지 글자가 순서대로 들어 있으면 약칭 후보."""
    it = iter(full)
    return len(short) >= 2 and short[0] == full[0] and all(ch in it for ch in short)


def candidate_list(name, corps):
    """되묻기용 후보 [(상장사명, 출처)] 최대 5개. 별칭 -> 우선주 -> 영문명 -> 이름 포함 -> 약칭 -> 비슷한 철자 순. 자동 확정에는 쓰지 않는다."""
    n = _norm(name)
    by_norm = {_norm(c[1]): c[1] for c in corps}
    out = []

    def add(names, source):
        for x in names:
            if x not in [o[0] for o in out]:
                out.append((x, source))

    if ALIASES.get(n) in by_norm.values():
        add([ALIASES[n]], SRC_ALIAS)
    base = _PREFERRED.sub("", n)
    if base != n and base in by_norm:
        add([by_norm[base]], SRC_PREFERRED)
    e = _eng_norm(name)
    if len(e) >= 5:
        add([c[1] for c in corps if len(c) > 3 and c[3] and e in _eng_norm(c[3])][:3], SRC_ENGLISH)
    add([by_norm[k] for k in sorted((k for k in by_norm if n and n in k), key=len)], "이름 일부 일치")
    add([by_norm[k] for k in sorted((k for k in by_norm if len(k) >= 3 and k in n and k != n), key=len, reverse=True)], "입력에 포함된 회사명")
    add([by_norm[k] for k in sorted((k for k in by_norm if _is_abbrev(n, k)), key=len)], "약칭 추정")
    if _is_jamo(n) and len(n) >= 3:
        add([c[1] for c in sorted(corps, key=lambda c: len(c[1])) if _chosung_ko(c[1]) == n][:3], "초성 일치")
    if not out:  # 오타 후보는 다른 후보가 없을 때만(엉뚱한 제안을 줄이기 위해 기준을 높게 둔다)
        add([by_norm[k] for k in difflib.get_close_matches(n, list(by_norm), n=5, cutoff=0.75)], "비슷한 철자")
    return out[:5]


def company_candidates(name, corps):
    return [c for c, _ in candidate_list(name, corps)]


def exact_matches(name, corps):
    """회사명이 정확히 일치(공백·대소문자 차이만 무시)하는 행들."""
    return [c for c in corps if c[1] == name.strip()] or [c for c in corps if _norm(c[1]) == _norm(name)]


def find_company(name, corps):
    """정확히 일치(공백·대소문자 차이만 무시)하는 상장사 한 곳만 확정한다. 그 밖에는 추측하지 않고 후보를 알려 되묻는다."""
    hits = exact_matches(name, corps)
    if len(hits) == 1:
        return hits[0][0], hits[0][1]
    if not hits:
        fm = famous_match(name, corps)
        if fm:
            return fm[0], fm[1]
    if hits:
        raise FinError("COMPANY_AMBIGUOUS", f"'{name.strip()}'에 해당하는 상장사가 {len(hits)}곳입니다: " + ", ".join(f"{c[1]}({c[2]})" for c in hits[:5]),
                       [c[1] for c in hits[:5]])
    cl = candidate_list(name, corps)
    cands = [c for c, _ in cl]
    raise FinError("COMPANY_NOT_FOUND", f"상장사 '{name.strip()}'을(를) 찾지 못했습니다." + (f" 혹시 {', '.join(cands)} 중 하나인가요?" if cands else ""),
                   cands, dict(cl))


LISTED_CLS = ("Y", "K", "N")  # 유가증권·코스닥·코넥스. E(기타)는 상장폐지 등


def listing_class(corp_code, _get=http_get_company):
    """기업개황의 법인구분(corp_cls). 같은 이름의 상장사가 둘 이상일 때 현재 상장된 곳을 가리는 데 쓴다. 조회에 실패하면 None."""
    try:
        d = _get({"corp_code": corp_code})
    except FinError:
        return None
    return d.get("corp_cls") if d.get("status") == "000" else None


def report_meta(corp_code, year, rcept_no, _get=http_get_list):
    """사업보고서 접수번호의 보고서명·접수일·정정 여부. 같은 사업연도의 접수 건수도 센다. 실패하면 None(조회 자체는 막지 않는다)."""
    try:
        d = _get({"corp_code": corp_code, "bgn_de": f"{year + 1}0101", "end_de": f"{year + 3}1231", "pblntf_detail_ty": "A001",
                  "last_reprt_at": "N", "page_count": "100"})
    except FinError:
        return None
    rows = [r for r in d.get("list", []) if f"({year}.12)" in r.get("report_nm", "")]
    mine = next((r for r in rows if r.get("rcept_no") == rcept_no), None)
    if not mine:
        return None
    return {"report_name": mine["report_nm"].strip(), "rcept_date": mine["rcept_dt"], "is_amended": "정정" in mine["report_nm"], "filings_for_year": len(rows)}


def _amount(rows, account_id, year):
    hits = [r for r in rows if r.get("sj_div") in ("IS", "CIS") and r.get("account_id") == account_id]
    if len(hits) != 1:
        raise FinError("ACCOUNT_NOT_UNIQUE", f"{year}년 계정 {account_id}가 {len(hits)}건입니다. 임의로 선택하지 않습니다.")
    r = hits[0]
    if r.get("currency") != "KRW":
        raise FinError("UNIT_MISMATCH", f"통화가 KRW가 아닙니다: {r.get('currency')}")
    raw = (r.get("thstrm_amount") or "").replace(",", "").strip()
    if not re.fullmatch(r"-?\d+", raw):
        raise FinError("PARSE_ERROR", f"{year}년 {account_id} 금액을 정수로 읽을 수 없습니다: {raw!r}")
    return int(raw), r["rcept_no"]


@traceable(name="fetch_financials", run_type="tool", process_inputs=lambda i: {k: i[k] for k in ("company", "year", "basis") if k in i})
def fetch_financials(company, year, basis="연결", _get=http_get, _corps=None):
    """해당 연도 사업보고서 당기(thstrm) 금액. 후속 보고서의 재작성 수치(frmtrm)는 쓰지 않는다."""
    if basis not in FS_DIV:
        raise FinError("UNSUPPORTED", f"지원하지 않는 재무제표 기준입니다: {basis}")
    corp_code, company = find_company(company, _corps if _corps is not None else load_corps())
    return fetch_by_code(corp_code, company, year, basis, _get)


def fetch_by_code(corp_code, company, year, basis="연결", _get=http_get):
    """고유번호로 조회. 회사 확정은 호출자가 끝낸 상태(동명 회사 문제를 피하려고 번호로 조회한다)."""
    if basis not in FS_DIV:
        raise FinError("UNSUPPORTED", f"지원하지 않는 재무제표 기준입니다: {basis}")
    d = _get({"corp_code": corp_code, "bsns_year": str(year), "reprt_code": REPORT_ANNUAL, "fs_div": FS_DIV[basis]})
    status = d.get("status")
    if status == "013":
        raise FinError("DATA_MISSING", f"{company} {year}년 {basis} 사업보고서 데이터가 없습니다. 다른 값으로 대체하지 않습니다.")
    if status != "000":
        raise FinError("API_ERROR", f"OpenDART 오류 {status}: {d.get('message')}")
    rows = d.get("list") or []
    rev, rcept = _amount(rows, ACCOUNTS["revenue"], year)
    op, rcept2 = _amount(rows, ACCOUNTS["operating_profit"], year)
    if rcept != rcept2:
        raise FinError("SOURCE_MISMATCH", "매출액과 영업이익의 접수번호가 서로 다릅니다.")
    return {"company": company, "corp_code": corp_code, "year": year, "basis": basis, "unit": "원", "revenue": rev,
            "operating_profit": op, "rcept_no": rcept, "fetched_at": datetime.now().isoformat(timespec="seconds")}
