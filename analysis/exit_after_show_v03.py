"""2025 입출차(659)와 공연 시간대(675)를 묶어 '공연 뒤 출차 물결'을 1년 치로 잰다(2026-11-23 작성, 결과 보기 전 기준 고정).

입력: data/raw/kcisa659/p*.json.gz(1만 행 1~227쪽) + data/raw/kcisa659_n5000/p*.json.gz(5천 행 455~483쪽), analysis/kcisa675_events_v01.csv
v02(2026-11-24): v01 과 기준, 정의, 통과선이 같고 입력 경로와 출력 파일명만 다르다. 1만 행 228쪽부터 504 가 연달아 나서 남은 행을 5천 행 단위로 받았다.
1천 행 시험 파일(kcisa659_n1000)은 5천 행 466쪽과 겹치므로 넣지 않는다(LOCAL_ID 중복 제거로도 결과는 같다).
사전 점검(실패하면 멈춤): 고유 LOCAL_ID 수 == totalCount(쪽 나눔이 행을 빠뜨리거나 겹치게 받지 않았는지). 출차 시각 해석 실패 0.

정의(결과 전 고정):
- 출차 수: 출차시간 기준 10분 칸 개수. 30분 물결 = 연속 3칸 합.
- 공연일: 675 에 공연명이 적힌 날. 그날 공연 시간대의 끝 = 그날 공연 행의 마지막 시각(last_hour) + 1시간.
- 그날 밤 최고 물결: 그날 15:00~다음날 01:00 사이 30분 물결의 최댓값과 그 시작 시각.
- 공연 뒤 지연 = 최고 물결 시작 시각 - 공연 시간대 끝(분).
- 평일 기준선: 공연 없는 날의 같은 창 최고 물결 크기 중앙값.

예보 시험(결과 전 고정, 공연일만):
- 학습 = 2025-01~06 공연일, 시험 = 2025-07~12 공연일.
- 시각 예보 A = 공연 시간대 끝 + 학습 지연 중앙값. 상수 예보 B = 학습 최고 물결 시작 시각(하루 중 분)의 중앙값.
- 크기 예보 A = 학습 공연일로 맞춘 직선(최고 물결 크기 ~ 관람객 수). 상수 예보 B = 학습 최고 물결 크기 중앙값.
- 통과(각각): 시험 평균 절대 오차가 A 가 B 보다 20% 이상 작다. 둘 다 통과해야 '공연 일정으로 그날 밤 출차 시각과 규모를 미리 안내'를 기획서에 쓴다.
  하나만 통과하면 통과한 쪽만 쓴다. 둘 다 실패하면 예보 약속을 빼고 실시간 알림만 쓴다.
- 공연 없는 날은 예보 대상이 아니다(1판 비판 점검에서 상수 예보보다 나빴음).
출력: analysis/exit_after_show_v02.json, analysis/exit_after_show_daily_v02.csv
v03(2026-11-24 11시대, 실행 전 커밋): 기준, 정의, 통과선은 앞 판과 같다. 바꾼 것은 하나뿐이다:
analysis/coverage_v01.json 의 온전한 날(valid_days)만 쓴다. 원본에 8, 9월 일부만 남음, 11, 12월 7일 끊김, 매달 마지막 날 0건 결함이 있어
앞 판의 시험 구간 절반 이상이 결함이었다(coverage_v01.py 에 규칙과 근거). 규칙은 건수만 보고 정했다.
"""

import csv
import datetime as dt
import gzip
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAWS = [HERE.parent / "data" / "raw" / "kcisa659", HERE.parent / "data" / "raw" / "kcisa659_n5000"]
EVENTS = HERE / "kcisa675_events_v01.csv"

