"""675 시간 단위 행에서 공연이 적힌 시간대를 날짜, 공연별로 묶는다(2026-11-23). 판정 아님, 구조 확인.

정의: TITLE 의 '공연명:' 뒤 값이 비지 않은 행을 공연 시간으로 본다. 같은 날 같은 공연명의 첫 시각과 마지막 시각, 시간 수, 관람객 수.
출력: analysis/kcisa675_events_v01.csv
"""

import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "data" / "raw" / "kcisa675"
rows = []
for f in sorted(RAW.glob("p*.json.gz")):
    d = json.loads(gzip.decompress(f.read_bytes()).decode("utf-8"))
    it = d.get("response", d)["body"]["items"]
    if isinstance(it, dict):
        it = it.get("item", [])
    rows += it

pat = re.compile(r"공연명:(.*?),공연관람객수:(\d*)", re.S)
hours_per_day = defaultdict(int)
ev = defaultdict(list)
bad = 0
for r in rows:
    ts = r["ISSUED_DATE"]
    day, hh = ts[:10], int(ts[11:13])
    hours_per_day[day] += 1
    m = pat.search(r["TITLE"])
    if not m:
        bad += 1
        continue
    name = m.group(1).strip()
    if not name:
        continue
    ev[(day, name)].append((hh, int(m.group(2) or 0)))

print("rows", len(rows), "unparsed", bad, "days", len(hours_per_day))
hc = defaultdict(int)
for v in hours_per_day.values():
    hc[v] += 1
print("hours per day distribution", dict(sorted(hc.items())))
all_h = sorted({int(r["ISSUED_DATE"][11:13]) for r in rows})
print("hours present", all_h)

out = HERE / "kcisa675_events_v01.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["date", "name", "first_hour", "last_hour", "n_hours", "audience"])
    for (day, name), hs in sorted(ev.items()):
        hrs = sorted(h for h, _ in hs)
        aud = max(a for _, a in hs)
        w.writerow([day, name, hrs[0], hrs[-1], len(hrs), aud])
print("event-days", len(ev), "->", out)
fh = defaultdict(int)
for (day, name), hs in ev.items():
    fh[min(h for h, _ in hs)] += 1
print("first_hour distribution", dict(sorted(fh.items())))
nh = defaultdict(int)
for (day, name), hs in ev.items():
    nh[len(hs)] += 1
print("n_hours distribution", dict(sorted(nh.items())))
