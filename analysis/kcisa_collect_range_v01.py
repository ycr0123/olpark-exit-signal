"""문화공공데이터광장 659 남은 구간 내려받기(2026-11-24). 키는 private/kcisa-keys.txt 에서 읽고 출력, 저장하지 않는다.

배경: 1만 행 단위로 227쪽까지 받은 뒤 228쪽에서 중계 서버 60초 시간 초과(504)가 연달아 났다.
남은 행(2,270,001번째부터)을 더 작은 단위로 받는다.

사용: python kcisa_collect_range_v01.py <numOfRows> <첫 쪽> <끝 쪽> <간격초> <키 이름>
- 쪽 번호는 numOfRows 기준. 예: 5천 행이면 455쪽 = 2,270,001~2,275,000번째 행.
- 저장: data/raw/kcisa659_n<numOfRows>/p0455.json.gz(응답 원문, 키 문자열은 지움). 이미 있는 쪽은 건너뛴다.
- HTTP 오류(429, 504 포함)나 결과 코드가 0000 이 아니면 즉시 멈춘다(재시도는 바깥 스크립트가 정한다).
- 쪽마다 받은 행 수가 numOfRows(전체의 마지막 쪽은 나머지)와 다르면 멈춘다.
- 호출 수는 v02 수집기와 같은 파일(kcisa_calls_<키>_<날짜>.txt)에 더한다. 950 에서 멈춘다.
- 진행 기록: data/raw/kcisa659/progress.log (v02 와 같은 파일, 줄 머리에 RANGE 표시)
"""

import datetime as dt
import gzip
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYS = HERE.parent / "private" / "kcisa-keys.txt"
EP = "https://api.kcisa.kr/openapi/API_CPM_008/request"
DAILY_STOP = 950
nrows, first, last = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
GAP = float(sys.argv[4])
KEYNAME = sys.argv[5]
keys = dict(
    line.split("=", 1)
    for line in KEYS.read_text(encoding="utf-8").split()
    if "=" in line
)
key = keys[KEYNAME]
raw_dir = HERE.parent / "data" / "raw"
out = raw_dir / f"kcisa659_n{nrows}"
out.mkdir(parents=True, exist_ok=True)
log = raw_dir / "kcisa659" / "progress.log"
today = dt.datetime.now().strftime("%Y%m%d")
cnt_file = raw_dir / f"kcisa_calls_{KEYNAME}_{today}.txt"


def note(msg):
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} RANGE n{nrows} {msg}"
    print(line, flush=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def bump():
    n = int(cnt_file.read_text()) if cnt_file.exists() else 0
    cnt_file.write_text(str(n + 1))
    return n + 1


def items_of(d):
    bd = d.get("response", d).get("body", {})
    it = bd.get("items", {})
    if isinstance(it, dict):
        it = it.get("item", [])
    if isinstance(it, dict):
        it = [it]
    return bd, it


for page in range(first, last + 1):
    f = out / f"p{page:04d}.json.gz"
    if f.exists():
        continue
    used = bump()
    if used > DAILY_STOP:
        note(f"STOP daily guard {used - 1} calls today")
        raise SystemExit(3)
    q = urllib.parse.urlencode({"serviceKey": key, "numOfRows": nrows, "pageNo": page})
    req = urllib.request.Request(
        EP + "?" + q,
        headers={
            "Accept": "application/json",
            "User-Agent": "olpark-exit-forecast collector",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        try:
            eb = e.read().decode("utf-8", "replace").replace(key, "<KEY>")[:300]
        except Exception:
            eb = "?"
        note(
            f"STOP HTTP {e.code} page {page} after {time.time() - t0:.0f}s body {eb!r}"
        )
        raise SystemExit(2)
    except Exception as e:
        note(f"STOP error page {page}: {type(e).__name__}")
        raise SystemExit(2)
    secs = time.time() - t0
    text = raw.decode("utf-8").replace(key, "<KEY>")
    d = json.loads(text)
    hdr = d.get("response", d).get("header", {})
    if hdr.get("resultCode") != "0000":
        note(f"STOP resultCode {hdr} page {page}")
        raise SystemExit(2)
    bd, it = items_of(d)
    total = int(bd["totalCount"])
    pages = math.ceil(total / nrows)
    expect = nrows if page < pages else total - nrows * (pages - 1)
    if len(it) != expect:
        note(f"STOP rows {len(it)} != expected {expect} page {page}")
        raise SystemExit(2)
    f.write_bytes(gzip.compress(text.encode("utf-8")))
    note(f"OK page {page}/{pages} rows {len(it)} total {total} resp {secs:.0f}s")
    if page >= last:
        note(f"DONE range {first}-{last}")
        break
    time.sleep(GAP)