pat_out = re.compile(r"출차시간:(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
seen = set()
total = None
bins = defaultdict(int)  # (datetime of 10-min bin) -> count
bad = 0
FILES = [f for r in RAWS for f in sorted(r.glob("p*.json.gz"))]
print("files", len(FILES), [len(list(r.glob("p*.json.gz"))) for r in RAWS])
for f in FILES:
    d = json.loads(gzip.decompress(f.read_bytes()).decode("utf-8"))
    body = d.get("response", d)["body"]
    total = int(body["totalCount"])
    it = body["items"]
    if isinstance(it, dict):
        it = it.get("item", [])
    for r in it:
        lid = r["LOCAL_ID"]
        if lid in seen:
            continue
        seen.add(lid)
        m = pat_out.search(r.get("DESCRIPTION") or "")
        if not m:
            bad += 1
            continue
        t = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        bins[t.replace(minute=t.minute // 10 * 10, second=0)] += 1
print("unique", len(seen), "total", total, "unparsed exit", bad)
if total is None or len(seen) != total:
    raise SystemExit("STOP unique LOCAL_ID != totalCount (page gaps or overlaps)")

ev = defaultdict(lambda: {"last_hour": -1, "aud": 0})
with open(EVENTS, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        e = ev[row["date"]]
        e["last_hour"] = max(e["last_hour"], int(row["last_hour"]))
        e["aud"] = max(e["aud"], int(row["audience"]))


def night_peak(day):
    start = dt.datetime.combine(day, dt.time(15, 0))
    best, best_t = -1, None
    t = start
    while t <= start + dt.timedelta(hours=9, minutes=30):
        s = sum(bins.get(t + dt.timedelta(minutes=10 * k), 0) for k in range(3))
        if s > best:
            best, best_t = s, t
        t += dt.timedelta(minutes=10)
    return best, best_t


daily = []
day = dt.date(2025, 1, 1)
while day <= dt.date(2025, 12, 30):
    size, t = night_peak(day)
    ds = day.isoformat()
    rec = {
        "date": ds,
        "event": ds in ev,
        "peak30": size,
        "peak_start": t.strftime("%H:%M"),
    }
    rec["peak_min"] = (t - dt.datetime.combine(day, dt.time(0, 0))).total_seconds() / 60
    if ds in ev:
        end = dt.datetime.combine(day, dt.time(0, 0)) + dt.timedelta(
            hours=ev[ds]["last_hour"] + 1
        )
        rec["block_end"] = end.strftime("%H:%M")
        rec["delay_min"] = (t - end).total_seconds() / 60
        rec["audience"] = ev[ds]["aud"]
    daily.append(rec)
    day += dt.timedelta(days=1)

VALID = set(json.loads((Path(__file__).resolve().parent / "coverage_v01.json").read_text(encoding="utf-8"))["valid_days"])
daily = [r for r in daily if r["date"] in VALID]
print("valid days used", len(daily))

with open(
    HERE / "exit_after_show_daily_v03.csv", "w", newline="", encoding="utf-8-sig"
) as f:
    keys = [
        "date",
        "event",
        "audience",
        "block_end",
        "peak_start",
        "delay_min",
        "peak30",
    ]
    w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    w.writerows(daily)

evd = [r for r in daily if r["event"]]
non = [r for r in daily if not r["event"]]
train = [r for r in evd if r["date"] < "2025-07-01"]
test = [r for r in evd if r["date"] >= "2025-07-01"]
med_delay = st.median(r["delay_min"] for r in train)
med_peak_min = st.median(r["peak_min"] for r in train)
med_size = st.median(r["peak30"] for r in train)
xs = [r["audience"] for r in train]
ys = [r["peak30"] for r in train]
mx, my = st.mean(xs), st.mean(ys)
sxx = sum((x - mx) ** 2 for x in xs)
slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
icpt = my - slope * mx


def mae(pairs):
    return st.mean(abs(a - b) for a, b in pairs)


end_min = {r["date"]: (ev[r["date"]]["last_hour"] + 1) * 60 for r in test}
t_a = mae((end_min[r["date"]] + med_delay, r["peak_min"]) for r in test)
t_b = mae((med_peak_min, r["peak_min"]) for r in test)
s_a = mae((icpt + slope * r["audience"], r["peak30"]) for r in test)
s_b = mae((med_size, r["peak30"]) for r in test)
res = {
    "unique_rows": len(seen),
    "event_days": len(evd),
    "non_event_days": len(non),
    "train_n": len(train),
    "test_n": len(test),
    "train_median_delay_min": med_delay,
    "delay_quartiles_all_event_days": st.quantiles([r["delay_min"] for r in evd], n=4),
    "event_peak30_median": st.median(r["peak30"] for r in evd),
    "non_event_peak30_median": st.median(r["peak30"] for r in non),
    "size_fit": {"slope_per_audience": slope, "intercept": icpt},
    "time_mae_min": {"A_block_end_plus_delay": t_a, "B_constant": t_b},
    "size_mae": {"A_audience_line": s_a, "B_constant": s_b},
    "time_pass": t_a <= 0.8 * t_b,
    "size_pass": s_a <= 0.8 * s_b,
}
(HERE / "exit_after_show_v03.json").write_text(
    json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(res, ensure_ascii=False, indent=2))
