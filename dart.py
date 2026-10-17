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
CORP_CACHE = Path(__file__).with_name(".cache") / "corp_codes.json"
REPORT_ANNUAL = "11011"  # 사업보고서
FS_DIV = {"연결": "CFS", "별도": "OFS"}
ACCOUNTS = {"revenue": "ifrs-full_Revenue", "operating_profit": "dart_OperatingIncomeLoss"}


class FinError(Exception):
    def __init__(self, code, message, candidates=None):
        super().__init__(message)
        self.code, self.message, self.candidates = code, message, candidates


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


def http_get(params):
    """타임아웃·네트워크 오류만 최대 2회 시도. 예외 메시지에 URL(키)이 섞이지 않도록 종류만 보고한다."""
    url = URL + "?" + urllib.parse.urlencode({"crtfc_key": _api_key(), **params})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.load(resp)
        except (OSError, ValueError) as e:  # URLError·타임아웃·HTTP 오류·JSON 파싱 실패
            if attempt == 2:
                raise FinError("NETWORK_ERROR", f"OpenDART 요청에 실패했습니다 ({type(e).__name__}).") from None
            time.sleep(1)


def load_corps():
    """상장사 [고유번호, 회사명, 종목코드] 목록. 최초 1회 corpCode.xml을 내려받아 .cache에 저장한다."""
    # ponytail: 캐시 만료 없음. 신규 상장·사명 변경이 필요하면 .cache/corp_codes.json을 지운다.
    if CORP_CACHE.exists():
        return json.loads(CORP_CACHE.read_text(encoding="utf-8"))
    try:
        with urllib.request.urlopen(CORP_URL + "?" + urllib.parse.urlencode({"crtfc_key": _api_key()}), timeout=60) as resp:
            xml = zipfile.ZipFile(io.BytesIO(resp.read())).read("CORPCODE.xml")
    except (OSError, zipfile.BadZipFile, KeyError) as e:  # 잘못된 키는 zip 대신 오류 본문이 온다
        raise FinError("NETWORK_ERROR", f"회사 목록을 받지 못했습니다 ({type(e).__name__}). 키와 네트워크를 확인하세요.") from None
    corps = [[c.findtext("corp_code"), c.findtext("corp_name"), c.findtext("stock_code").strip()]
             for c in ET.fromstring(xml).iter("list") if (c.findtext("stock_code") or "").strip()]
    CORP_CACHE.parent.mkdir(exist_ok=True)
    CORP_CACHE.write_text(json.dumps(corps, ensure_ascii=False), encoding="utf-8")
    return corps


def _norm(s):
    return re.sub(r"\s+", "", s).casefold()


def _is_abbrev(short, full):
    """'삼전' ⊂ '삼성전자': 첫 글자가 같고 나머지 글자가 순서대로 들어 있으면 약칭 후보."""
    it = iter(full)
    return len(short) >= 2 and short[0] == full[0] and all(ch in it for ch in short)


def company_candidates(name, corps):
    """되묻기용 후보(최대 5개). 부분 일치 -> 약칭 -> 비슷한 철자 순. 자동 선택에는 쓰지 않는다."""
    n = _norm(name)
    names = {_norm(c[1]): c[1] for c in corps}
    out = []
    for group in ([k for k in names if n and n in k], [k for k in names if _is_abbrev(n, k)]):
        out += [names[k] for k in sorted(group, key=len) if names[k] not in out]
    if not out:  # 오타 후보는 다른 후보가 없을 때만(엉뚱한 제안을 줄이기 위해 기준을 높게 둔다)
        out = [names[k] for k in difflib.get_close_matches(n, list(names), n=5, cutoff=0.75)]
    return out[:5]


def find_company(name, corps):
    """정확히 일치(공백·대소문자 차이만 무시)하는 상장사 한 곳만 확정한다. 그 밖에는 추측하지 않고 후보를 알려 되묻는다."""
    hits = [c for c in corps if c[1] == name.strip()] or [c for c in corps if _norm(c[1]) == _norm(name)]
    if len(hits) == 1:
        return hits[0][0], hits[0][1]
    if hits:
        raise FinError("COMPANY_AMBIGUOUS", f"'{name.strip()}'에 해당하는 상장사가 {len(hits)}곳입니다: " + ", ".join(f"{c[1]}({c[2]})" for c in hits[:5]),
                       [c[1] for c in hits[:5]])
    cands = company_candidates(name, corps)
    raise FinError("COMPANY_NOT_FOUND", f"상장사 '{name.strip()}'을(를) 찾지 못했습니다." + (f" 혹시 {', '.join(cands)} 중 하나인가요?" if cands else ""), cands)


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
    return {"company": company, "year": year, "basis": basis, "unit": "원", "revenue": rev,
            "operating_profit": op, "rcept_no": rcept, "fetched_at": datetime.now().isoformat(timespec="seconds")}
