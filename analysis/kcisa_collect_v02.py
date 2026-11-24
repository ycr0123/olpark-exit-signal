"""문화공공데이터광장 2025 데이터 내려받기(2026-11-23). 키는 private/kcisa-keys.txt 에서 읽고 출력, 저장하지 않는다.

사용: python kcisa_collect_v01.py <675|659> <numOfRows> [max_calls] [간격초] [키 이름(기본 api 번호, 예: 659op)]
- 쪽마다 data/raw/kcisa<api>/p0001.json.gz 로 저장(응답 원문, 키 문자열은 지움). 이미 있는 쪽은 건너뛴다(이어받기).
- 순차 호출, 호출 사이 GAP초(4번째 인자, 기본 30초). 2초 간격은 11-23 14:22 에 2번째 호출에서 429 를 받았다. 결과 코드가 0000 이 아니거나 HTTP 오류(429 포함)면 즉시 멈춘다.
- 타임아웃은 1번만 다시 시도하고, 또 실패하면 멈춘다.
- 하루 한도(개발 계정 1,000건) 보호: 오늘 호출 수를 calls_<날짜>.txt 에 세고 950 에서 멈춘다.
- 쪽마다 받은 행 수가 numOfRows(마지막 쪽은 나머지)와 다르면 멈춘다.
- 진행 기록: data/raw/kcisa<api>/progress.log
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
EP = {
    "675": "https://api.kcisa.kr/openapi/API_CPM_009/request",
    "659": "https://api.kcisa.kr/openapi/API_CPM_008/request",
}
DAILY_STOP = 950
api, nrows = sys.argv[1], int(sys.argv[2])
max_calls = int(sys.argv[3]) if len(sys.argv) > 3 else 10**9
GAP = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
# 5번째 인자: 키 이름(기본은 api 번호). 659op = 11-23 15:21 발급 운영 계정 키.
KEYNAME = sys.argv[5] if len(sys.argv) > 5 else api
keys = dict(
    line.split("=", 1)
    for line in KEYS.read_text(encoding="utf-8").split()
    if "=" in line
)
key = keys[KEYNAME]
out = HERE.parent / "data" / "raw" / f"kcisa{api}"
out.mkdir(parents=True, exist_ok=True)
log = out / "progress.log"
today = dt.datetime.now().strftime("%Y%m%d")
cnt_file = out.parent / f"kcisa_calls_{KEYNAME}_{today}.txt"


def note(msg):
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def bump():
    n = int(cnt_file.read_text()) if cnt_file.exists() else 0
    cnt_file.write_text(str(n + 1))
    return n + 1


def fetch(page):
    q = urllib.parse.urlencode({"serviceKey": key, "numOfRows": nrows, "pageNo": page})
    req = urllib.request.Request(
        EP[api] + "?" + q,
        headers={
            "Accept": "application/json",
            "User-Agent": "olpark-exit-forecast collector",
        },
    )
    for attempt in (1, 2):
        used = bump()
        if used > DAILY_STOP:
            note(f"STOP daily guard {used - 1} calls today")
            raise SystemExit(3)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            try:
                eb = e.read().decode("utf-8", "replace").replace(key, "<KEY>")[:600]
            except Exception:
                eb = "?"
            hd = {k: v for k, v in e.headers.items() if k.lower() not in ("set-cookie",)}
            note(f"STOP HTTP {e.code} page {page} headers {hd} body {eb!r}")
            raise SystemExit(2)
        except Exception as e:
            note(f"timeout/error page {page} attempt {attempt}: {type(e).__name__}")
            if attempt == 2:
                raise SystemExit(2)
            time.sleep(10)


def items_of(d):
    bd = d.get("response", d).get("body", {})
    it = bd.get("items", {})
    if isinstance(it, dict):
        it = it.get("item", [])
    if isinstance(it, dict):
        it = [it]
    return bd, it


total = None
pages = None
page = 1
calls = 0
while True:
    f = out / f"p{page:04d}.json.gz"
    if f.exists():
        if total is None:
            bd, _ = items_of(
                json.loads(gzip.decompress(f.read_bytes()).decode("utf-8"))
            )
            total = int(bd["totalCount"])
            pages = math.ceil(total / nrows)
        if page >= pages:
            break
        page += 1
        continue
    if calls >= max_calls:
        note(f"PAUSE max_calls {max_calls} reached at page {page}")
        break
    raw = fetch(page)
    calls += 1
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
    note(f"OK page {page}/{pages} rows {len(it)} total {total} key {KEYNAME}")
    if page >= pages:
        note("DONE all pages")
        break
    page += 1
    time.sleep(GAP)
